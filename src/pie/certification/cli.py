"""Operator CLI for read-only Codex usage capture, comparison and routing audit."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from pie.certification.live_codex import _read_records,capture_codex,compare,validate_scenario,preflight_codex
from pie.certification.coverage import audit_codex

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
    p=subs.add_parser("preflight");p.add_argument("--scenario",type=Path,required=True)
    p.add_argument("--condition",choices=("baseline","optimized"),required=True)
    p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--codex-home",type=Path,required=True)
    p.add_argument("--output",type=Path);p.add_argument("--codex-bin",default="codex")
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
                    codex_home=args.codex_home,timeout=args.timeout,codex_bin=args.codex_bin)
        elif args.cmd=="preflight":
            scenario=validate_scenario(json.loads(args.scenario.read_text(encoding="utf-8")))
            result=preflight_codex(scenario,condition=args.condition,workspace=args.workspace,
                                   codex_home=args.codex_home,codex_bin=args.codex_bin)
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
        print(json.dumps({"state":"NOT_CERTIFIED","reason":type(ex).__name__}),file=sys.stderr)
        return 2
if __name__=="__main__":raise SystemExit(main())
