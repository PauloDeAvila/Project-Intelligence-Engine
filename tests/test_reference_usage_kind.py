"""Deterministic, offline regression tests for reverse-reference classification."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pie.indexing.indexer import index_project
from pie.interfaces.cli import command_init
from pie.retrieval.symbols import find_references


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


if __name__ == "__main__":
    unittest.main()
