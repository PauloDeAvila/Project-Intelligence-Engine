"""Explicit one-time setup and baseline CLI for PIE Phase 1.

No modification of Codex or RTK configurations without --apply.
Existing MCP server registrations are never overwritten automatically.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from pie.gateway.metrics import report
from pie.gateway.rtk_adapter import install_rtk_codex_hook, rtk_version
from pie.indexing.global_workspace import detect_workspace
from pie.storage.locations import ENV_HOME, global_home


def registration_plan(name: str, upstream: list[str], *, python: str,
                      max_chars: int = 2500,
                      compress_tools: tuple[str,...] = ()) -> list[str]:
    if not name or not name.replace("-","").replace("_","").isalnum() or len(name)>64:
        raise ValueError("MCP registration name must be 1..64 alphanumeric/hyphen/underscore")
    if not upstream or not all(isinstance(s,str) and s for s in upstream):
        raise ValueError("Upstream argv required")
    if type(max_chars) is not int or not 800<=max_chars<=64000:
        raise ValueError("Invalid max_chars")
    if not all(t and isinstance(t,str) and len(t)<=128 for t in compress_tools):
        raise ValueError("Invalid compressor tool names")
    argv=["codex","mcp","add",name,"--",python,"-m","pie.gateway.mcp_stdio",
          "--max-chars",str(max_chars)]
    for tool in compress_tools:
        argv.extend(["--compress-tool",tool])
    return [*argv,"--",*upstream]


def register_mcp(name: str, upstream: list[str], *, python: str,
                 max_chars: int = 2500, compress_tools: tuple[str,...] = (),
                 apply: bool = False) -> dict:
    cmd=registration_plan(name,upstream,python=python,
                          max_chars=max_chars,compress_tools=compress_tools)
    if not apply:
        return {"state":"DRY_RUN","command":cmd,
                "note":"Review actual upstream command and auth before --apply"}
    if not shutil.which("codex"):
        raise RuntimeError("Codex CLI missing from PATH")
    check=subprocess.run(["codex","mcp","get",name],capture_output=True,
                         text=True,timeout=15,check=False)
    if check.returncode==0:
        raise ValueError("MCP name already registered: "+name+
                         " (no automatic overwrite)")
    installed=subprocess.run(cmd,capture_output=True,text=True,
                             timeout=30,check=False)
    if installed.returncode:
        raise RuntimeError("Codex MCP registration failed: "+installed.stderr[:500])
    return {"state":"INSTALLED","name":name,
            "verify_command":["codex","mcp","get",name],
            "note":"This registers an additional proxy; existing MCP servers remain unchanged"}


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="PIE Phase 1 operator commands")
    parser.add_argument("--store",type=Path,default=None)
    actions=parser.add_subparsers(dest="action",required=True)
    actions.add_parser("rtk-status")
    actions.add_parser("install-rtk").add_argument("--apply",action="store_true")
    stats=actions.add_parser("metrics")
    stats.add_argument("--workspace",type=Path,default=Path.cwd())
    register=actions.add_parser("register-mcp")
    register.add_argument("--name",required=True)
    register.add_argument("--max-chars",type=int,default=2500)
    register.add_argument("--compress-tool",action="append",default=[])
    register.add_argument("--apply",action="store_true")
    register.add_argument("upstream",nargs=argparse.REMAINDER)
    args=parser.parse_args(argv)
    os.environ[ENV_HOME]=str((args.store or global_home()).resolve())
    try:
        if args.action=="rtk-status":
            result={"rtk_version":rtk_version(),
                    "available":shutil.which("rtk") is not None}
        elif args.action=="install-rtk":
            result=install_rtk_codex_hook(accept_config_change=args.apply)
        elif args.action=="metrics":
            result=report(detect_workspace(args.workspace))
        else:
            upstream=args.upstream
            if upstream and upstream[0]=="--":
                upstream=upstream[1:]
            result=register_mcp(args.name,upstream,python=sys.executable,
                                max_chars=args.max_chars,
                                compress_tools=tuple(args.compress_tool),
                                apply=args.apply)
    except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired) as exc:
        print(json.dumps({"state":"ERROR","error":str(exc)},ensure_ascii=False))
        return 1
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
