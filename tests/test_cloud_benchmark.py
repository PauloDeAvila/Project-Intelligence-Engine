"""Regression checks for cloud benchmark serialization and experiment integrity."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"src"))
from cloud_pie_benchmark import LAB, QUESTIONS, ANSWER_KEYS, compact_evidence, compact_flow_evidence, curated_context, semantic_grade, evaluation_prompt, source_slice
from pie_causal_selector import build_causal_context
from pie.indexing.indexer import index_project
from pie.graph.relationships import build_relationships


class CloudBenchmarkTests(unittest.TestCase):
    def test_compact_deduplicates_and_preserves_provenance(self):
        item={"path":"pkg/module.py","start_line":2,"end_line":3,"kind":"function","content":"def f():\n    return 1"}
        report={"context_state":"CURRENT","evidence":[item,item],"relationships":[{"metadata":"do_not_send"}]}
        result=compact_evidence(report)
        self.assertEqual(result.count("def f():"),1)
        self.assertIn("pkg/module.py:2-3",result)
        self.assertNotIn("do_not_send",result)
    def test_compact_refuses_stale_or_incomplete(self):
        for state in ("STALE","UNINDEXED"):
            with self.subTest(state=state):
                with self.assertRaises(RuntimeError):
                    compact_evidence({"context_state":state,"evidence":[]})
    def test_partial_context_still_requires_evidence_audit(self):
        # PARTIAL alone means an optional candidate may have been omitted.
        # The benchmark's mandatory-evidence checks decide if it is usable.
        source={"context_state":"PARTIAL","evidence":[{"path":"p.py","start_line":1,
            "end_line":1,"kind":"function","content":"def f(): pass"}]}
        self.assertIn("def f(): pass",compact_evidence(source))
    def test_flow_annotation_preserves_code_and_extracts_handler(self):
        report={"context_state":"CURRENT","evidence":[{"path":"service.py","start_line":10,
            "end_line":15,"kind":"function","symbol":"OrderService.checkout",
            "content":"    def checkout(self):\n        try:\n            return charge_with_retry()\n        except Exception:\n            self.inventory.release()\n            raise"}]}
        result=compact_flow_evidence(report)
        self.assertIn("return charge_with_retry()",result)
        self.assertIn("TRY_RETURN",result)
        self.assertIn("HANDLER Exception",result)
        self.assertIn("ATTRIBUTE_CALL",result)
        self.assertIn("AttributeError",result)
    def test_causal_retrieval_includes_module_assignment(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for name,source in LAB.items():
                p=root/name
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(source,encoding="utf-8")
            self.assertEqual(index_project(root)["index_state"],"CURRENT")
            build_relationships(root)
            ctx=build_causal_context(root,"MAX_RETRIES")
            self.assertEqual(ctx["context_state"],"CURRENT")
            evidence=compact_evidence(ctx)
            self.assertIn("MAX_RETRIES = 3",evidence)
            self.assertIn("range(config.MAX_RETRIES + 1)",evidence)
    def test_curated_reference_is_grounded(self):
        self.assertIn("range(config.MAX_RETRIES + 1)",curated_context("MAX_RETRIES"))
        self.assertIn("test_rollback_on_failure",curated_context("release"))
        self.assertIn("self.inventory.reserve",curated_context("charge_with_retry"))
    def test_lab_code_is_syntactically_valid(self):
        import ast
        for path,code in LAB.items():
            with self.subTest(path=path): ast.parse(code)
    def test_semantic_grading_is_deterministic(self):
        import json
        for scenario, expected in ANSWER_KEYS.items():
            with self.subTest(scenario=scenario):
                self.assertEqual(semantic_grade(scenario,json.dumps(expected))["passed"],4)
                self.assertEqual(semantic_grade(scenario,"not json")["passed"],0)
                wrong=dict(expected)
                key=next(iter(wrong))
                wrong[key]=None
                self.assertEqual(semantic_grade(scenario,json.dumps(wrong))["passed"],3)
                self.assertIn("JSON",evaluation_prompt(scenario))
    def test_three_scenarios_remain_distinct(self):
        self.assertEqual(len(QUESTIONS),3)
        self.assertEqual(len(set(QUESTIONS.values())),3)

if __name__=="__main__":
    unittest.main()
