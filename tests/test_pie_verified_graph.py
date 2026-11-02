"""Verified graph unit and integration regression tests."""
import tempfile
import unittest
from pathlib import Path

from pie.graph.verified import VerifiedGraph
from pie.indexing.indexer import index_project
from pie.retrieval.warm import WarmContextService
from pie.storage.database import connect


class GraphTests(unittest.TestCase):
    def test_verified_and_unresolved_edges(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"provider.py").write_text(
                'def execute(x):\n    """Execute a verified provider operation."""\n    return x\n')
            (root/"consumer.py").write_text(
                'from provider import execute\n'
                'def handler(x):\n    """Handle operation using imported provider."""\n'
                '    return execute(x)\n')
            (root/"other.py").write_text(
                'def execute(x):\n    """Unrelated function sharing an identical name."""\n    return x\n')
            index_project(root)
            with WarmContextService(root) as service:
                graph=service._verified_graph
                edges=graph.consumers("provider.py","execute")["edges"]
                self.assertTrue(any(e["source_path"]=="consumer.py" for e in edges),edges)
                self.assertEqual(graph.consumers("other.py","execute")["edges"],[])
                pack=service.task_pack("Execute a verified provider operation")
                self.assertIn("provider.py::execute",pack["verified_consumers"])
                self.assertTrue(all(e["resolution"]=="verified" for e in edges))
                with self.assertRaises(ValueError):
                    graph.consumers("provider.py","execute",depth=6)
                (root/"provider.py").unlink()
                service.refresh()
                self.assertFalse(service._verified_graph.consumers("provider.py","execute")["edges"])

    def test_graph_bounded_cycles(self):
        from pie.graph.verified import Edge
        edges=[
            Edge("a.py","a","b.py","b","k1",2,1).__dict__,
            Edge("b.py","b","a.py","a","k2",2,1).__dict__,
        ]
        graph=VerifiedGraph(edges)
        result=graph.consumers("a.py","a",depth=5,limit=10)
        self.assertLessEqual(len(result["edges"]),2)
        self.assertEqual(len(graph.dependencies("a.py","a")["edges"]),1)


if __name__=="__main__":
    unittest.main()
