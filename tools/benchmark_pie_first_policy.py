"""Deterministic no-LLM PIE-first trace replay for policy safety and call counts."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from pie.retrieval.pie_first_policy import Observation, Decision, evaluate


def run() -> dict[str, Any]:
    scenarios=[
        ("fresh_in_scope", Observation("grep",True,True,True,False)),
        ("fresh_repeat", Observation("read",True,True,True,True)),
        ("stale_source", Observation("read",True,True,False,False)),
        ("outside_project", Observation("grep",False,False,True,False)),
        ("unknown_file", Observation("read",True,False,True,False)),
        ("source_validation", Observation("read",True,True,True,False,explicit_source_read=True)),
        ("editing", Observation("edit",True,True,True,False)),
        ("testing", Observation("test",True,True,True,False)),
        ("glob", Observation("glob",True,True,True,False)),
    ]
    variants={}
    for strict in (False,True):
        results=[]
        for name,obs in scenarios:
            verdict=evaluate(obs,strict=strict)
            results.append({"case":name,"decision":verdict.decision.value,"reason":verdict.reason})
        variants["strict" if strict else "soft"]=results
    raw_actions=sum(o.action in {"read","grep","glob"} for _,o in scenarios)
    # This is only a routing opportunity estimate, NOT agent/tool execution.
    opportunities=sum(evaluate(o).decision is Decision.PIE_FIRST for _,o in scenarios)
    return {
        "schema":"pie_first_navigation_replay_v1","scenarios":len(scenarios),
        "raw_navigation_opportunities":raw_actions,
        "pie_first_redirect_opportunities":opportunities,
        "actual_saved_tool_calls":None,"actual_provider_tokens_saved":None,
        "actual_task_quality_delta":None,
        "variants":variants,
        "disclaimer":"Policy decision replay, not agent behavior. Does not prove token reduction.",
    }


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("benchmark-results/pie-first-policy.json"))
    args=p.parse_args()
    report=run()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
