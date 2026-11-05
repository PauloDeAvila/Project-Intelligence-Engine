"""Deterministic offline A/B: lexical vs verified PPR, file-level vs diff-symbol impact."""
import argparse
import json
import statistics
import subprocess
import tempfile
import time
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from pie.indexing.indexer import index_project
from pie.retrieval.intelligence import smart_context
from pie.retrieval.graph_rank import rank_context
from pie.retrieval.diff_blast import blast_diff
from pie.graph.verified import VerifiedGraph
from pie.storage.database import connect

def run(repeats=5):
    if type(repeats) is not int or not 1<=repeats<=30:
        raise ValueError("repeats must be 1..30")
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        (root/"core.py").write_text(
            "def process_order(value):\n    return value + 1\n\n"
            "def process_logs(value):\n    return value * 2\n\n"
            "def unrelated(value):\n    return value / 2\n",encoding="utf-8")
        (root/"service.py").write_text(
            "from core import process_order\n"
            "def checkout():\n    return process_order(3)\n",encoding="utf-8")
        (root/"logger.py").write_text("from core import process_logs\n"+"def report():\n"+"    return process_logs(7)\n",encoding="utf-8")
        (root/"noise.py").write_text(
            "def process_debug(value):\n    return value + 2\n",encoding="utf-8")
        def git(*args):
            subprocess.run(["git","-C",str(root),*args],check=True,capture_output=True,text=True)
        git("init");git("add",".")
        git("-c","user.name=PIE","-c","user.email=pie@example.invalid",
            "commit","-m","benchmark source")
        index_project(root)
        data=[]
        queries=[("process_order","process_order"),("process logs","process_logs")]
        for query,gold in queries:
            for mode,fn in (("lexical",smart_context),("verified_ppr",rank_context)):
                durations=[];hit=[]
                for _ in range(repeats):
                    start=time.perf_counter()
                    got=fn(root,query,limit=3,max_chars=12000,include_body=False) if mode=="lexical" else fn(root,query,limit=3,max_chars=12000)
                    durations.append((time.perf_counter()-start)*1000)
                    hit.append(any(x["symbol"]==gold for x in got["evidence"][:3]))
                data.append({"query":query,"mode":mode,"top3_correct":all(hit),
                             "median_ms":round(statistics.median(durations),3),
                             "runs":repeats,"source_state":got["context_state"]})
        (root/"core.py").write_text(
            "def process_order(value):\n    return value + 4\n\n"
            "def process_logs(value):\n    return value * 2\n\n"
            "def unrelated(value):\n    return value / 2\n",encoding="utf-8")
        index_project(root)
        with connect(root/".pie"/"index.sqlite3") as db:
            g=VerifiedGraph.from_connection(db)
            file_symbols=[r[0] for r in db.execute(
                "SELECT qualified_name FROM symbols s JOIN files f ON s.file_id=f.id WHERE f.path='core.py'")]
        # Naive file-level traversal considers ALL symbols in the changed file.
        coarse={(e["source_path"],e["consumer"],e["source_line"])
                for name in file_symbols
                for e in g.consumers("core.py",name,depth=1)["edges"]}
        start=time.perf_counter()
        precise=blast_diff(root,depth=1)
        blast_ms=round((time.perf_counter()-start)*1000,3)
        fine={(e["consumer_path"],e["consumer"],e["line"])
              for e in precise["potential_consumers"]}
        return {"benchmark":"trail_inspired_pie_offline_v1",
                "external_inference_calls":0,"provider_tokens":None,
                "ranking":data,
                "blast":{"changed_symbols":[s["symbol"] for s in precise["seeds"]],
                         "coarse_file_level_consumers":len(coarse),
                         "diff_symbol_consumers":len(fine),
                         "precision_refinement":len(coarse)-len(fine),
                         "elapsed_ms":blast_ms,"state":precise["state"]},
                "caveat":"Synthetic tiny fixture: top-3 containment and latency do not establish general quality or speed."}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--repeats",type=int,default=5)
    p.add_argument("--out",default="benchmark-results/trail-inspired.json")
    a=p.parse_args()
    result=run(a.repeats)
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
