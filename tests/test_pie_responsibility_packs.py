"""Contract tests for source-grounded responsibility packs."""
import json
import tempfile
import unittest
from pathlib import Path
from pie.indexing.indexer import index_project
from pie.retrieval.warm import WarmContextService

class ResponsibilityPacksTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/"provider.py").write_text(
            'def persist_value(x):\n    """Persist a value in durable storage."""\n    return x\n',encoding="utf8")
        (self.root/"consumer.py").write_text(
            'from provider import persist_value\ndef save(x):\n    return persist_value(x)\n',encoding="utf8")
        self.assertEqual(index_project(self.root)["index_state"],"CURRENT")

    def test_budget_provenance_and_graph(self):
        with WarmContextService(self.root) as service:
            pack=service.task_pack("Persist a value in durable storage",max_chars=4000)
            self.assertEqual(pack["context_state"],"CURRENT")
            self.assertLessEqual(len(json.dumps(pack,ensure_ascii=False,separators=(",",":"))),4000)
            target=next(x for x in pack["responsibilities"] if x["symbol"]=="persist_value")
            self.assertEqual(target["path"],"provider.py")
            self.assertEqual(len(target["sha256"]),64)
            self.assertIn("def persist_value",target["source"])
            self.assertTrue(all(x["resolution"]=="verified" for x in target["verified_consumers"]))

    def test_fails_closed_for_stale_snapshot(self):
        with WarmContextService(self.root) as service:
            first=service.task_pack("persist_value")
            (self.root/"provider.py").write_text('def renamed(x):\n    return x\n',encoding="utf8")
            updated=service.task_pack("persist_value")
            self.assertFalse(any(x["symbol"]=="persist_value" for x in updated["responsibilities"]))
            self.assertNotEqual(first["responsibilities"],updated["responsibilities"])

    def test_small_budget_never_exceeds_limit(self):
        with WarmContextService(self.root) as service:
            pack=service.task_pack("persist_value",max_chars=500)
            self.assertLessEqual(len(json.dumps(pack,ensure_ascii=False,separators=(",",":"))),500)
            with self.assertRaises(ValueError):
                service.task_pack("persist_value",max_chars=499)
