"""Reproducible local PIE context latency measurement; no model calls.

Do not compare these timings with end-to-end LLM latency.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pie.indexing.indexer import index_project
from pie.retrieval.intelligence import smart_context

def measure(root: Path, queries: list[str], repeats: int = 5, max_chars: int = 12000):
    root = root.resolve()
    start = time.perf_counter()
    indexed = index_project(root)
    index_seconds = time.perf_counter() - start
    if indexed["index_state"] != "CURRENT":
        raise RuntimeError("Incomplete PIE index; no valid benchmark")
    results=[]
    for query in queries:
        elapsed=[]
        counts=[]
        for _ in range(repeats):
            t0=time.perf_counter()
            result=smart_context(root,query,max_chars=max_chars)
            elapsed.append(time.perf_counter()-t0)
            counts.append(len(result["evidence"]))
            if result["context_state"] not in ("CURRENT","PARTIAL"):
                raise RuntimeError("Stale evidence; no valid benchmark")
        results.append({"query":query,"median_seconds":round(statistics.median(elapsed),6),
                        "p95_seconds":round(sorted(elapsed)[max(0,int(.95*len(elapsed))-1)],6),
                        "max_seconds":round(max(elapsed),6),"matches":counts[-1]})
    return {"root":str(root),"source_files":indexed["files"],
            "warm_index_seconds":round(index_seconds,6),"query_samples":results,
            "scope":"Local retrieval only; not LLM inference or agent end-to-end timing"}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",default=".")
    p.add_argument("--repeats",type=int,default=5)
    p.add_argument("--output",default="pie-local-latency.json")
    p.add_argument("--max-chars",type=int,default=12000)
    args=p.parse_args()
    if not 1 <= args.repeats <= 100:
        p.error("repeats out of range")
    result=measure(Path(args.root),["cache state","verify source files","find references","update local index"],
                   args.repeats,args.max_chars)
    Path(args.output).write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))
