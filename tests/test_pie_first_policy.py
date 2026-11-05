"""Safety, routing, and replay regression tests for the opt-in PIE-first policy."""
import sys
import unittest
from pathlib import Path

from pie.retrieval.pie_first_policy import Decision, Observation, evaluate

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from benchmark_pie_first_policy import run


class PIEFirstTests(unittest.TestCase):
    def test_orients_before_first_indexed_raw_read(self):
        for tool in ("read", "grep", "glob"):
            with self.subTest(tool=tool):
                outcome = evaluate(Observation(tool, True, True, True, False))
                self.assertEqual(outcome.decision, Decision.PIE_FIRST)
                self.assertEqual(outcome.next_tool, "pie_query")

    def test_strict_blocks_only_first_read_or_grep(self):
        for tool in ("read", "grep"):
            outcome = evaluate(Observation(tool, True, True, True, False), strict=True)
            self.assertEqual(outcome.decision, Decision.BLOCK_ONCE)
        glob = evaluate(Observation("glob", True, True, True, False), strict=True)
        self.assertEqual(glob.decision, Decision.PIE_FIRST)
        subsequent = evaluate(
            Observation("read", True, True, True, False, first_raw_navigation=False),
            strict=True,
        )
        self.assertEqual(subsequent.decision, Decision.PIE_FIRST)

    def test_never_blocks_stale_unindexed_external_or_validation(self):
        observations = (
            Observation("read", True, True, False, False),
            Observation("grep", False, False, True, False),
            Observation("read", True, False, True, False),
            Observation("read", True, True, True, False, explicit_source_read=True),
            Observation("read", True, True, True, True),
        )
        for observation in observations:
            self.assertEqual(evaluate(observation, strict=True).decision, Decision.ALLOW_RAW)

    def test_edit_tests_and_index_queries_are_unrestricted(self):
        for tool in ("edit", "test", "pie_query"):
            with self.subTest(tool=tool):
                self.assertEqual(
                    evaluate(Observation(tool, True, True, True, False), strict=True).decision,
                    Decision.ALLOW_RAW,
                )

    def test_benchmark_does_not_claim_measured_savings(self):
        output = run()
        self.assertEqual(output["scenarios"], 9)
        self.assertEqual(output["pie_first_redirect_opportunities"], 2)
        self.assertIsNone(output["actual_saved_tool_calls"])
        self.assertIsNone(output["actual_provider_tokens_saved"])
        self.assertIsNone(output["actual_task_quality_delta"])


if __name__ == "__main__":
    unittest.main()
