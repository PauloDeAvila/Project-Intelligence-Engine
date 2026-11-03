"""DES-03 score audit: semantic sufficiency must not imply certification."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "des03_benchmark", BASE / "tools" / "benchmark_dynamic_selection.py"
)
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class GoldPolicyScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = benchmark.load_gold(BASE / "tests" / "test_dynamic_evidence_planner.py")
        cls.policy = benchmark.load_policy(
            BASE / "tests" / "fixtures" / "dynamic_selection_gold_v3.json",
            cls.cases)

    def test_all_case_labels_present(self):
        self.assertEqual(len(self.cases), 30)
        self.assertEqual(len(self.policy), 30)

    def test_case_two_path_alone_is_sufficient_and_exact(self):
        policy = self.policy[2]
        self.assertEqual(policy["required"], ["path"])
        self.assertEqual(policy["optional"], ["line"])
        score = benchmark.score_selection(["path"], policy)
        self.assertTrue(score["semantically_sufficient"])
        self.assertTrue(score["selection_exact"])
        self.assertEqual(score["recall"], 1.0)

    def test_optional_line_is_sufficient_but_not_exact(self):
        score = benchmark.score_selection(["path", "line"], self.policy[2])
        self.assertTrue(score["semantically_sufficient"])
        self.assertFalse(score["selection_exact"])
        self.assertEqual(score["precision"], 1.0)
        self.assertEqual(score["selected_optional"], ["line"])

    def test_forbidden_field_rejects_semantic_sufficiency(self):
        score = benchmark.score_selection(["path", "signature"], self.policy[2])
        self.assertFalse(score["semantically_sufficient"])
        self.assertIn("signature", score["selected_forbidden"])

    def test_missing_required_field_is_insufficient(self):
        score = benchmark.score_selection(["line"], self.policy[2])
        self.assertFalse(score["semantically_sufficient"])
        self.assertEqual(score["missing_mandatory"], ["path"])

    def test_duplicate_field_does_not_count_as_exact(self):
        score = benchmark.score_selection(["path", "path"], self.policy[2])
        self.assertFalse(score["semantically_sufficient"])
        self.assertFalse(score["selection_exact"])

    def test_abstentions_are_distinct_from_positive_sufficiency(self):
        policy = self.policy[21]
        self.assertTrue(policy["abstain"])
        self.assertEqual(policy["required"], [])
        self.assertEqual(policy["optional"], [])
        self.assertFalse(benchmark.score_selection([], policy)["semantically_sufficient"])


if __name__ == "__main__":
    unittest.main()
