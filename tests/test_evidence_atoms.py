import json
import sqlite3
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from pie.indexing.indexer import index_project
from pie.graph.relationships import build_relationships
from pie.interfaces.mcp_server import dispatch
from pie.retrieval.evidence_atoms import _source_hash_matches, build_proof_context


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
        self.assertEqual(result["delivery"]["status"], "FALLBACK_REQUIRED")
        self.assertFalse(result["delivery"]["can_deliver_atoms"])

    def test_unverified_source_hash_marks_facts_unverified(self):
        result = build_proof_context(self.root, "greet", requirements=["return"])
        self.assertTrue(result["structured_facts"])
        self.assertTrue(all(fact["verified"] for fact in result["structured_facts"]))

        # Tamper with the source bytes after indexing: the claimed sha256 no
        # longer matches the file contents, so no atom may claim verification.
        # The persistent cache replays the flags computed at build time, so the
        # check must run against a fresh build (different detail => new key).
        (self.root / "app.py").write_bytes(
            (self.root / "app.py").read_bytes() + b"\n# appended\n"
        )
        tampered = build_proof_context(
            self.root, "greet", requirements=["return"], detail="full"
        )
        # Tampering without reindexing makes the index stale, so the pipeline may
        # legitimately select no sources at all. Either way, no fact may report
        # verification: the bytes on disk no longer match the claimed hash.
        self.assertFalse(any(fact["verified"] for fact in tampered["structured_facts"]))
        self.assertFalse(
            any(source["verified"] for source in tampered["sources"] if "verified" in source)
        )

    def test_source_hash_check_fails_closed(self):
        # A source path escaping the root must never verify, and missing
        # inputs (no root, empty path, short hash) must not be trusted.
        self.assertFalse(
            _source_hash_matches(
                self.root, {"path": "../outside.py", "sha256": sha256(b"payload").hexdigest()}
            )
        )
        self.assertFalse(_source_hash_matches(self.root, {"path": "", "sha256": "0" * 64}))
        self.assertFalse(_source_hash_matches(self.root, {"path": "app.py", "sha256": "abc"}))
        self.assertFalse(_source_hash_matches(None, {"path": "app.py", "sha256": "0" * 64}))
        self.assertFalse(
            _source_hash_matches(self.root, {"path": "missing.py", "sha256": "0" * 64})
        )

    def test_persistent_cache_reuses_and_invalidates_verified_evidence(self):
        first = build_proof_context(self.root, "greet", requirements=["return"])
        second = build_proof_context(self.root, "greet", requirements=["return"])
        self.assertTrue(first["cache"]["persistent"])
        self.assertFalse(first["cache"]["hit"])
        self.assertTrue(second["cache"]["hit"])
        self.assertTrue(second["structured_facts"][0]["verified"])

        (self.root / "app.py").write_text(
            "def greet(name):\n    return name.upper()\n",
            encoding="utf-8",
        )
        index_project(self.root)
        third = build_proof_context(self.root, "greet", requirements=["return"])
        self.assertFalse(third["cache"]["hit"])
        self.assertNotEqual(first["sources"][0][1], third["sources"][0][1])

    def test_adaptive_selection_deduplicates_clauses(self):
        result = build_proof_context(
            self.root,
            "greet",
            requirements=["def greet", "return", "return"],
        )
        self.assertEqual(result["selection"]["strategy"], "adaptive_clause_set_cover")
        self.assertLessEqual(result["selection"]["selected_count"], result["selection"]["candidate_count"])
        self.assertEqual(result["delivery"]["status"], "READY")
        self.assertTrue(result["structured_facts"])

    def test_different_questions_share_the_same_atom_catalog(self):
        build_proof_context(self.root, "greet", requirements=["raise"])
        second = build_proof_context(self.root, "greet", requirements=["return"])
        self.assertTrue(second["coverage"]["ok"])
        self.assertEqual(second["delivery"]["status"], "READY")
        connection = sqlite3.connect(self.root / ".pie" / "evidence_atoms.sqlite3")
        try:
            atom_ranges = connection.execute("SELECT COUNT(*) FROM atom_cache").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(atom_ranges, 1)

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
