"""Deterministic, offline regression tests for reverse-reference classification."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pie.indexing.indexer import index_project
from pie.interfaces.cli import command_init
from pie.retrieval.symbols import find_references, find_definitions
from pie.interfaces.mcp_server import dispatch


class ReferenceUsageKindTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "geometry.py").write_text(
            "def analyze_mesh(mesh, matrix, config):\n"
            "    return mesh\n", encoding="utf-8"
        )
        (self.root / "tests.py").write_text(
            "from geometry import analyze_mesh\n"
            "def direct():\n"
            "    return analyze_mesh(1, 2, 3)\n"
            "def assigned():\n"
            "    fn = analyze_mesh\n"
            "    return fn(1, 2, 3)\n"
            "def passed():\n"
            "    return consume(analyze_mesh)\n", encoding="utf-8"
        )
        command_init(self.root)
        indexed = index_project(self.root)
        self.assertEqual(indexed["index_state"], "CURRENT")

    def tearDown(self):
        self.temp.cleanup()

    def test_direct_call_alias_value_and_argument_are_distinct(self):
        payload = find_references(self.root, "analyze_mesh")
        self.assertEqual(payload["state"], "CURRENT")
        refs = {r["line"]: r for r in payload["references"]
                if r["path"] == "tests.py"}
        self.assertEqual(refs[3]["usage_kind"], "direct_call")
        self.assertEqual(refs[5]["usage_kind"], "value_reference")
        self.assertEqual(refs[8]["usage_kind"], "argument_pass")
        self.assertEqual({r["resolution"] for r in refs.values()}, {"verified"})
        self.assertTrue(all(r["target"] for r in refs.values()))

    def test_modified_source_does_not_return_verified_stale_evidence(self):
        (self.root / "tests.py").write_text("from geometry import analyze_mesh\n", encoding="utf-8")
        payload = find_references(self.root, "analyze_mesh")
        self.assertEqual(payload["state"], "STALE")
        self.assertEqual(payload["references"], [])
        self.assertTrue(payload.get("excluded_stale"))


    def test_exact_definition_is_located(self):
        result = find_definitions(self.root, "analyze_mesh")
        self.assertEqual(result["state"], "CURRENT")
        self.assertTrue(any(d["path"] == "geometry.py" for d in result["definitions"]))

    def test_negative_lookup_does_not_invent_references(self):
        result = find_references(self.root, "nonexistent_name")
        self.assertEqual(result["references"], [])

    def test_alias_invocation_is_not_mislabeled_direct(self):
        result = find_references(self.root, "analyze_mesh")
        occurrences = [r for r in result["references"] if r["path"] == "tests.py"]
        self.assertEqual(sum(r["usage_kind"] == "direct_call" for r in occurrences), 1)

    def test_import_resolution_preserves_original_target(self):
        result = find_references(self.root, "analyze_mesh")
        occurrences = [r for r in result["references"] if r["path"] == "tests.py"]
        self.assertTrue(all("geometry.py" in r["target"] for r in occurrences))

    def test_missing_required_mcp_argument_is_rejected(self):
        response = dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": "pie_find_references", "arguments": {}}}, self.root)
        self.assertTrue(response["result"]["isError"])

    def test_mcp_rejects_unknown_arguments(self):
        response = dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                             "params": {"name": "pie_project_status",
                                        "arguments": {"query": "not-valid"}}}, self.root)
        self.assertTrue(response["result"]["isError"])

    def test_mcp_status_accepts_empty_arguments(self):
        response = dispatch({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                             "params": {"name": "pie_project_status", "arguments": {}}}, self.root)
        self.assertNotIn("error", response)
        self.assertFalse(response["result"].get("isError", False))

    def test_changed_definition_invalidates_reference_proof(self):
        (self.root / "geometry.py").write_text("def analyze_mesh(mesh):\n    return mesh\n", encoding="utf-8")
        result = find_references(self.root, "analyze_mesh")
        self.assertEqual(result["state"], "STALE")
        self.assertFalse(result["references"])

    def test_reindex_recovers_current_evidence(self):
        (self.root / "tests.py").write_text(
            "from geometry import analyze_mesh\ndef run():\n    return analyze_mesh(1,2,3)\n",
            encoding="utf-8")
        indexed = index_project(self.root)
        self.assertEqual(indexed["index_state"], "CURRENT")
        result = find_references(self.root, "analyze_mesh")
        self.assertEqual(result["state"], "CURRENT")
        self.assertTrue(any(r["usage_kind"] == "direct_call" for r in result["references"]))



if __name__ == "__main__":
    unittest.main()
