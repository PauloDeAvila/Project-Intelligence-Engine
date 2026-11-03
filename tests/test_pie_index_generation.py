"""Background index refresh and explicit consistency modes."""
import tempfile
import time
import unittest
from pathlib import Path

from pie.indexing.indexer import index_project
from pie.retrieval.warm import WarmContextService


class GenerationGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "cache.py"
        self.source.write_text(
            'def refresh_cache(x):\n    """Refresh cached snapshots for callers."""\n    return x\n',
            encoding="utf8")
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")

    def test_strict_cache_hit_after_refresh(self):
        with WarmContextService(self.root, background_interval=None) as svc:
            initial = svc.query("refresh_cache")
            self.assertFalse(initial["cache_hit"])
            hit = svc.query("refresh_cache")
            self.assertTrue(hit["cache_hit"])
            self.assertTrue(hit["result"]["evidence"])

    def test_eventual_detects_edit_of_cached_evidence(self):
        with WarmContextService(self.root, background_interval=None) as svc:
            svc.query("refresh_cache")
            self.source.write_text(
                'def purge_cache(x):\n    """Remove obsolete cached snapshots safely."""\n    return x\n',
                encoding="utf8")
            answer = svc.query("refresh_cache")
            self.assertFalse(answer["cache_hit"])
            self.assertFalse(any(e["symbol"]=="refresh_cache" for e in answer["result"]["evidence"]))

    def test_background_worker_reindexes_new_responsibilities(self):
        with WarmContextService(self.root, background_interval=0.1) as svc:
            added = self.root / "payments.py"
            added.write_text(
                'def reconcile_invoices(x):\n    """Reconcile payments with unpaid invoices."""\n    return x\n',
                encoding="utf8")
            deadline = time.monotonic() + 7
            while time.monotonic() < deadline:
                answer = svc.query("reconcile_invoices")
                if any(e["path"]=="payments.py" for e in answer["result"]["evidence"]):
                    break
                time.sleep(0.1)
            else:
                self.fail("background indexing did not discover new file")

    def test_strict_and_invalid_mode(self):
        with WarmContextService(self.root) as svc:
            self.assertIn("result", svc.query("refresh_cache"))
            with self.assertRaises(TypeError):
                svc.query("refresh_cache", consistency="unsafe")


if __name__ == "__main__":
    unittest.main()
