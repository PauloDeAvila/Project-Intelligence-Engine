"""Global workspace-aware PIE MCP, independent of agent prompts.

Install once in the Codex user profile; the server inherits the client's
current workspace directory, indexes before replying, and polls the filesystem.
All data live under ~/.pie-global. No user source tree is modified.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

from pie.indexing.global_workspace import GlobalWorkspaceIndex
from pie.interfaces.mcp_server import dispatch
from pie.storage.locations import ENV_HOME, global_home

EXTRA_TOOLS = [
    {
        "name": "pie_global_status",
        "description": "Read current global PIE workspace index state and automatic refresh metrics.",
        "inputSchema": {"type":"object","properties":{},"additionalProperties":False},
    },
    {
        "name": "pie_global_find_files",
        "description": "Search bounded source text and paths across supported languages in the current auto-indexed workspace. Results are file-hash verified, non-Python languages have lexical coverage only.",
        "inputSchema": {"type":"object","properties":{
            "query":{"type":"string"},
            "limit":{"type":"integer","minimum":1,"maximum":20},
            "max_chars":{"type":"integer","minimum":700,"maximum":64000}},
            "required":["query"],"additionalProperties":False},
    },
]


def _error_reply(id_, message: str) -> dict:
    return {"jsonrpc":"2.0","id":id_,"result":{
        "isError":True,"content":[{"type":"text","text":message[:800]}],
    }}


def _dispatch(req: dict, manager: GlobalWorkspaceIndex, *, tool_profile: str) -> dict | None:
    if req.get("method") == "tools/list":
        original = dispatch(req, manager.root, tool_profile=tool_profile)
        if original and isinstance(original.get("result"), dict):
            original["result"]["tools"].extend(EXTRA_TOOLS)
        return original
    if req.get("method") == "tools/call" and isinstance(req.get("params"), dict):
        params = req["params"]
        name = params.get("name")
        if name in ("pie_global_status", "pie_global_find_files"):
            args = params.get("arguments", {})
            if not isinstance(args, dict) or (
                name == "pie_global_status" and args):
                return _error_reply(req.get("id"),"Invalid global tool arguments")
            if name == "pie_global_find_files" and (
                set(args)-{"query","limit","max_chars"} or "query" not in args):
                return _error_reply(req.get("id"),"Invalid file search arguments")
            try:
                value = (manager.status() if name == "pie_global_status"
                         else manager.search(args["query"], limit=args.get("limit",5),
                                             max_chars=args.get("max_chars",4000)))
                return {"jsonrpc":"2.0","id":req.get("id"),"result":{
                    "content":[{"type":"text","text":json.dumps(value,ensure_ascii=False,separators=(",",":"))}]
                }}
            except (TypeError, ValueError, OSError) as exc:
                return _error_reply(req.get("id"),f"{type(exc).__name__}: {exc}")
    return dispatch(req, manager.root, tool_profile=tool_profile)


def run_stdio(workspace: Path, *, poll_seconds: float = 5.0,
              tool_profile: str = "compact") -> int:
    if not 0 <= poll_seconds <= 3600:
        raise ValueError("poll_seconds must be between 0 (disabled) and 3600")
    if tool_profile not in ("full","compact"):
        raise ValueError("Invalid MCP tool profile")
    manager=GlobalWorkspaceIndex(workspace,force_global=True)
    manager.refresh()  # startup bootstrap, before any model discovers tools.
    stopping=threading.Event()

    def watcher() -> None:
        while not stopping.wait(poll_seconds):
            try:
                manager.refresh()
            except Exception as exc:
                manager.error=f"{type(exc).__name__}: {exc}"
                # A subsequent model request will fail closed until refresh works.

    thread=None
    if poll_seconds:
        thread=threading.Thread(target=watcher,name="pie-global-watcher",daemon=True)
        thread.start()
    try:
        for line in sys.stdin:
            try:
                req=json.loads(line)
                if not isinstance(req,dict):
                    raise ValueError("Expected MCP object")
                if req.get("jsonrpc")!="2.0":
                    raise ValueError("Invalid JSON-RPC version")
                if req.get("method") == "tools/call":
                    manager.refresh() # ensure freshness before each tool call.
                    if manager.error:
                        raise RuntimeError("Automatic index refresh failed: "+manager.error)
                reply=_dispatch(req,manager,tool_profile=tool_profile)
            except Exception as exc:
                req_id=req.get("id") if isinstance(locals().get("req"),dict) else None
                reply=_error_reply(req_id,f"PIE_GLOBAL_UNAVAILABLE: {type(exc).__name__}: {exc}")
            if reply is not None:
                sys.stdout.write(json.dumps(reply,ensure_ascii=False,separators=(",",":"))+"\n")
                sys.stdout.flush()
    finally:
        stopping.set()
        if thread:
            thread.join(timeout=2)
    return 0


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description="Global zero-prompt PIE MCP")
    parser.add_argument("--workspace",type=Path,default=Path.cwd())
    parser.add_argument("--store",type=Path,default=None)
    parser.add_argument("--poll-seconds",type=float,default=5.0)
    parser.add_argument("--tool-profile",choices=("full","compact"),default="compact")
    args=parser.parse_args(argv)
    # Process-only setting. Do not set a user-wide environment variable.
    os.environ[ENV_HOME]=str((args.store or global_home()).expanduser().resolve())
    return run_stdio(args.workspace,poll_seconds=args.poll_seconds,
                     tool_profile=args.tool_profile)


def install_codex() -> dict:
    """Explicit one-time user action; writes only through Codex's own CLI."""
    if not shutil.which("codex"):
        raise RuntimeError("Codex CLI not found in PATH")
    # Refuse to silently overwrite an existing global registration.
    current=subprocess.run(["codex","mcp","get","pie-global"],capture_output=True,
                           text=True,timeout=15)
    if current.returncode==0:
        return {"status":"ALREADY_REGISTERED","note":"Inspect codex mcp get pie-global"}
    command=["codex","mcp","add","pie-global","--",sys.executable,
             "-m","pie.interfaces.global_mcp"]
    run=subprocess.run(command,capture_output=True,text=True,timeout=30)
    if run.returncode!=0:
        raise RuntimeError("Codex registration failed: "+run.stderr[:800])
    return {"status":"INSTALLED","command":"codex mcp get pie-global",
            "global_storage":str(global_home())}


def cli(argv=None) -> int:
    parser=argparse.ArgumentParser(description="Global PIE setup/status")
    parser.add_argument("command",choices=("install-codex","status","scan","watch"))
    parser.add_argument("--workspace",type=Path,default=Path.cwd())
    parser.add_argument("--store",type=Path)
    parser.add_argument("--poll-seconds",type=float,default=5.0)
    args=parser.parse_args(argv)
    if args.store:
        os.environ[ENV_HOME]=str(args.store.expanduser().resolve())
    else:
        os.environ[ENV_HOME]=str(global_home())
    if args.command=="install-codex":
        result=install_codex()
    else:
        manager=GlobalWorkspaceIndex(args.workspace,force_global=True)
        result=manager.refresh()
        if args.command=="status":
            result=manager.status()
        if args.command=="watch":
            try:
                while True:
                    if args.poll_seconds <= 0:
                        raise ValueError("watch interval must be positive")
                    threading.Event().wait(args.poll_seconds)
                    current=manager.refresh()
                    if current["mode"]!="UNCHANGED":
                        print(json.dumps(current,ensure_ascii=False),flush=True)
            except KeyboardInterrupt:
                return 0
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
