"""Regression checks for cloud benchmark serialization and experiment integrity."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"src"))
from cloud_pie_benchmark import LAB, QUESTIONS, compact_evidence, curated_context, source_slice


class CloudBenchmarkTests(unittest.TestCase):
    def test_compact_deduplicates_and_preserves_provenance(self):
        item={"path":"pkg/module.py","start_line":2,"end_line":3,"kind":"function","content":"def f():\n    return 1"}
        report={"context_state":"CURRENT","evidence":[item,item],"relationships":[{"metadata":"do_not_send"}]}
        result=compact_evidence(report)
        self.assertEqual(result.count("def f():"),1)
        self.assertIn("pkg/module.py:2-3",result)
        self.assertNotIn("do_not_send",result)
    def test_compact_refuses_stale_or_incomplete(self):
        for state in ("STALE","PARTIAL","UNINDEXED"):
            with self.subTest(state=state):
                with self.assertRaises(RuntimeError):
                    compact_evidence({"context_state":state,"evidence":[]})
    def test_curated_reference_is_grounded(self):
        self.assertIn("range(config.MAX_RETRIES + 1)",curated_context("MAX_RETRIES"))
        self.assertIn("test_rollback_on_failure",curated_context("release"))
        self.assertIn("self.inventory.reserve",curated_context("charge_with_retry"))
    def test_lab_code_is_syntactically_valid(self):
        import ast
        for path,code in LAB.items():
            with self.subTest(path=path): ast.parse(code)
    def test_three_scenarios_remain_distinct(self):
        self.assertEqual(len(QUESTIONS),3)
        self.assertEqual(len(set(QUESTIONS.values())),3)

if __name__=="__main__":
    unittest.main()
