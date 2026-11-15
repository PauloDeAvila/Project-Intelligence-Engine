"""Operator CLI for read-only Codex usage capture, comparison and routing audit."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from pie.certification.live_codex import _read_records,capture_codex,compare,validate_scenario,preflight_codex
from pie.certification.task_telemetry import import_provider_record
from pie.certification.coverage import audit_codex

_SAFE_ERROR_PREFIXES=(
    "PRECHECK_", "MCP route evidence", "Codex execution unavailable/timeout",
    "Codex executable unavailable", "Codex version unavailable", "Codex failed",
    "Missing ", "Invalid ", "No ", "Need ", "Condition/", "Accuracy ",
    "Duplicate ", "Mismatched ", "Same configuration", "Not enough ",
)

def _safe_error(exc:Exception)->str:
    message=" ".join(str(exc).split())[:240]
    if any(message.startswith(prefix) for prefix in _SAFE_ERROR_PREFIXES):
        return message
    return type(exc).__name__

def _scenario_app(scenario: dict) -> str:
    value = " ".join(str(scenario.get(k, "")) for k in ("required_mcp_server", "scenario_id")).lower()
    if "blender" in value:
        return "blender"
    if "web" in value or "playwright" in value:
        return "web"
    return "other_mcp"

def main(argv=None)->int:
    parser=argparse.ArgumentParser(description="PIE real Codex token and routing certification")
    subs=parser.add_subparsers(dest="cmd",required=True)
    a=subs.add_parser("audit");a.add_argument("--codex-home",type=Path,required=True)
    a.add_argument("--project-config",type=Path);a.add_argument("--output",type=Path)
    c=subs.add_parser("capture");c.add_argument("--scenario",type=Path,required=True)
    c.add_argument("--condition",choices=("baseline","optimized"),required=True)
    c.add_argument("--repetition",type=int,required=True)
    c.add_argument("--workspace",type=Path,required=True)
    c.add_argument("--codex-home",type=Path,required=True)
    c.add_argument("--output",type=Path,required=True)
    c.add_argument("--timeout",type=int,default=240)
    c.add_argument("--codex-bin",default="codex")
    c.add_argument("--profile")
    c.add_argument("--telemetry-workspace",type=Path)
    c.add_argument("--telemetry-app",choices=("blender","web"))
    c.add_argument("--telemetry-task-id")
    p=subs.add_parser("preflight");p.add_argument("--scenario",type=Path,required=True)
    p.add_argument("--condition",choices=("baseline","optimized"),required=True)
    p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--codex-home",type=Path,required=True)
    p.add_argument("--output",type=Path);p.add_argument("--codex-bin",default="codex");p.add_argument("--profile")
    q=subs.add_parser("compare");q.add_argument("records",nargs="+",type=Path)
    q.add_argument("--min-pairs",type=int,default=3)
    q.add_argument("--prices",type=Path);q.add_argument("--output",type=Path)
    args=parser.parse_args(argv)
    try:
        if args.cmd=="audit":
            result=audit_codex(args.codex_home,project_config=args.project_config)
        elif args.cmd=="capture":
            scenario=validate_scenario(json.loads(args.scenario.read_text(encoding="utf-8")))
            result=capture_codex(scenario,condition=args.condition,
                    repetition=args.repetition,workspace=args.workspace,
                    codex_home=args.codex_home,timeout=args.timeout,codex_bin=args.codex_bin,profile=args.profile)
            if args.telemetry_workspace is not None:
                import_provider_record(args.telemetry_workspace, result,
                                       app=args.telemetry_app or _scenario_app(scenario),
                                       task_id=args.telemetry_task_id or scenario["scenario_id"])
        elif args.cmd=="preflight":
            scenario=validate_scenario(json.loads(args.scenario.read_text(encoding="utf-8")))
            result=preflight_codex(scenario,condition=args.condition,workspace=args.workspace,
                                   codex_home=args.codex_home,codex_bin=args.codex_bin,profile=args.profile)
        else:
            rates=json.loads(args.prices.read_text(encoding="utf-8")) if args.prices else None
            result=compare(_read_records(args.records),min_pairs=args.min_pairs,prices=rates)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(json.dumps(result,indent=2,ensure_ascii=False))
        if args.cmd=="compare" and result["state"]=="NOT_CERTIFIED":return 2
        if args.cmd=="preflight" and result["state"]!="READY_FOR_BENCHMARK":return 2
        if args.cmd=="audit" and result["coverage_state"]!="PARTIAL_RTK_AND_MCP_ROUTED":return 2
        return 0
    except (ValueError,OSError,RuntimeError,json.JSONDecodeError) as ex:
        # Never print raw provider stderr or possible secrets.
        print(json.dumps({"state":"NOT_CERTIFIED","reason":_safe_error(ex)}),file=sys.stderr)
        return 2
if __name__=="__main__":raise SystemExit(main())
