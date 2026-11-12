"""Regression: repeated qualified names in one file are distinct definitions."""
import tempfile
import unittest
from pathlib import Path

from pie.indexing.indexer import index_project
from pie.interfaces.mcp_context import MCPContextEngine


class DuplicateSymbolIdentityTests(unittest.TestCase):
    def test_same_file_redefinition_is_ambiguous(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "shader.py").write_text(
                "def make_material():\n    return 1\n\ndef make_material():\n    return 2\n",
                encoding="utf-8",
            )
            index_project(root)
            with MCPContextEngine(root) as engine:
                response = engine.query("make_material", mode="navigation")
            self.assertEqual(response["lookup_status"], "AMBIGUOUS")
            self.assertEqual(response["exact_match_count"], 2)


if __name__ == "__main__":
    unittest.main()
