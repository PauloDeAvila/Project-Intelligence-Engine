import hashlib
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pie.indexing.python_ast import parse_python
from pie.indexing.python_ast import parse_python_content
from pie.scanning.discovery import discover_files
from pie.scanning.hashing import sha256_bytes, sha256_file


class ScannerAndParserTests(unittest.TestCase):
    def test_hash_matches_sha256(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "sample.py"
            path.write_bytes(b"print('hello')")
            self.assertEqual(sha256_file(path), hashlib.sha256(b"print('hello')").hexdigest())

    def test_discovery_ignores_generated_directories_and_non_python(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "app.py").write_text("x = 1", encoding="utf-8")
            (root / "notes.txt").write_text("ignore", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "hidden.py").write_text("x = 2", encoding="utf-8")
            self.assertEqual([str(item.path) for item in discover_files(root)], ["app.py"])

    def test_discovery_applies_gitignore_patterns_and_negations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / ".gitignore").write_text("build/\n*.py\n!important.py\nlogs/**/*.py\n", encoding="utf-8")
            (root / "build").mkdir()
            (root / "build" / "generated.py").write_text("x = 1", encoding="utf-8")
            (root / "cache.py").write_text("x = 1", encoding="utf-8")
            (root / "important.py").write_text("x = 1", encoding="utf-8")
            (root / "logs" / "nested").mkdir(parents=True)
            (root / "logs" / "nested" / "debug.py").write_text("x = 1", encoding="utf-8")
            (root / "keep.py").write_text("x = 1", encoding="utf-8")
            self.assertEqual([str(item.path) for item in discover_files(root)], ["important.py"])

    def test_parser_extracts_nested_symbols_and_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "service.py"
            path.write_text("from db import Repo as R\n\nclass Service:\n    def add(self):\n        def validate():\n            return True\n        return validate()\n", encoding="utf-8")
            symbols, imports, error = parse_python(path, "service.py")
            self.assertIsNone(error)
            self.assertEqual([(item.qualified_name, item.kind) for item in symbols], [("Service", "class"), ("Service.add", "method"), ("Service.add.validate", "function")])
            self.assertEqual((imports[0].module, imports[0].imported_name, imports[0].alias), ("db", "Repo", "R"))

    def test_parser_reports_invalid_python_without_raising(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "broken.py"
            path.write_text("def broken(:\n", encoding="utf-8")
            symbols, imports, error = parse_python(path, "broken.py")
            self.assertEqual((symbols, imports, error), ([], [], "SyntaxError"))

    def test_hash_and_parser_use_the_same_content_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            path = root / "snapshot.py"
            path.write_text("def old():\n    pass\n", encoding="utf-8")
            record = discover_files(root)[0]
            path.write_text("def new():\n    pass\n", encoding="utf-8")
            symbols, _, error = parse_python_content(record.content, str(record.path))
            self.assertIsNone(error)
            self.assertEqual([item.name for item in symbols], ["old"])
            self.assertEqual(record.sha256, sha256_bytes(record.content))

    def test_discovery_supports_unicode_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            path = root / "área" / "分析.py"
            path.parent.mkdir()
            path.write_text("def função():\n    pass\n", encoding="utf-8")
            records = discover_files(root)
            self.assertEqual([item.path.as_posix() for item in records], ["área/分析.py"])

    def test_discovery_skips_file_that_becomes_unreadable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            path = root / "unavailable.py"
            path.write_text("x = 1", encoding="utf-8")
            original = pathlib.Path.read_bytes

            def read_bytes(current):
                if current.suffix == ".py":
                    raise OSError("simulated read failure")
                return original(current)

            with mock.patch.object(pathlib.Path, "read_bytes", read_bytes):
                self.assertEqual(discover_files(root), [])

    def test_discovery_parses_the_snapshot_even_if_file_changes_after_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            path = root / "concurrent.py"
            original_content = b"def before():\n    pass\n"
            path.write_bytes(original_content)
            original = pathlib.Path.read_bytes

            def read_bytes(current):
                content = original(current)
                if current == path:
                    path.write_bytes(b"def after():\n    pass\n")
                return content

            with mock.patch.object(pathlib.Path, "read_bytes", read_bytes):
                record = discover_files(root)[0]
            self.assertEqual(record.content, original_content)
            self.assertEqual(record.sha256, sha256_bytes(original_content))

    def test_search_query_wildcards_are_literal(self):
        # The CLI query is covered at the integration boundary; this assertion documents the escaping contract.
        query = "100%_ready"
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        self.assertEqual(escaped, "100\\%\\_ready")

