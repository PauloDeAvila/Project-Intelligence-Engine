"""Reproducible paired comparisons for PIE benchmarks.

No cherry-picked single median: match each treatment with the same
question/repetition. Report uncertainty, measured usage and correctness.
"""
from __future__ import annotations
import json
from pathlib import Path
import random
import statistics
import sys

def _median(values):
    return statistics.median(values) if values else None

def paired_summary(data:dict, baseline:str, candidate:str, seed:int=20261102)->dict:
    records=data["results"]
    lookup={(r["repeat"],r["case"],r["mode"]):r for r in records if r.get("ok")}
    keys=sorted((rep,case) for rep,case,mode in lookup if mode==baseline)
    pairs=[]
    for rep,case in keys:
        a=lookup.get((rep,case,baseline))
        b=lookup.get((rep,case,candidate))
        if not a or not b:continue
        a_tokens=a.get("usage",{}).get("prompt_tokens")
        b_tokens=b.get("usage",{}).get("prompt_tokens")
        pairs.append({
            "repeat":rep,"case":case,
            "latency_delta_s":round(b["seconds"]-a["seconds"],6),
            "baseline_seconds":a["seconds"],"candidate_seconds":b["seconds"],
            "prompt_tokens_saved":a_tokens-b_tokens if isinstance(a_tokens,int) and isinstance(b_tokens,int) else None,
            "baseline_correct":a.get("semantic_grade",{}).get("passed",0),
            "candidate_correct":b.get("semantic_grade",{}).get("passed",0),
            "baseline_certified":a.get("certification",{}).get("approved"),
            "candidate_certified":b.get("certification",{}).get("approved")
        })
    diffs=[row["latency_delta_s"] for row in pairs]
    savings=[row["prompt_tokens_saved"] for row in pairs if row["prompt_tokens_saved"] is not None]
    ci=None
    if diffs:
        rng=random.Random(seed)
        bootstrap=[statistics.median(rng.choices(diffs,k=len(diffs))) for _ in range(1500)]
        bootstrap.sort()
        ci=[round(bootstrap[int(.025*(len(bootstrap)-1))],4),
            round(bootstrap[int(.975*(len(bootstrap)-1))],4)]
    return {
        "baseline":baseline,"candidate":candidate,
        "pairs":len(pairs),
        "median_paired_latency_delta_s":round(_median(diffs),4) if diffs else None,
        "median_paired_delta_95pct_bootstrap_ci_s":ci,
        "fraction_candidate_faster":round(sum(d<0 for d in diffs)/len(diffs),4) if diffs else None,
        "total_measured_prompt_tokens_saved":sum(savings),
        "fraction_candidate_certified":(
            round(sum(x["candidate_certified"] is True for x in pairs)/len(pairs),4) if pairs else None),
        "fraction_baseline_certified":(
            round(sum(x["baseline_certified"] is True for x in pairs)/len(pairs),4) if pairs else None),
        "interpretation":"Small correlated synthetic scenarios; bootstrap measures paired-run variation, not project generalization",
        "paired_observations":pairs,
    }

def main():
    source=Path(sys.argv[1] if len(sys.argv)>1 else "benchmark-results/results.json")
    data=json.loads(source.read_text(encoding="utf-8"))
    modes=sorted({r["mode"] for r in data["results"]})
    candidate_baseline=("baseline_observed" if "baseline_observed" in modes else "baseline")
    reports={m:paired_summary(data,candidate_baseline,m) for m in modes if m!=candidate_baseline}
    dest=source.with_name("paired-statistics.json")
    dest.write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding="utf-8")
    for m,r in reports.items():
        print(f"PAIRED {m}: n={r['pairs']} median_delta={r['median_paired_latency_delta_s']}s "
              f"CI={r['median_paired_delta_95pct_bootstrap_ci_s']} saved_tokens={r['total_measured_prompt_tokens_saved']}")

if __name__=="__main__":
    main()
