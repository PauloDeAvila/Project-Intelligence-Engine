"""Contract tests for DES-04 facts vs causal claims.

All projects are created in temporary directories and indexed separately.
No production repo or model service is touched.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pie.indexing.indexer import index_project
from pie.interfaces.cli import command_init
from pie.retrieval.evidence import EvidenceError
from pie.retrieval.static_traceability import inspect_static_dependencies


class StaticTraceabilityContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "logic.py").write_text(
            "def compute_total(amount, tax):\n"
            "    return amount + tax\n", encoding="utf-8")
        (self.root / "service.py").write_text(
            "from logic import compute_total\n"
            "def checkout():\n"
            "    return compute_total(10, 2)\n", encoding="utf-8")
        command_init(self.root)
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")

    def tearDown(self):
        self.temp.cleanup()

    def test_multi_file_edge_has_source_proof_not_runtime_certification(self):
        report = inspect_static_dependencies(self.root, "compute_total")
        self.assertEqual(report["status"], "STATIC_EVIDENCE_ONLY")
        self.assertEqual(report["verified_direct_call_count"], 1)
        self.assertEqual(report["observed_edge_count"], 1)
        edge = report["edges"][0]
        self.assertEqual(edge["source"]["path"], "service.py")
        self.assertEqual(edge["source"]["line"], 3)
        self.assertEqual(edge["target"]["path"], "logic.py")
        self.assertEqual(edge["target"]["line"], 1)
        self.assertEqual(edge["kind"], "verified_static_direct_call")
        self.assertEqual(edge["proof"]["resolution"], "verified")
        self.assertEqual(report["impact"]["status"], "UNDETERMINED")
        self.assertFalse(report["impact"]["breaking_change_proven"])
        self.assertEqual(report["impact"]["causal_claims_certified"], [])

    def test_new_unindexed_caller_refuses_global_coverage(self):
        (self.root / "third_party.py").write_text(
            "from logic import compute_total\n"
            "compute_total(3, 4)\n", encoding="utf-8")
        with self.assertRaisesRegex(EvidenceError, "STALE_PROJECT"):
            inspect_static_dependencies(self.root, "compute_total")

    def test_modified_target_refuses_stale_claim(self):
        (self.root / "logic.py").write_text(
            "def compute_total(amount, tax, factor):\n"
            "    return (amount + tax) * factor\n", encoding="utf-8")
        with self.assertRaisesRegex(EvidenceError, "STALE_PROJECT"):
            inspect_static_dependencies(self.root, "compute_total")

    def test_duplicate_symbol_is_ambiguous(self):
        (self.root / "other_logic.py").write_text(
            "def compute_total(x, y):\n"
            "    return x - y\n", encoding="utf-8")
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")
        with self.assertRaisesRegex(EvidenceError, "AMBIGUOUS"):
            inspect_static_dependencies(self.root, "compute_total")

    def test_dynamic_call_never_becomes_breakage_proof(self):
        (self.root / "dynamic.py").write_text(
            "import logic\n"
            "def dynamic_dispatch(name):\n"
            "    return getattr(logic, name)(10, 2)\n", encoding="utf-8")
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")
        report = inspect_static_dependencies(self.root, "compute_total")
        self.assertEqual(report["impact"]["status"], "UNDETERMINED")
        self.assertFalse(report["impact"]["runtime_effect_proven"])
        self.assertIn("dynamic dispatch", report["coverage"]["not_verified"])


if __name__ == "__main__":
    unittest.main()
