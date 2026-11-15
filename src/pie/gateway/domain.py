"""Two-domain PIE MCP server: Blender and browser navigation only.

This is an opt-in registration boundary. It cannot intercept native Codex
browser tools, unrelated MCP registrations or remote HTTP servers.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from pie.gateway.bootstrap import event as bootstrap_event

bootstrap_event("PROCESS_STARTED", module=__name__)
bootstrap_event("BOOTSTRAP_INITIALIZED")
bootstrap_event("IMPORT_STARTED", module="pie.gateway.mcp_stdio")
try:
    from pie.gateway.mcp_stdio import MCPStdioGateway
except Exception as exc:
    bootstrap_event("IMPORT_FAILED", error_type=type(exc).__name__)
    raise
bootstrap_event("IMPORT_SUCCEEDED", module="pie.gateway.mcp_stdio")

from pie.gateway.web_results import SNAPSHOT_RESULT_TOOLS
from pie.storage.locations import ENV_HOME, global_home


def domain_route(domain: str, upstream: list[str], *, python: str,
                 max_chars: int, exposed_tools: tuple[str, ...] = ()) -> tuple[list[str], tuple[str,...], str]:
    if domain not in ("blender","web"):
        raise ValueError("Only blender and web domains are implemented")
    if not upstream or not all(isinstance(x,str) and x for x in upstream):
        raise ValueError("Upstream MCP server command is required")
    if any(not isinstance(tool, str) or not tool for tool in exposed_tools):
        raise ValueError("Invalid exposed tool allowlist")
    if type(max_chars) is not int or not 800<=max_chars<=64000:
        raise ValueError("Invalid output budget")
    if domain=="blender":
        # Existing Blender bridge adds pie_blender_scene_delta and
        # pie_blender_expand. Keep its specialized observation compaction.
        # The outer gateway forwards all data without a second lossy pass.
        bridge=[python,"-m","pie.integrations.blender_mcp_bridge",
                "--max-chars",str(max_chars)]
        for tool in exposed_tools:
            bridge += ["--expose-tool", tool]
        bridge += ["--",*upstream]
        return (bridge,
                (),"generic")
    # Web profile applies only to recognizable Playwright accessibility
    # snapshot replies; other web actions, errors and image results pass through.
    return list(upstream),tuple(sorted(SNAPSHOT_RESULT_TOOLS)),"web"


def register_plan(domain: str, name: str, upstream: list[str], *,
                  python: str, max_chars: int = 2400) -> list[str]:
    domain_route(domain,upstream,python=python,max_chars=max_chars)
    if (not isinstance(name,str) or not 1<=len(name)<=64 or
        any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in name)):
        raise ValueError("Invalid MCP registration name")
    return ["codex","mcp","add",name,"--",python,"-m",
            "pie.gateway.domain","serve","--domain",domain,
            "--max-chars",str(max_chars),"--",*upstream]


def register_codex(domain: str, name: str, upstream: list[str], *,
                   python: str, max_chars: int = 2400, apply: bool = False) -> dict:
    plan=register_plan(domain,name,upstream,python=python,max_chars=max_chars)
    if not apply:
        # Do not display exact upstream argument list in logs, as it may include
        # authorization material. The command is printed locally only on request.
        return {"state":"DRY_RUN","domain":domain,"name":name,
                "command_executable":plan[0],"python":python,
                "upstream_executable":upstream[0],
                "output_budget_chars":max_chars,
                "note":"No registration changed; --apply creates a new name, not a replacement"}
    codex=shutil.which("codex")
    if not codex:raise RuntimeError("Codex CLI missing")
    check=subprocess.run([codex,"mcp","get",name],capture_output=True,
                         text=True,timeout=15,check=False)
    if check.returncode==0:raise RuntimeError("Refusing to overwrite registered MCP name")
    put=subprocess.run([codex,*plan[1:]],capture_output=True,
                       text=True,timeout=30,check=False)
    if put.returncode:raise RuntimeError("Codex MCP registration rejected")
    return {"state":"REGISTERED","domain":domain,"name":name,
            "verify":["codex","mcp","get",name],
            "note":"Original server unaffected; route clients to the new name explicitly"}


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="PIE Blender/Web-only MCP optimizer")
    subs=parser.add_subparsers(dest="action",required=True)
    for action in ("serve","register"):
        p=subs.add_parser(action)
        p.add_argument("--domain",required=True,choices=("blender","web"))
        p.add_argument("--max-chars",type=int,default=2400)
        p.add_argument("--workspace",type=Path,default=Path.cwd())
        p.add_argument("--store",type=Path)
        p.add_argument("--expose-tool", action="append", default=[])
        if action=="register":
            p.add_argument("--name",required=True)
            p.add_argument("--apply",action="store_true")
        p.add_argument("upstream",nargs=argparse.REMAINDER)
    args=parser.parse_args(argv)
    exit_code=2
    upstream=args.upstream[1:] if args.upstream and args.upstream[0]=="--" else args.upstream
    try:
        os.environ[ENV_HOME]=str((args.store or global_home()).expanduser().resolve())
        if args.action=="register":
            result=register_codex(args.domain,args.name,upstream,
                                  python=sys.executable,max_chars=args.max_chars,
                                  apply=args.apply)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            exit_code=0
            return exit_code
        command,tools,profile=domain_route(args.domain,upstream,
                                          python=sys.executable,max_chars=args.max_chars,
                                          exposed_tools=tuple(args.expose_tool))
        os.environ.setdefault("PIE_APP", args.domain)
        if os.environ.get("PIE_MCP_DIAGNOSTICS_PATH"):
            print(json.dumps({"event":"domain_gateway_start","domain":args.domain,
                              "upstream_executable":Path(upstream[0]).name},
                             separators=(",",":")),file=sys.stderr,flush=True)
        exit_code=MCPStdioGateway(args.workspace,command,max_chars=args.max_chars,
                                  compress_tools=tools,profile=profile,
                                  exposed_tools=tuple(args.expose_tool)).run()
        return exit_code
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
        # Never write protocol failures to MCP stdout.
        print("PIE domain gateway unavailable: "+type(exc).__name__,file=sys.stderr)
        return exit_code
    finally:
        bootstrap_event("PROCESS_EXITING", exit_code=exit_code)


if __name__=="__main__":
    raise SystemExit(main())
