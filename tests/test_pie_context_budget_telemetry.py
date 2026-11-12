"""Regression: returned source-character telemetry matches the returned snippets."""
import tempfile
import unittest
from pathlib import Path

from pie.indexing.indexer import index_project
from pie.retrieval.context import build_context


class ContextBudgetTelemetryTests(unittest.TestCase):
    def test_source_characters_match_returned_ranges(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "module.py").write_text(
                "\n".join(f"def sample_{i}():\n    return '{'x' * 250}'" for i in range(12)),
                encoding="utf-8",
            )
            index_project(root)
            result = build_context(root, "sample_", max_chars=900, limit=12)
            self.assertEqual(result["source_characters"], sum(
                len(item["content"]) for item in result["source_ranges"]))


if __name__ == "__main__":
    unittest.main()
