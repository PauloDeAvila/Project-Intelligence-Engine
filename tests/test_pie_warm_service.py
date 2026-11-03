"""Regression tests for the persistent PIE service."""
import io
import json
from pathlib import Path
import tempfile
import unittest

from pie.indexing.indexer import index_project
from pie.retrieval.warm import WarmContextService, serve


class WarmServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "cache_ops.py").write_text(
            'def invalidate_cache(key):\n    """Discard stale cache entries after updates."""\n    return key\n',
            encoding="utf8")
        index_project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_repeated_query_and_invalidation(self):
        with WarmContextService(self.root) as service:
            first = service.query("Discard stale cache entries")
            self.assertFalse(first["cache_hit"])
            second = service.query("Discard stale cache entries")
            self.assertTrue(second["cache_hit"])
            self.assertEqual(first["result"]["evidence"], second["result"]["evidence"])
            (self.root / "cache_ops.py").write_text(
                'def purge_cache(key):\n    """Purge obsolete cached values safely."""\n    return key\n',
                encoding="utf8")
            third = service.query("Discard stale cache entries")
            self.assertFalse(third["cache_hit"])
            self.assertNotEqual(first["result"]["evidence"], third["result"]["evidence"])

    def test_json_lines_protocol(self):
        stream = io.StringIO('{"method":"ping"}\n{"method":"query","query":"cache"}\n{"method":"bad"}\n')
        output = io.StringIO()
        serve(self.root, stream, output)
        events = [json.loads(x) for x in output.getvalue().splitlines()]
        self.assertTrue(events[0]["ok"])
        self.assertTrue(events[1]["ok"])
        self.assertFalse(events[2]["ok"])


if __name__ == "__main__":
    unittest.main()
