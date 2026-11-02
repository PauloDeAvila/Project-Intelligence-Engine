"""Scalable synthetic PIE latency experiment.

These timings apply to indexed retrieval, not model responses. The corpus is
synthetic and cannot substitute for unseen real-repository coding benchmarks.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import statistics
import tempfile
import time
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from pie.indexing.indexer import index_project
from pie.retrieval.intelligence import smart_context

def run(files: int, repeats: int, max_chars: int) -> dict[str, object]:
    if files < 1 or files > 20000 or repeats < 1 or repeats > 100:
        raise ValueError("files/repeats outside safe range")
    with tempfile.TemporaryDirectory(prefix="pie-scale-") as temp:
        root=Path(temp)
        pkg=root/"scaled"
        pkg.mkdir()
        for i in range(files):
            (pkg/f"module_{i:05d}.py").write_text(
                f'def process_task_{i:05d}(value):\n'
                f'    """Process a uniquely named responsibility module number {i:05d}; '
                f'manage caching updates and verify inputs."""\n'
                '    if value is None:\n'
                '        raise ValueError("missing")\n'
                '    return value + 1\n',
                encoding="utf-8")
        begin=time.perf_counter()
        indexed=index_project(root)
        cold_index=time.perf_counter()-begin
        if indexed["index_state"]!="CURRENT":
            raise RuntimeError("index incomplete")
        start=time.perf_counter()
        warm=index_project(root)
        warm_index=time.perf_counter()-start
        if warm["changed_files"] or warm["removed_files"]:
            raise RuntimeError("unchanged sources were unexpectedly rebuilt")
        queries=["process_task_00000",
                 f"process_task_{files//2:05d}",
                 f"process_task_{files-1:05d}",
                 "manage caching updates and verify inputs"]
        rows=[]
        for q in queries:
            for budget in (12000,max_chars):
                elapsed=[]; returned=0; size=0
                for _ in range(repeats):
                    t=time.perf_counter()
                    output=smart_context(root,q,max_chars=budget,include_body=True)
                    elapsed.append(time.perf_counter()-t)
                    if output["context_state"] not in ("CURRENT","PARTIAL"):
                        raise RuntimeError("retrieval stale")
                    returned=len(output["evidence"])
                    size=len(json.dumps(output,ensure_ascii=False))
                    if size>budget:
                        raise RuntimeError("context budget exceeded")
                rows.append({"query":q,"budget_chars":budget,
                             "median_seconds":round(statistics.median(elapsed),6),
                             "worst_seconds":round(max(elapsed),6),
                             "returned":returned,"serialized_chars":size})
        return {"files":files,"symbols":indexed["symbols"],
                "cold_index_seconds":round(cold_index,6),
                "warm_index_seconds":round(warm_index,6),
                "queries":rows,"scope":"Synthetic Python corpus; local only",
                "machine":"GitHub Actions runner if executed there"}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--files",type=int,default=1000)
    p.add_argument("--repeats",type=int,default=5)
    p.add_argument("--max-chars",type=int,default=200000)
    p.add_argument("--output",default="pie-context-scale.json")
    a=p.parse_args()
    result=run(a.files,a.repeats,a.max_chars)
    Path(a.output).write_text(json.dumps(result,indent=2),encoding="utf8")
    print(json.dumps(result,indent=2))
