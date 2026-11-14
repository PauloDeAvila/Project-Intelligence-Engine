"""Read-only fail-closed Codex routing audit; never claim universal interception."""
from __future__ import annotations
from hashlib import sha256
import json,shutil,tomllib
from pathlib import Path
from typing import Any

def _sha(blob:bytes)->str:return sha256(blob).hexdigest()
def _hook_present(obj:Any)->bool:
    if isinstance(obj,dict):
        command=obj.get("command")
        if isinstance(command,(list,tuple)):command=" ".join(str(x) for x in command)
        if isinstance(command,str) and "rtk hook codex" in command.lower():return True
        return any(_hook_present(v) for v in obj.values())
    if isinstance(obj,list):return any(_hook_present(v) for v in obj)
    return False

def audit_codex(home:Path,*,project_config:Path|None=None)->dict:
    home=Path(home).expanduser().resolve(strict=True)
    config=home/"config.toml"
    if not config.is_file():raise ValueError("Codex config.toml missing")
    raw=config.read_bytes();cfg=tomllib.loads(raw.decode("utf-8"))
    project_sha=None
    if project_config:
        extra=Path(project_config).expanduser().resolve(strict=True).read_bytes()
        proj=tomllib.loads(extra.decode("utf-8"));project_sha=_sha(extra)
        servers=dict(cfg.get("mcp_servers",{}))
        servers.update(proj.get("mcp_servers",{}))
    else:servers=cfg.get("mcp_servers",{})
    if not isinstance(servers,dict):raise ValueError("Invalid MCP registry")
    routes=[]
    for name,settings in sorted(servers.items()):
        if not isinstance(name,str) or not isinstance(settings,dict):raise ValueError("Invalid MCP item")
        if settings.get("enabled") is False:state,transport="DISABLED","disabled"
        elif isinstance(settings.get("url"),str):state,transport="UNWRAPPED_HTTP","http"
        elif isinstance(settings.get("command"),str):
            transport="stdio"
            cmd=settings["command"].lower();args=settings.get("args",[])
            if not isinstance(args,list) or not all(isinstance(v,str) for v in args):
                raise ValueError("MCP args must be string array")
            full=" ".join(args).lower()
            scoped=("pie.gateway.domain" in full and "serve" in args and
                    "--domain" in args and
                    args.index("--domain")+1<len(args) and
                    args[args.index("--domain")+1] in ("blender","web"))
            wrapped=(scoped or "pie.gateway.mcp_stdio" in full or
                     "pie-mcp-proxy" in cmd or "pie-mcp-proxy" in full)
            state="PIE_STDIO_WRAPPED" if wrapped else "UNWRAPPED_STDIO"
        else:state,transport="UNKNOWN_CONFIGURATION","unknown"
        routes.append({"name":name,"transport":transport,"route":state,
                       "has_environment":bool(settings.get("env") or settings.get("env_vars")),
                       "has_cwd":bool(settings.get("cwd")),"enabled":state!="DISABLED"})
    hooks=home/"hooks.json";hookdoc=None;hookhash=None
    if hooks.is_file():
        binary=hooks.read_bytes();hookhash=_sha(binary)
        try:hookdoc=json.loads(binary)
        except json.JSONDecodeError:pass
    rtk_hook=_hook_present(hookdoc)
    rtk=shutil.which("rtk") is not None
    active=[r for r in routes if r["enabled"]]
    wrapped=sum(r["route"]=="PIE_STDIO_WRAPPED" for r in active)
    uncovered=[r["name"] for r in active if r["route"]!="PIE_STDIO_WRAPPED"]
    counts={}
    for r in routes:counts[r["route"]]=counts.get(r["route"],0)+1
    return {"schema":"pie-codex-coverage-audit-v1","codex_config_sha256":_sha(raw),
            "project_config_sha256":project_sha,"hooks_sha256":hookhash,
            "rtk_binary_in_path":rtk,"rtk_hook_configured":rtk_hook,
            "terminal_interception":("PARTIAL_FOR_RECOGNIZED_COMMANDS" if rtk_hook and rtk
                                     else "NOT_VERIFIED"),
            "mcp":{"active_servers":len(active),"wrapped_stdio":wrapped,
                   "unwrapped_or_unknown_servers":uncovered,"routes":routes,
                   "counts":counts,"configured_routing_ratio":round(wrapped/len(active),5) if active else None},
            "coverage_state":("PARTIAL_RTK_AND_MCP_ROUTED" if rtk and rtk_hook
                              and active and not uncovered else "GAPS_OR_NO_ROUTED_SERVERS"),
            "universal_interception_certified":False,
            "reason":"Native tools, unknown shell commands, remote HTTP and client-specific routes remain unproven",
            "privacy":"No raw commands, environment secrets, TOML, or credentials exported"}
