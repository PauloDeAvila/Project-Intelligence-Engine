"""Predictive prefetch correctness and boundedness."""
import tempfile
import unittest
from pathlib import Path
from pie.indexing.indexer import index_project
from pie.retrieval.predictive import predict_adjacent_queries
from pie.retrieval.warm import WarmContextService

class PredictiveTests(unittest.TestCase):
    def test_selection_requires_verified_source(self):
        pack={"responsibilities":[{"verified_consumers":[
            {"consumer":"handler","source_path":"consumer.py","resolution":"verified"},
            {"consumer":"handler","source_path":"consumer.py","resolution":"verified"},
            {"consumer":None,"source_path":"x.py"}]}]}
        self.assertEqual(predict_adjacent_queries(pack),["handler consumer.py"])
        self.assertEqual(predict_adjacent_queries({"responsibilities":[]}),[])
        with self.assertRaises(ValueError):
            predict_adjacent_queries(pack,limit=21)

    def test_predictive_rechecks_changed_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/"provider.py").write_text(
                'def persist_value(x):\n    """Persist a value in durable storage."""\n    return x\n',encoding="utf8")
            (root/"consumer.py").write_text(
                'from provider import persist_value\ndef handler(x):\n    return persist_value(x)\n',encoding="utf8")
            self.assertEqual(index_project(root)["index_state"],"CURRENT")
            with WarmContextService(root) as svc:
                result=svc.predictive_prefetch("Persist a value in durable storage")
                self.assertEqual(result["consistency"],"strict")
                self.assertLessEqual(result["prepared"],6)
                self.assertEqual(result["prepared"],len(result["predicted"]))
                (root/"provider.py").write_text("def unrelated(x):\n    return x\n",encoding="utf8")
                new=svc.predictive_prefetch("Persist a value in durable storage")
                self.assertEqual(new["prepared"],0)

if __name__=="__main__":
    unittest.main()
