"""Regression tests for PIE context intelligence, impact and persistent glossary."""
import json
from pathlib import Path
import tempfile
import unittest

from pie.indexing.indexer import index_project
from pie.retrieval.intelligence import smart_context, impact
from pie.retrieval.glossary import remember, recall


class ContextIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "cache_manager.py").write_text(
            'def refresh_cache(value):\n'
            '    """Refresh the cached value after an update."""\n'
            '    return value + 1\n',
            encoding="utf-8")
        (self.root / "consumer.py").write_text(
            'from cache_manager import refresh_cache\n'
            'def run():\n'
            '    return refresh_cache(2)\n',
            encoding="utf-8")
        indexed = index_project(self.root)
        self.assertEqual(indexed["index_state"], "CURRENT")

    def test_responsibility_query_returns_source_provenance(self):
        result = smart_context(self.root, "Which function refreshes cached values?")
        self.assertEqual(result["context_state"], "CURRENT")
        self.assertTrue(any(e["symbol"] == "refresh_cache" and
                            e["path"] == "cache_manager.py" for e in result["evidence"]))

    def test_context_budget_is_strict(self):
        result = smart_context(self.root, "refresh cache", max_chars=500)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), 500)

    def test_changed_source_never_returned(self):
        (self.root / "cache_manager.py").write_text("def refresh_cache():\n    pass\n",encoding="utf-8")
        result = smart_context(self.root, "refresh cache")
        self.assertEqual(result["context_state"], "STALE")
        self.assertFalse(any(e["path"] == "cache_manager.py" for e in result["evidence"]))

    def test_glossary_is_hash_bound_to_evidence(self):
        remember(self.root, "cache", "Cache refresh responsibility", "cache_manager.py")
        self.assertEqual(recall(self.root, "cache")["entries"][0]["state"], "CURRENT")
        (self.root / "cache_manager.py").write_text("print('changed')\n",encoding="utf-8")
        entry = recall(self.root, "cache")["entries"][0]
        self.assertEqual(entry["state"], "STALE")
        self.assertIsNone(entry["description"])

    def test_glossary_rejects_escape(self):
        with self.assertRaises(ValueError):
            remember(self.root, "secret", "outside", "../outside.txt")

    def test_incremental_docs_rebuild_without_reparsing_unchanged_files(self):
        unchanged=index_project(self.root)
        self.assertEqual(unchanged["changed_files"], [])
        self.assertEqual(unchanged["removed_files"], [])
        (self.root / "cache_manager.py").write_text(
            'def refresh_cache(value):\n'
            '    """Recompute cached snapshots after mutations."""\n'
            '    return value + 3\n', encoding="utf-8")
        updated=index_project(self.root)
        self.assertEqual(updated["changed_files"], ["cache_manager.py"])
        result=smart_context(self.root, "Recompute cached snapshots")
        self.assertEqual(result["context_state"], "CURRENT")
        self.assertTrue(any("Recompute cached snapshots" in e["description"] for e in result["evidence"]))

    def test_auto_glossary_from_indexed_docstrings(self):
        result=recall(self.root,"Refresh the cached")
        self.assertTrue(any(e.get("kind")=="indexed_symbol" and e["state"]=="CURRENT"
                            for e in result["entries"]))

    def test_incremental_deletion_invalidates_docs(self):
        (self.root / "cache_manager.py").unlink()
        updated=index_project(self.root)
        self.assertIn("cache_manager.py",updated["removed_files"])
        result=smart_context(self.root,"refresh_cache")
        self.assertFalse(any(e["path"]=="cache_manager.py" for e in result["evidence"]))

    def test_impact_is_bounded_and_has_provenance(self):
        result=impact(self.root,"refresh_cache")
        self.assertIn("affected_files",result)
        self.assertIn("verified_references",result)


if __name__ == "__main__":
    unittest.main()
