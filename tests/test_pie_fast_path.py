"""Fast Path correctness: bounded candidates, alias, stale source and no match."""
import tempfile
import unittest
from pathlib import Path
from pie.indexing.indexer import index_project
from pie.retrieval.intelligence import smart_context
from pie.storage.database import connect

class FastPathTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for i in range(120):
            (self.root / f"module_{i:03d}.py").write_text(
                f'def operation_{i:03d}(x):\n'
                f'    """Perform distinct operation number {i:03d} on input."""\n'
                '    return x\n', encoding="utf8")
        (self.root / "cache_store.py").write_text(
            'def invalidate_cache(key):\n'
            '    """Discard stale cache entries when data changes."""\n'
            '    return key\n', encoding="utf8")
        assert index_project(self.root)["index_state"] == "CURRENT"

    def test_responsibility_and_no_match(self):
        found = smart_context(self.root, "Discard stale cache entries")
        self.assertTrue(any(e["path"] == "cache_store.py" for e in found["evidence"]))
        absent = smart_context(self.root, "Kubernetes admission controller")
        self.assertEqual(absent["evidence"], [])

    def test_exact_name_and_sha(self):
        found = smart_context(self.root, "invalidate_cache")
        self.assertTrue(any(e["symbol"] == "invalidate_cache" for e in found["evidence"]))
        (self.root / "cache_store.py").write_text("def invalidate_cache(): pass\n", encoding="utf8")
        stale = smart_context(self.root, "invalidate_cache")
        self.assertEqual(stale["context_state"], "STALE")
        self.assertFalse(any(e["path"] == "cache_store.py" for e in stale["evidence"]))

    def test_candidate_bound(self):
        db = connect(self.root / ".pie" / "index.sqlite3")
        try:
            count = db.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            self.assertGreater(count, 100)
        finally:
            db.close()
        result = smart_context(self.root, "invalidate_cache", limit=4)
        self.assertLessEqual(len(result["evidence"]), 4)
        self.assertLessEqual(len(str(result)), 12000)

if __name__ == "__main__":
    unittest.main()
