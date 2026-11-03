"""DES-04 regression: import resolution and syntactic direct-call proof.

The old resolver missed relative imports and attribute() call sites. This
fixture checks verified evidence, ambiguity, stdlib shadowing and invalidation
without executing analyzed source or modifying real-repo snapshots.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pie.indexing.indexer import index_project
from pie.interfaces.cli import command_init
from pie.retrieval.evidence import EvidenceError, build_evidence
from pie.retrieval.static_traceability import inspect_static_dependencies
from pie.retrieval.symbols import find_references


class CrossModuleResolutionTests(unittest.TestCase):
    def setUp(self):
        self.workspace = TemporaryDirectory()
        self.root = Path(self.workspace.name)
        self.pkg = self.root / "src" / "samplepkg"
        self.pkg.mkdir(parents=True)
        (self.pkg / "__init__.py").write_text("", encoding="utf-8")
        (self.pkg / "helpers.py").write_text(
            "def helper(value):\n    return value + 1\n", encoding="utf-8")
        (self.pkg / "caller.py").write_text(
            "from .helpers import helper as renamed\n"
            "from . import helpers\n"
            "import samplepkg.helpers as alias\n"
            "def calculate():\n"
            "    one = renamed(1)\n"
            "    two = helpers.helper(2)\n"
            "    three = alias.helper(3)\n"
            "    return one + two + three\n",
            encoding="utf-8")
        command_init(self.root)
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")

    def tearDown(self):
        self.workspace.cleanup()

    def test_cross_file_direct_calls_are_verified(self):
        evidence = build_evidence(self.root, "helper")
        self.assertEqual(evidence["direct_call_count"], 3)
        calls = evidence["direct_call_sites"]
        self.assertEqual({item["line"] for item in calls}, {5, 6, 7})
        self.assertEqual({item["path"] for item in calls}, {"src/samplepkg/caller.py"})
        self.assertTrue(all(item["resolution"] == "verified" for item in calls))
        report = inspect_static_dependencies(self.root, "helper")
        self.assertEqual(report["observed_edge_count"], 3)
        self.assertEqual(report["impact"]["status"], "UNDETERMINED")

    def test_attribute_and_plain_calls_are_distinguished(self):
        references = find_references(self.root, "helper", limit=100)
        calls = [r for r in references["references"] if r["usage_kind"] == "direct_call"]
        self.assertEqual(len(calls), 3)
        self.assertEqual(sum(r["name"] == "helper" for r in calls), 2)
        self.assertEqual(sum(r["name"] == "renamed" for r in calls), 1)

    def test_stdlib_import_does_not_bind_nested_project_module(self):
        (self.pkg / "types.py").write_text(
            "def TracebackType():\n    return 'fake'\n", encoding="utf-8")
        (self.pkg / "std.py").write_text(
            "from types import TracebackType\n"
            "def use():\n"
            "    return TracebackType()\n", encoding="utf-8")
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")
        refs = find_references(self.root, "TracebackType", limit=50)
        self.assertEqual(refs["count"], 0)

    def test_relative_import_reindexed_when_target_changes(self):
        evidence = build_evidence(self.root, "helper")
        self.assertEqual(evidence["direct_call_count"], 3)
        (self.pkg / "helpers.py").write_text(
            "def replacement(value):\n    return value\n", encoding="utf-8")
        with self.assertRaisesRegex(EvidenceError, "STALE_PROJECT"):
            build_evidence(self.root, "helper")
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")
        with self.assertRaises(EvidenceError):
            build_evidence(self.root, "helper")

    def test_relative_consumer_reference_is_invalidated_after_reindex(self):
        # A prior verified reference must not survive a changed import target.
        self.assertEqual(build_evidence(self.root, "helper")["direct_call_count"], 3)
        (self.pkg / "helpers.py").write_text(
            "def replacement(value):\n    return value\n", encoding="utf-8")
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")
        from pie.storage.database import connect
        connection = connect(self.root / ".pie" / "index.sqlite3")
        try:
            rows = connection.execute(
                "SELECT name, resolution, target_binding_key FROM usages u "
                "JOIN files f ON f.id=u.file_id "
                "WHERE f.path=? AND u.line IN (5,6,7) AND u.name IN ('renamed','helper')",
                ("src/samplepkg/caller.py",),
            ).fetchall()
            self.assertGreaterEqual(len(rows), 3)
            self.assertTrue(all(row["resolution"] != "verified" for row in rows))
            self.assertTrue(all(row["target_binding_key"] is None for row in rows))
        finally:
            connection.close()

    def test_name_collision_fails_closed(self):
        (self.pkg / "other.py").write_text(
            "def helper(value):\n    return value\n", encoding="utf-8")
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")
        with self.assertRaisesRegex(EvidenceError, "AMBIGUOUS"):
            build_evidence(self.root, "helper")


if __name__ == "__main__":
    unittest.main()
