import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from pie.indexing.indexer import index_project
from pie.graph.relationships import build_relationships
from pie.interfaces.mcp_server import dispatch
from pie.retrieval.evidence_atoms import build_proof_context


class EvidenceAtomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "app.py").write_text(
            "def greet(name):\n"
            "    if not name:\n"
            "        raise ValueError('name required')\n"
            "    return name.strip()\n",
            encoding="utf-8",
        )
        index_project(self.root)
        build_relationships(self.root)

    def test_proof_context_is_compact_and_hash_backed(self):
        result = build_proof_context(
            self.root,
            "greet",
            requirements=["raise", "return"],
            detail="full",
        )
        self.assertEqual(result["schema_version"], "pie-proof-context-v1")
        self.assertEqual(result["index_state"], "CURRENT")
        self.assertTrue(result["coverage"]["complete"])
        self.assertTrue(result["atoms"])
        source = result["sources"][0]
        self.assertEqual(source["path"], "app.py")
        self.assertEqual(source["sha256"], sha256((self.root / "app.py").read_bytes()).hexdigest())
        self.assertLessEqual(result["used_chars"], 4000)
        json.dumps(result, ensure_ascii=False)

    def test_missing_proof_obligation_is_explicit(self):
        result = build_proof_context(self.root, "greet", requirements=["not_present"], detail="full")
        self.assertFalse(result["coverage"]["complete"])
        self.assertEqual(result["coverage"]["missing"], ["not_present"])
        self.assertTrue(result["fallback"]["available"])

    def test_mcp_contract_exposes_proof_context(self):
        tools = dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, self.root)
        names = {item["name"] for item in tools["result"]["tools"]}
        self.assertIn("pie_build_proof_context", names)
        response = dispatch(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "pie_build_proof_context",
                    "arguments": {"query": "greet", "requirements": ["return"]},
                },
            },
            self.root,
        )
        self.assertFalse(response["result"].get("isError", False))
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(payload["coverage"]["ok"])
        self.assertTrue(payload["facts"])


if __name__ == "__main__":
    unittest.main()
