"""Transparent MCP stdio intermediary with conservative, recoverable reductions.

- No extra execution of upstream tools, ever.
- No shell or network: operator supplies an argv for an existing local server.
- JSON-RPC request IDs, notifications, errors and structured responses survive.
- Only successful, explicitly allowlisted text-only tool results are reduced.
- Recovery is a local MCP tool, paged from the existing global PIE output store.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any, TextIO

from pie.gateway.metrics import record
from pie.gateway.policy import mcp_compactable, reduce_text
from pie.gateway.web_results import web_result_eligible, web_snapshot_preview
from pie.indexing.global_workspace import detect_workspace
from pie.retrieval.output_pipeline import recover_output
from pie.storage.locations import ENV_HOME, global_home

RECOVERY_NAME = "pie_gateway_output_get"
RECOVERY_TOOL = {
    "name": RECOVERY_NAME,
    "description": "Recover a sanitized chunk of a tool observation compacted by PIE; "
                   "source data are project-isolated, not raw unredacted logs.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "output_id": {"type":"string"},
            "start": {"type":"integer","minimum":0},
            "max_chars": {"type":"integer","minimum":800,"maximum":16000}
        },
        "required": ["output_id"], "additionalProperties": False
    },
}


def _id(value: Any) -> str:
    return json.dumps(value, separators=(",",":"), ensure_ascii=False)


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",",":"), ensure_ascii=False)


def _tool_error(req_id: Any, message: str) -> dict:
    return {"jsonrpc":"2.0","id":req_id,
            "result":{"isError":True,"content":[{"type":"text","text":message[:700]}]}}


def recovery_page(root: Path, args: object) -> dict:
    if not isinstance(args, dict) or set(args)-{"output_id","start","max_chars"}:
        raise ValueError("Invalid recovery tool parameters")
    start=args.get("start",0)
    limit=args.get("max_chars",4000)
    if type(start) is not int or start<0:
        raise ValueError("Invalid start offset")
    if type(limit) is not int or not 800<=limit<=16000:
        raise ValueError("Invalid recovery character budget")
    output_id=args.get("output_id")
    payload=recover_output(root, output_id)
    source=payload["text"]
    if start>len(source):
        raise ValueError("Start offset exceeds recovery length")
    # Budget covers serialized JSON inside TextContent. Reserve conservatively.
    step=max(0,min(len(source)-start,limit-500))
    while True:
        end=start+step
        body={"status":"COMPLETE_SANITIZED" if end==len(source) else "PARTIAL",
              "output_id":output_id,"start":start,"end":end,
              "total_chars":len(source),
              "text":source[start:end],
              "sha256":payload["sha256"],
              "next_start":end if end<len(source) else None,
              "redacted_before_storage":True}
        encoded=_json(body)
        if len(encoded)<=limit and (step>0 or start==len(source)):
            return {"content":[{"type":"text","text":encoded}]}
        if step<=0:
            raise ValueError("Budget too small for recovery metadata")
        step=max(0,step-max(1,len(encoded)-limit))


class MCPStdioGateway:
    def __init__(self, root: Path, command: list[str], *,
                 max_chars: int = 2500, compress_tools: tuple[str,...] =
                 ("get_scene_info","get_object_info"), profile: str = "generic") -> None:
        self.root=detect_workspace(root)
        if not command or not all(isinstance(v,str) and v for v in command):
            raise ValueError("Upstream server command is required")
        if type(max_chars) is not int or not 800<=max_chars<=64000:
            raise ValueError("Invalid MCP result budget")
        if profile not in ("generic","web"):
            raise ValueError("MCP profile must be generic or web")
        self.profile=profile
        self.command=list(command)
        self.max_chars=max_chars
        self.compress_tools=frozenset(compress_tools)
        self._write_lock=threading.RLock()
        self._pending_lock=threading.RLock()
        self._pending:dict[str,tuple[str,str]]={}
        self._output_schema_tools:set[str]=set()
        self._listed_tools:set[str]=set()
        self._collision=False

    def _send(self, stdout: TextIO, message: dict) -> None:
        with self._write_lock:
            stdout.write(_json(message)+"\n")
            stdout.flush()

    def _handle_recovery(self, message: dict) -> dict:
        args=message.get("params",{}).get("arguments",{})
        try:
            result=recovery_page(self.root,args)
            return {"jsonrpc":"2.0","id":message.get("id"),"result":result}
        except (ValueError, OSError) as exc:
            return _tool_error(message.get("id"),
                               "PIE_RECOVERY_FAILED: "+str(exc))

    def _transform(self, response: dict) -> dict:
        if not isinstance(response,dict) or "id" not in response:
            return response
        with self._pending_lock:
            pending=self._pending.pop(_id(response["id"]),None)
        if not pending:
            return response
        method,tool=pending
        if method=="tools/list":
            body=response.get("result")
            if isinstance(body,dict) and isinstance(body.get("tools"),list):
                for spec in body["tools"]:
                    if isinstance(spec,dict):
                        name=spec.get("name")
                        if isinstance(name,str):
                            self._listed_tools.add(name)
                        if spec.get("outputSchema") is not None:
                            self._output_schema_tools.add(name)
                        if name==RECOVERY_NAME:
                            self._collision=True
                if not self._collision and not any(t.get("name")==RECOVERY_NAME
                                                   for t in body["tools"] if isinstance(t,dict)):
                    body["tools"].append(dict(RECOVERY_TOOL))
            return response
        if method!="tools/call":
            return response
        body=response.get("result")
        if not isinstance(body,dict) or not isinstance(body.get("content"),list):
            return response
        content=body["content"]
        if len(content)!=1 or not isinstance(content[0],dict) or not isinstance(content[0].get("text"),str):
            return response
        source=content[0]["text"]
        eligible=(not self._collision and tool in self._listed_tools and
                  mcp_compactable(response,tool,self.compress_tools,
                                  has_output_schema=tool in self._output_schema_tools))
        web_view=None
        if eligible and self.profile=="web":
            eligible=web_result_eligible(source,tool)
            if eligible and len(source)>self.max_chars:
                web_view=web_snapshot_preview(source,max(250,self.max_chars-480))
                eligible=web_view is not None
        if not eligible or len(source)<=self.max_chars:
            # Telemetry only. Never mutate unsupported/structured/error results.
            try:
                record(self.root,surface="mcp",tool=tool,
                       state="PASSTHROUGH" if not eligible else "SMALL",
                       source_chars=len(source),returned_chars=len(source),elapsed_ms=0)
            except (OSError, ValueError):
                pass
            return response
        started=time.perf_counter()
        try:
            reduced=reduce_text(self.root,source,surface="mcp",tool=tool,
                                kind="web" if self.profile=="web" else "api",
                                max_chars=self.max_chars,record_metric=False)
            if reduced["state"]=="CAPTURE_LIMIT_EXCEEDED":
                # Oversize source cannot be fully recovered; do not rewrite it.
                record(self.root,surface="mcp",tool=tool,state="OVERSIZE_PASSTHROUGH",
                       source_chars=len(source),returned_chars=len(source),
                       elapsed_ms=(time.perf_counter()-started)*1000)
                return response
            envelope={"pie_gateway":"v1","state":reduced["state"],
                      "tool":tool,"preview":reduced["text"],
                      "output_id":reduced["output_id"],
                      "source_chars":reduced["source_chars"],
                      "returned_chars":reduced["returned_chars"],
                      "recovery_tool":RECOVERY_NAME,
                      "recovery":"complete_sanitized_source_only",
                      "token_measurement":None}
            if self.profile=="web" and web_view is not None:
                envelope["preview"]=web_view["preview"]
                envelope["web"]={k:v for k,v in web_view.items() if k!="preview"}
            encoded=_json(envelope)
            if len(encoded)>self.max_chars:
                # No invalid protocol; use metadata-only reference with hash-backed
                # recovery, not an over-budget preview.
                envelope["preview"]=None
                encoded=_json(envelope)
            if len(encoded)>self.max_chars:
                return response
            content[0]["text"]=encoded
            record(self.root,surface="mcp",tool=tool,state="COMPACTED",
                   source_chars=len(source),returned_chars=len(encoded),
                   elapsed_ms=(time.perf_counter()-started)*1000,
                   output_id=reduced["output_id"])
        except (ValueError, RuntimeError, OSError):
            # Fail open for exact tool semantics; never invent a successful summary.
            return response
        return response

    def run(self, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
        upstream=subprocess.Popen(
            self.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=None,bufsize=1,text=True,encoding="utf-8",errors="replace",
            cwd=self.root,shell=False)
        assert upstream.stdin is not None and upstream.stdout is not None

        def read_upstream() -> None:
            for line in upstream.stdout:
                try:
                    payload=json.loads(line)
                    response=self._transform(payload) if isinstance(payload,dict) else payload
                    with self._write_lock:
                        stdout.write(_json(response)+"\n")
                        stdout.flush()
                except (ValueError, TypeError):
                    # A non-JSON stdio line is a violation by the upstream server.
                    # Do not forward malformed content on the protocol channel.
                    sys.stderr.write("PIE: upstream emitted invalid JSON-RPC\n")
            upstream.stdout.close()

        reader=threading.Thread(target=read_upstream,daemon=True,
                                name="pie-mcp-upstream-reader")
        reader.start()
        try:
            for line in stdin:
                try:
                    request=json.loads(line)
                except ValueError:
                    # Forward malformed downstream input unchanged, allowing the
                    # native server to produce the standard JSON-RPC parse error.
                    request=None
                if isinstance(request,dict) and "id" in request:
                    if (request.get("method")=="tools/call"
                            and isinstance(request.get("params"),dict)
                            and request["params"].get("name")==RECOVERY_NAME
                            and not self._collision):
                        self._send(stdout,self._handle_recovery(request))
                        continue
                    name=(request.get("params") or {}).get("name","") if isinstance(request.get("params"),dict) else ""
                    with self._pending_lock:
                        self._pending[_id(request["id"])]=(request.get("method",""),name)
                upstream.stdin.write(line)
                upstream.stdin.flush()
        finally:
            upstream.stdin.close()
            try:
                upstream.wait(timeout=20)
            except subprocess.TimeoutExpired:
                upstream.kill()
                upstream.wait()
            reader.join(timeout=3)
        return upstream.returncode or 0


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="PIE transparent MCP stdio output proxy")
    parser.add_argument("--workspace",type=Path,default=Path.cwd())
    parser.add_argument("--store",type=Path,default=None)
    parser.add_argument("--max-chars",type=int,default=2500)
    parser.add_argument("--profile",choices=("generic","web"),default="generic")
    parser.add_argument("--compress-tool",action="append",default=None,
                        help="Explicitly authorize lossy text-only reduction for this tool")
    parser.add_argument("upstream",nargs=argparse.REMAINDER)
    opt=parser.parse_args(argv)
    command=opt.upstream[1:] if opt.upstream and opt.upstream[0]=="--" else opt.upstream
    os.environ[ENV_HOME]=str((opt.store or global_home()).resolve())
    if not command:
        parser.error("Provide upstream argv after --")
    proxy=MCPStdioGateway(opt.workspace,command,max_chars=opt.max_chars,
                          compress_tools=tuple(opt.compress_tool) if opt.compress_tool
                          else ("get_scene_info","get_object_info"),
                          profile=opt.profile)
    return proxy.run()


if __name__=="__main__":
    raise SystemExit(main())
