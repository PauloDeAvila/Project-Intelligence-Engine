"""Offline regression for Trail-inspired rank and diff blast."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from pie.retrieval.graph_rank import pagerank, rank_context
from pie.retrieval.diff_blast import parse_hunks, blast_diff
from pie.interfaces.tool_gateway import execute_gateway
from pie.indexing.indexer import index_project

def git(root,*args):
    return subprocess.run(["git","-C",str(root),*args],capture_output=True,text=True,check=True)

class GraphRankBlastTests(unittest.TestCase):
    def test_pagerank_deterministic_and_disconnected(self):
        nodes=["a","b","c"]
        x=pagerank(nodes,[("a","b")],{"a":3,"c":1})
        self.assertEqual(x,pagerank(reversed(nodes),[("a","b")],{"c":1,"a":3}))
        self.assertGreater(x["b"],0)
        self.assertAlmostEqual(sum(x.values()),1,places=9)
        self.assertEqual(pagerank(nodes,[],{}),{"a":0.0,"b":0.0,"c":0.0})
        with self.assertRaises(ValueError):
            pagerank(nodes,[],{"a":float("nan")})

    def test_hunks_addition_deletion_and_invalid(self):
        text="diff --git a/foo.py b/foo.py\n+++ b/foo.py\n@@ -3,2 +3,4 @@\n@@ -10 +12,0 @@\n"
        self.assertEqual(parse_hunks(text),{"foo.py":[(3,6),(12,12)]})
        with self.assertRaises(ValueError):
            parse_hunks("+++ b/../outside.py\n@@ -1 +1 @@")

    def test_offline_benchmark_contract(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
        from benchmark_trail_pie import run
        report=run(2)
        self.assertEqual(report["external_inference_calls"],0)
        self.assertIsNone(report["provider_tokens"])
        self.assertEqual(len(report["ranking"]),4)
        self.assertTrue(all(r["runs"]==2 for r in report["ranking"]))
        self.assertIn("process_order",report["blast"]["changed_symbols"])
        self.assertNotIn("unrelated",report["blast"]["changed_symbols"])
        self.assertGreater(report["blast"]["coarse_file_level_consumers"],report["blast"]["diff_symbol_consumers"])
        self.assertGreater(report["blast"]["precision_refinement"],0)

    def test_end_to_end_local_repository(self):
        if not shutil.which("git"): self.skipTest("git unavailable")
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"core.py").write_text(
                "def process(value):\n    return value + 1\n\n"
                "def unrelated(value):\n    return value * 7\n",encoding="utf-8")
            (root/"app.py").write_text(
                "from core import process\n"
                "def run():\n    return process(5)\n",encoding="utf-8")
            git(root,"init")
            git(root,"-c","user.name=PIE","-c","user.email=pie@example.invalid",
                "add",".")
            git(root,"-c","user.name=PIE","-c","user.email=pie@example.invalid",
                "commit","-m","fixture")
            index_project(root)
            ranked=rank_context(root,"process",limit=3)
            self.assertEqual(ranked["context_state"],"CURRENT")
            self.assertTrue(any(e["symbol"]=="process" for e in ranked["evidence"]))
            self.assertEqual(ranked["method"],"verified_ppr_v1")
            routed=execute_gateway(root,"graph_rank",{"query":"process"},max_chars=12000)
            self.assertEqual(routed["operation"],"graph_rank")
            self.assertEqual(json.loads(routed["result"])["method"],"verified_ppr_v1")
            (root/"core.py").write_text(
                "def process(value):\n    return value + 2\n\n"
                "def unrelated(value):\n    return value * 7\n",encoding="utf-8")
            with self.assertRaises(ValueError):
                blast_diff(root)
            index_project(root)
            report=blast_diff(root)
            routed=execute_gateway(root,"blast_diff",{"depth":1},max_chars=16000)
            self.assertEqual(json.loads(routed["result"])["method"],"git_diff_verified_blast_v1")
            self.assertIn("core.py",report["changed_files"])
            self.assertTrue(any(s["symbol"]=="process" for s in report["seeds"]))
            self.assertFalse(any(s["symbol"]=="unrelated" for s in report["seeds"]))
            self.assertNotIn("unrelated",json.dumps(report["potential_consumers"]))

if __name__=="__main__":
    unittest.main()
