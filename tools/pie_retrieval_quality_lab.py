"""Deterministic retrieval quality smoke lab with no-match and recall@K.

This evaluates source retrieval only. It is not a model coding benchmark.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from pie.indexing.indexer import index_project
from pie.retrieval.intelligence import smart_context

FIXTURES={
    "cache_ops.py":'def invalidate_cache(key):\n    """Discard stale cache entries after updates."""\n    return key\n',
    "billing.py":'def settle_invoice(amount):\n    """Reconcile invoice payments and outstanding balances."""\n    return amount\n',
    "network.py":'def retry_request(url):\n    """Retry failed HTTP requests after network errors."""\n    return url\n',
    "render.py":'def draw_scene(scene):\n    """Render the current scene to the display surface."""\n    return scene\n',
}
QUESTIONS=[
    ("Which function discards stale cache entries?","cache_ops.py"),
    ("Where are invoice payments reconciled?","billing.py"),
    ("Which function retries HTTP requests?","network.py"),
    ("What renders a scene to the display?","render.py"),
    ("Where is the Kubernetes admission controller deployed?",None),
]

def run():
    with tempfile.TemporaryDirectory(prefix="pie-quality-") as directory:
        root=Path(directory)
        for path,content in FIXTURES.items():
            (root/path).write_text(content,encoding="utf8")
        index_project(root)
        results=[]
        for query,expected in QUESTIONS:
            started=time.perf_counter()
            response=smart_context(root,query,max_chars=12000,limit=3)
            latency=time.perf_counter()-started
            paths=[item["path"] for item in response["evidence"]]
            hit=(expected in paths) if expected else not paths
            results.append({"query":query,"expected":expected,"top3":paths,
                            "hit":hit,"latency_ms":round(latency*1000,3)})
        report={"total":len(results),"passed":sum(x["hit"] for x in results),
                "scope":"Curated synthetic retrieval questions; no LLM calls",
                "results":results}
        print(json.dumps(report,indent=2))
        return 0 if report["passed"]==report["total"] else 1

if __name__=="__main__":
    raise SystemExit(run())
