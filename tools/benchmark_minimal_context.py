"""A/B: unchanged PIE/RTK vs minimal sufficient source candidate set.

Experimental selector uses only ranked, hash-checked PIE evidence (no gold or
case-specific source lists). The independent gold is consulted only for scoring.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from cloud_pie_benchmark import (LAB, QUESTIONS, ANSWER_KEYS, SYSTEM, call, evaluation_prompt,
                                 semantic_grade, synthetic_modules)
from pie.indexing.indexer import index_project
from pie.graph.relationships import build_relationships
from pie_causal_selector import build_causal_context
from rtk_style_context import compact_source_evidence
from pie_runtime_verifier import observe_case


def minimal_evidence(report:dict[str,Any], *, functions:int=3, tests:int=1) -> dict[str,Any]:
    """Retain ranked source-backed definitions, top functions and top tests.

    All selected snippets are complete (never sliced); no gold answers or
    task-specific source filename lists guide selection.
    """
    if report.get("context_state")!="CURRENT" or report.get("omitted"):
        raise ValueError("Minimal selector requires complete CURRENT source evidence")
    if not 1<=functions<=9 or not 0<=tests<=2:
        raise ValueError("invalid per-kind cap")
    chosen=[]
    counts={"function":0,"behavioral_test":0}
    for item in report["evidence"]:
        kind=item["kind"]
        if kind=="definition":
            chosen.append(item)
        elif kind=="function" and counts[kind]<functions:
            chosen.append(item)
            counts[kind]+=1
        elif kind=="behavioral_test" and counts[kind]<tests:
            chosen.append(item)
            counts[kind]+=1
    return {**report,"evidence":chosen,"omitted":[],
            "context_state":"CURRENT",
            "selection":"ranked_complete_snippets_v1",
            "dropped_existing_candidates":len(report["evidence"])-len(chosen)}


def bench(args:argparse.Namespace) -> dict[str,Any]:
    if args.max_calls!=len(args.cases.split(","))*2*args.repeats:
        raise ValueError("Call budget must match the exact number of paired requests")
    if not (1<=args.max_calls<=12 and 1<=args.repeats<=3 and 0<=args.scale_modules<=150):
        raise ValueError("invalid experiment limits")
    cases=args.cases.split(",")
    if len(set(cases))!=len(cases) or not cases or any(c not in QUESTIONS for c in cases):
        raise ValueError("invalid/duplicate cases")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        for path,source in list(LAB.items())+list(synthetic_modules(args.scale_modules)):
            dest=root/path;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(source,encoding="utf-8")
        check=subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-q"],
                             cwd=root,env={**os.environ,"PYTHONPATH":str(root)},
                             capture_output=True,text=True,timeout=35,check=False)
        if check.returncode: raise RuntimeError("Fixture regression failed")
        idx=index_project(root)
        if idx.get("index_state")!="CURRENT": raise RuntimeError("Index not CURRENT")
        build_relationships(root)
        observed={q:observe_case(root,q) for q in cases}
        if any(observed[q]!=ANSWER_KEYS[q] for q in cases):
            raise RuntimeError("Independent executable gold mismatch")
        contexts={}
        audits={}
        for q in cases:
            source=build_causal_context(root,q,max_chars=12000)
            if source["context_state"]!="CURRENT" or source["omitted"]:
                raise RuntimeError("PIE source evidence is not fully current")
            small=minimal_evidence(source,functions=args.functions,tests=args.tests)
            standard=compact_source_evidence(source,max_chars=12000)
            compact=compact_source_evidence(small,max_chars=12000)
            if standard["state"]!="CURRENT" or compact["state"]!="CURRENT":
                raise RuntimeError("Partial payload detected")
            contexts[q]={"pie_rtk":standard["content"],"pie_minimal":compact["content"]}
            audits[q]={"original_candidates":len(source["evidence"]),
                       "minimal_candidates":len(small["evidence"]),
                       "removed_candidates":small["dropped_existing_candidates"],
                       "original_chars":len(standard["content"]),
                       "minimal_chars":len(compact["content"]),
                       "full_sha256":hashlib.sha256(standard["content"].encode()).hexdigest(),
                       "minimal_sha256":hashlib.sha256(compact["content"].encode()).hexdigest(),
                       "minimal_source_ranges":[[x["path"],x["start_line"],x["end_line"]] for x in small["evidence"]]}
            if compact["content"]==standard["content"]:
                raise RuntimeError(f"No context reduction for case {q}")
        (out/"audit.json").write_text(json.dumps({"model":args.model,"cases":cases,
            "mode_definitions":{"pie_rtk":"existing unchanged RTK context",
                                "pie_minimal":"ranked PIE evidence with capped functions/tests"},
            "audit":audits},indent=2,ensure_ascii=False),encoding="utf-8")
        if args.dry_run:
            result={"status":"DRY_RUN_PASSED","audits":audits,"api_calls":0}
            print(json.dumps(result,ensure_ascii=False));return result
        url=os.getenv("PIE_API_BASE_URL","").rstrip("/")
        # cloud_pie_benchmark.call appends /v1/chat/completions.
        # Accept configured base URLs ending in /v1 without doubling that prefix.
        if url.endswith("/v1"):
            url=url[:-3]
        key=os.getenv("PIE_API_KEY","")
        if not url.startswith("https://") or not key: raise RuntimeError("Missing HTTPS tunnel or 9Router inference key")
        jobs=[]
        for repetition in range(args.repeats):
            randomized=list(cases)
            random.Random(371+repetition).shuffle(randomized)
            for q in randomized:
                pair=["pie_rtk","pie_minimal"]
                random.Random(711+repetition+len(q)).shuffle(pair)
                jobs.extend((repetition,q,mode) for mode in pair)
        results=[]
        for i,(rep,q,mode) in enumerate(jobs,1):
            context=contexts[q][mode]
            prompt="Pergunta: "+evaluation_prompt(q)+"\n\nCódigo e evidências:\n"+context
            reply=call(url,key,args.model,prompt,args.max_tokens)
            row={"case":q,"repeat":rep,"mode":mode,"context_chars":len(context),
                 "context_hash":hashlib.sha256(context.encode()).hexdigest(),**reply}
            if reply["ok"]:
                row["semantic_grade"]=semantic_grade(q,reply["answer"])
                del row["answer"]  # don't publish model content in workflow artifacts
            results.append(row)
            (out/"results.json").write_text(json.dumps({"model":args.model,"results":results},indent=2,ensure_ascii=False),encoding="utf-8")
            print(f"{i}/{len(jobs)} {q} {mode} {'OK' if reply['ok'] else 'FAIL'} {reply['seconds']}s",flush=True)
            if not reply["ok"]:
                break
            if i<len(jobs):time.sleep(args.cooldown)
        summary={}
        for mode in ("pie_rtk","pie_minimal"):
            vals=[r for r in results if r["mode"]==mode and r["ok"]]
            counts=[v.get("usage",{}) for v in vals]
            complete=bool(vals) and all(type(u.get("prompt_tokens")) is int and
                type(u.get("completion_tokens")) is int and
                u.get("total_tokens")==u["prompt_tokens"]+u["completion_tokens"] for u in counts)
            summary[mode]={"calls":len(vals),"input_tokens":sum(u["prompt_tokens"] for u in counts) if complete else None,
                           "output_tokens":sum(u["completion_tokens"] for u in counts) if complete else None,
                           "total_tokens":sum(u["total_tokens"] for u in counts) if complete else None,
                           "correct_fields":sum(r["semantic_grade"]["passed"] for r in vals),
                           "graded_fields":sum(r["semantic_grade"]["total"] for r in vals),
                           "full_answers_correct":sum(r["semantic_grade"]["passed"]==r["semantic_grade"]["total"] for r in vals),
                           "median_latency_seconds":statistics.median(r["seconds"] for r in vals) if vals else None}
        paired=len(results)==len(jobs) and all(r["ok"] for r in results)
        # Combos may fall back to different providers. Compare only when the
        # effective model is reported for every request and is identical.
        actual_models=sorted({r["actual_model"] for r in results
                              if r.get("ok") and isinstance(r.get("actual_model"),str)
                              and r["actual_model"].strip()})
        model_identity_complete=(paired and len(actual_models)==1 and
                                 all(isinstance(r.get("actual_model"),str)
                                     and r["actual_model"]==actual_models[0] for r in results))
        b=summary["pie_rtk"];m=summary["pie_minimal"]
        comparable=paired and model_identity_complete and b["total_tokens"] is not None and m["total_tokens"] is not None and b["calls"]==m["calls"]
        report={"model":args.model,"effective_models":actual_models,
                "model_identity_complete":model_identity_complete,
                "model_mismatch_or_unknown":paired and not model_identity_complete,
                "cases":cases,"paired":paired,
                "provider_usage_complete":comparable,"summary":summary,
                "saved_tokens":b["total_tokens"]-m["total_tokens"] if comparable else None,
                "total_reduction_percent":round(100*(b["total_tokens"]-m["total_tokens"])/b["total_tokens"],3) if comparable and b["total_tokens"] else None,
                "quality_nondegraded":m["correct_fields"]>=b["correct_fields"] if paired else None,
                "certification_warning":"Field grade of tiny synthetic fixture; no general accuracy certification",
                "architecture_changed":False}
        (out/"summary.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
        print("SUMMARY",json.dumps(report,ensure_ascii=False),flush=True)
        if not paired or not comparable: raise SystemExit(1)
        return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",default="pie-benchmark-fallback")
    p.add_argument("--cases",default="MAX_RETRIES,release")
    p.add_argument("--repeats",type=int,default=1)
    p.add_argument("--max-calls",type=int,default=4)
    p.add_argument("--max-tokens",type=int,default=768)
    p.add_argument("--cooldown",type=float,default=10)
    p.add_argument("--scale-modules",type=int,default=0)
    p.add_argument("--functions",type=int,default=3)
    p.add_argument("--tests",type=int,default=1)
    p.add_argument("--out",default="benchmark-results/minimal-context")
    p.add_argument("--dry-run",action="store_true")
    args=p.parse_args()
    if args.cooldown<10: p.error("At least 10 seconds cooldown")
    bench(args)


if __name__=="__main__":
    main()
