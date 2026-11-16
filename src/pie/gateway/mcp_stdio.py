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
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import sys
import threading
import uuid
from typing import Any, TextIO

from pie.gateway.metrics import record
from pie.gateway.bootstrap import path as bootstrap_path
from pie.gateway.policy import mcp_compactable, reduce_text
from pie.gateway.web_results import (WEB_CONTEXT_NAME, WEB_CONTEXT_TOOL,
                                     web_context_query, web_result_eligible,
                                     web_snapshot_preview)
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


def _event_id(req_id: Any, prefix: str) -> str:
    """Create a bounded event ID without storing request content."""
    return prefix + "-" + hashlib.sha256(_id(req_id).encode("utf-8")).hexdigest()[:32]


def _tool_error(req_id: Any, message: str) -> dict:
    return {"jsonrpc":"2.0","id":req_id,
            "result":{"isError":True,"content":[{"type":"text","text":message[:700]}]}}


def _workspace_fingerprint(root: Path) -> str:
    return hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]


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
                 ("get_scene_info","get_object_info"), profile: str = "generic",
                 request_timeout_sec: float = 120.0,
                 exposed_tools: tuple[str, ...] = ()) -> None:
        self.root=detect_workspace(root)
        if not command or not all(isinstance(v,str) and v for v in command):
            raise ValueError("Upstream server command is required")
        if type(max_chars) is not int or not 800<=max_chars<=64000:
            raise ValueError("Invalid MCP result budget")
        if profile not in ("generic","web"):
            raise ValueError("MCP profile must be generic or web")
        if isinstance(request_timeout_sec, bool) or not isinstance(request_timeout_sec, (int, float)) or not 1 <= request_timeout_sec <= 3600:
            raise ValueError("Invalid MCP request timeout")
        self.profile=profile
        self.request_timeout_sec=float(request_timeout_sec)
        self.command=list(command)
        self.max_chars=max_chars
        self.compress_tools=frozenset(compress_tools)
        if any(not isinstance(tool, str) or not tool for tool in exposed_tools):
            raise ValueError("Invalid exposed tool allowlist")
        self.exposed_tools=frozenset(exposed_tools)
        self._write_lock=threading.RLock()
        self._pending_lock=threading.RLock()
        self._pending:dict[str,tuple[str,str,float,threading.Timer]]={}
        self._request_history:dict[str,tuple[str,str,float]]={}
        self._expired:set[str]=set()
        self._output_schema_tools:set[str]=set()
        self._listed_tools:set[str]=set()
        self._collision=False
        self._last_web_source: str | None = None
        self._web_source_ready = threading.Condition(threading.RLock())
        self._upstream_write_lock = threading.RLock()
        self._internal_lock = threading.RLock()
        self._internal_waiters: dict[str, tuple[threading.Event, dict | None]] = {}
        self._upstream_stdin: TextIO | None = None
        self._diagnostics_path=bootstrap_path()
        self._diagnostic("gateway_constructed", profile=profile,
                         workspace_id=_workspace_fingerprint(self.root),
                         upstream_executable=Path(self.command[0]).name,
                         request_timeout_sec=self.request_timeout_sec)

    def _diagnostic(self, event: str, **fields: object) -> None:
        """Best-effort lifecycle diagnostics; never writes to MCP stdout."""
        if self._diagnostics_path is None:
            return
        row={"ts_utc":datetime.now(timezone.utc).isoformat(),"event":event,"pid":os.getpid()}
        for key in ("PIE_RUN_ID", "PIE_PAIR_ID", "PIE_TASK_ID", "PIE_CONDITION", "PIE_SCENARIO_ID", "PIE_GATEWAY_SERVER"):
            value=os.environ.get(key)
            if value:
                row[key.lower().replace("pie_", "")]=value[:120]
        for key,value in fields.items():
            if isinstance(value,(str,int,float,bool)) or value is None:
                row[key]=value
        try:
            self._diagnostics_path.parent.mkdir(parents=True,exist_ok=True)
            with self._diagnostics_path.open("a",encoding="utf-8") as stream:
                stream.write(_json(row)+"\n")
        except OSError:
            pass

    def _send(self, stdout: TextIO, message: dict) -> None:
        with self._write_lock:
            stdout.write(_json(message)+"\n")
            stdout.flush()

    def _handle_recovery(self, message: dict) -> dict:
        args=message.get("params",{}).get("arguments",{})
        started=time.perf_counter()
        try:
            result=recovery_page(self.root,args)
            self._diagnostic("recovery_complete", tool=RECOVERY_NAME)
            try:
                page=json.loads(result["content"][0]["text"])
                record(self.root,surface="mcp",tool=RECOVERY_NAME,state="RECOVERY",
                       source_chars=int(page["total_chars"]),returned_chars=len(_json(result)),
                       elapsed_ms=(time.perf_counter()-started)*1000,
                       source_event_id=_event_id(message.get("id"), "recovery"))
            except (OSError,ValueError,TypeError,KeyError,IndexError):
                pass
            return {"jsonrpc":"2.0","id":message.get("id"),"result":result}
        except (ValueError, OSError) as exc:
            self._diagnostic("recovery_failed", error_type=type(exc).__name__)
            return _tool_error(message.get("id"),
                               "PIE_RECOVERY_FAILED: "+str(exc))

    def _transform(self, response: dict) -> dict:
        if not isinstance(response,dict) or "id" not in response:
            return response
        response_key = _id(response["id"])
        with self._pending_lock:
            pending=self._pending.pop(response_key,None)
            history=self._request_history.pop(response_key,None)
        if not pending:
            with self._pending_lock:
                if response_key in self._expired:
                    self._expired.discard(response_key)
                    return None
            if history is not None:
                pending=(*history,None)
            body=response.get("result")
            if pending is None and isinstance(body,dict) and isinstance(body.get("tools"),list):
                pending=("tools/list","",0.0,None)
            elif pending is None:
                return response
        method,tool,started,timer=pending
        if timer is not None:
            timer.cancel()
        if method=="tools/list":
            body=response.get("result")
            if isinstance(body,dict) and isinstance(body.get("tools"),list):
                if self.exposed_tools:
                    body["tools"]=[spec for spec in body["tools"]
                                   if isinstance(spec,dict) and spec.get("name") in self.exposed_tools]
                for spec in body["tools"]:
                    if isinstance(spec,dict):
                        name=spec.get("name")
                        if isinstance(name,str):
                            self._listed_tools.add(name)
                        if spec.get("outputSchema") is not None:
                            self._output_schema_tools.add(name)
                        if name==RECOVERY_NAME:
                            self._collision=True
                if (not self.exposed_tools or RECOVERY_NAME in self.exposed_tools) and not self._collision and not any(t.get("name")==RECOVERY_NAME
                                                   for t in body["tools"] if isinstance(t,dict)):
                    body["tools"].append(dict(RECOVERY_TOOL))
                if (self.profile == "web" and not self._collision
                        and (not self.exposed_tools or WEB_CONTEXT_NAME in self.exposed_tools)
                        and not any(t.get("name") == WEB_CONTEXT_NAME
                                     for t in body["tools"] if isinstance(t, dict))):
                    body["tools"].append(dict(WEB_CONTEXT_TOOL))
                self._diagnostic("tools_list_complete", tool_count=len(body["tools"]),
                                 recovery_collision=self._collision)
            return response
        if method!="tools/call":
            return response
        elapsed_ms=(time.perf_counter()-started)*1000
        self._diagnostic("tools_call_response", tool=tool,
                         status="error" if "error" in response else "result",
                         duration_ms=round(elapsed_ms,3))
        def observe_passthrough(state: str) -> None:
            encoded = _json(response)
            try:
                record(self.root, surface="mcp", tool=tool, state=state,
                       source_chars=len(encoded), returned_chars=len(encoded),
                       elapsed_ms=elapsed_ms)
            except (OSError, ValueError):
                pass
        body=response.get("result")
        if not isinstance(body,dict) or not isinstance(body.get("content"),list):
            observe_passthrough("ERROR" if "error" in response else "STRUCTURED_PASSTHROUGH")
            return response
        content=body["content"]
        if (self.profile == "web" and WEB_CONTEXT_NAME in self.exposed_tools
                and tool == "browser_navigate" and not body.get("isError")):
            content[:] = [{"type": "text", "text": "PIE_NAVIGATED"}]
            try:
                record(self.root, surface="mcp", tool=tool,
                       state="SEMANTIC_NAVIGATION_ACK", source_chars=0,
                       returned_chars=len("PIE_NAVIGATED"), elapsed_ms=elapsed_ms,
                       source_event_id=_event_id(response["id"], "resp"))
            except (OSError, ValueError):
                pass
            return response
        if len(content)!=1 or not isinstance(content[0],dict) or not isinstance(content[0].get("text"),str):
            observe_passthrough("STRUCTURED_PASSTHROUGH")
            return response
        source=content[0]["text"]
        if self.profile == "web" and web_result_eligible(source, tool):
            with self._web_source_ready:
                self._last_web_source = source
                self._web_source_ready.notify_all()
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
                       source_chars=len(source),returned_chars=len(source),elapsed_ms=elapsed_ms,
                       source_event_id=_event_id(response["id"], "resp"))
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
                       elapsed_ms=elapsed_ms,
                       source_event_id=_event_id(response["id"], "resp"))
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
                   elapsed_ms=elapsed_ms,
                   output_id=reduced["output_id"],
                   source_event_id=_event_id(response["id"], "resp"))
        except (ValueError, RuntimeError, OSError):
            # Fail open for exact tool semantics; never invent a successful summary.
            return response
        return response

    def _handle_web_context(self, message: dict) -> dict:
        args = message.get("params", {}).get("arguments", {})
        try:
            if not isinstance(args, dict) or set(args) - {"query"}:
                raise ValueError("Invalid web context parameters")
            if self._last_web_source is None:
                self._request_internal_snapshot()
            deadline = time.monotonic() + self.request_timeout_sec
            with self._web_source_ready:
                while self._last_web_source is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ValueError("No browser snapshot is available")
                    self._web_source_ready.wait(timeout=remaining)
                source = self._last_web_source
            result = web_context_query(source,
                                       args.get("query", ""),
                                       700)
            return {"jsonrpc": "2.0", "id": message.get("id"),
                    "result": {"content": [{"type": "text", "text": _json(result)}]}}
        except (ValueError, TypeError) as exc:
            return _tool_error(message.get("id"), "PIE_WEB_CONTEXT_FAILED: " + str(exc))

    def _request_internal_snapshot(self) -> None:
        """Fetch one snapshot without forwarding it through the client context."""
        if self._upstream_stdin is None:
            raise ValueError("Upstream is not ready")
        internal_id = "pie-internal-snapshot-" + uuid.uuid4().hex
        event = threading.Event()
        with self._internal_lock:
            self._internal_waiters[internal_id] = (event, None)
        request = {"jsonrpc": "2.0", "id": internal_id, "method": "tools/call",
                   "params": {"name": "browser_snapshot", "arguments": {}}}
        try:
            with self._upstream_write_lock:
                self._upstream_stdin.write(_json(request) + "\n")
                self._upstream_stdin.flush()
            if not event.wait(self.request_timeout_sec):
                raise ValueError("Internal browser snapshot timed out")
            with self._internal_lock:
                result = self._internal_waiters[internal_id][1]
            if not isinstance(result, dict) or "error" in result:
                raise ValueError("Internal browser snapshot failed")
            body = result.get("result")
            parts = body.get("content") if isinstance(body, dict) else None
            text = parts[0].get("text") if isinstance(parts, list) and parts else None
            if not isinstance(text, str) or not web_result_eligible(text, "browser_snapshot"):
                raise ValueError("Internal response is not a valid browser snapshot")
            with self._web_source_ready:
                self._last_web_source = text
                self._web_source_ready.notify_all()
            try:
                record(self.root, surface="mcp", tool="browser_snapshot",
                       state="INTERNAL_CONTEXT", source_chars=len(text),
                       returned_chars=0, elapsed_ms=0.0)
            except (OSError, ValueError):
                pass
        finally:
            with self._internal_lock:
                self._internal_waiters.pop(internal_id, None)

    def _expire(self, key: str, stdout: TextIO) -> None:
        with self._pending_lock:
            pending = self._pending.pop(key, None)
            if pending is None:
                return
            self._expired.add(key)
            history = self._request_history.pop(key, None)
        method, tool, started, _ = pending
        if method == "tools/call":
            self._diagnostic("request_timeout", tool=tool)
            try:
                record(self.root, surface="mcp", tool=tool, state="TIMEOUT",
                       source_chars=0, returned_chars=0,
                       elapsed_ms=(time.perf_counter() - started) * 1000,
                       source_event_id=_event_id(json.loads(key), "timeout"))
            except (OSError, ValueError):
                pass
        try:
            self._send(stdout, {"jsonrpc":"2.0", "id":json.loads(key),
                                "error":{"code":-32001,
                                         "message":"PIE_GATEWAY_TIMEOUT"}})
        except OSError:
            pass

    def run(self, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
        self._diagnostic("upstream_spawn_start")
        try:
            upstream=subprocess.Popen(
                self.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=None,bufsize=1,text=True,encoding="utf-8",errors="replace",
                cwd=self.root,shell=False)
        except OSError as exc:
            self._diagnostic("upstream_spawn_failed", error_type=type(exc).__name__)
            self._diagnostic("UPSTREAM_FAILED", error_type=type(exc).__name__)
            raise
        self._diagnostic("upstream_spawned", pid=upstream.pid)
        self._diagnostic("UPSTREAM_STARTED", pid=upstream.pid)
        assert upstream.stdin is not None and upstream.stdout is not None
        self._upstream_stdin = upstream.stdin

        def read_upstream() -> None:
            for line in upstream.stdout:
                try:
                    payload=json.loads(line)
                    internal_id = payload.get("id") if isinstance(payload, dict) else None
                    with self._internal_lock:
                        internal = self._internal_waiters.get(internal_id) if isinstance(internal_id, str) else None
                        if internal is not None:
                            event, _ = internal
                            self._internal_waiters[internal_id] = (event, payload)
                            event.set()
                            continue
                    response=self._transform(payload) if isinstance(payload,dict) else payload
                    if response is None:
                        continue
                    with self._write_lock:
                        stdout.write(_json(response)+"\n")
                        stdout.flush()
                except (ValueError, TypeError):
                    # A non-JSON stdio line is a violation by the upstream server.
                    # Do not forward malformed content on the protocol channel.
                    sys.stderr.write("PIE: upstream emitted invalid JSON-RPC\n")
                    self._diagnostic("upstream_invalid_json")
            upstream.stdout.close()
            self._diagnostic("upstream_stdout_eof")

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
                    params=request.get("params")
                    method=request.get("method", "")
                    if (method == "tools/call" and self.exposed_tools and
                            isinstance(params, dict) and params.get("name") not in self.exposed_tools):
                        self._send(stdout, _tool_error(request["id"], "PIE_TOOL_NOT_EXPOSED"))
                        continue
                    if method == "initialize":
                        self._diagnostic("MCP_INITIALIZE_RECEIVED")
                    elif method == "tools/list":
                        self._diagnostic("MCP_TOOLS_LIST_RECEIVED")
                    elif method == "tools/call":
                        self._diagnostic("MCP_TOOL_CALL_RECEIVED",
                                         tool=params.get("name", "") if isinstance(params, dict) else "")
                    self._diagnostic("downstream_request", method=request.get("method",""),
                                     tool=params.get("name","") if isinstance(params,dict) else "")
                    if (request.get("method")=="tools/call"
                            and isinstance(request.get("params"),dict)
                            and request["params"].get("name")==RECOVERY_NAME
                            and not self._collision):
                        self._send(stdout,self._handle_recovery(request))
                        continue
                    if (request.get("method") == "tools/call"
                            and isinstance(request.get("params"), dict)
                            and request["params"].get("name") == WEB_CONTEXT_NAME
                            and self.profile == "web" and not self._collision):
                        self._send(stdout, self._handle_web_context(request))
                        continue
                    name=(request.get("params") or {}).get("name","") if isinstance(request.get("params"),dict) else ""
                    key=_id(request["id"])
                    with self._pending_lock:
                        if key in self._pending:
                            self._diagnostic("duplicate_request_suppressed")
                            continue
                        started=time.perf_counter()
                        timer=threading.Timer(self.request_timeout_sec, self._expire,
                                              args=(key,stdout))
                        self._pending[key]=(request.get("method",""),name,
                                            started,timer)
                        self._request_history[key]=(request.get("method",""),name,started)
                        timer.daemon=True
                        timer.start()
                with self._upstream_write_lock:
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
            with self._pending_lock:
                for _, _, _, timer in self._pending.values():
                    timer.cancel()
                self._pending.clear()
                self._request_history.clear()
            self._diagnostic("upstream_exit", exit_code=upstream.returncode)
        return upstream.returncode or 0


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="PIE transparent MCP stdio output proxy")
    parser.add_argument("--workspace",type=Path,default=Path.cwd())
    parser.add_argument("--store",type=Path,default=None)
    parser.add_argument("--max-chars",type=int,default=2500)
    parser.add_argument("--profile",choices=("generic","web"),default="generic")
    parser.add_argument("--request-timeout-sec",type=float,default=120.0)
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
                          profile=opt.profile,request_timeout_sec=opt.request_timeout_sec)
    return proxy.run()


if __name__=="__main__":
    raise SystemExit(main())
