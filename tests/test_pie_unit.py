import hashlib
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pie.indexing.python_ast import parse_python
from pie.scanning.discovery import discover_files
from pie.scanning.hashing import sha256_file


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

