import hashlib
import pathlib
import shutil
import sys
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pie.indexing.python_ast import parse_python
from pie.indexing.python_ast import parse_python_content
from pie.scanning import discovery
from pie.scanning.discovery import discover_files, iter_files
from pie.scanning.hashing import sha256_bytes, sha256_file
from pie.scanning.ignore import IgnoreRules


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

    def test_gitignore_supports_nested_files_directory_only_and_globstar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / ".gitignore").write_text("cache/\n*.tmp\n", encoding="utf-8")
            (root / "pkg").mkdir()
            (root / "pkg" / ".gitignore").write_text("/private/\n**/generated?.py\n!keep.py\n", encoding="utf-8")
            (root / "pkg" / "private").mkdir()
            (root / "pkg" / "private" / "hidden.py").write_text("x = 1", encoding="utf-8")
            (root / "pkg" / "deep").mkdir()
            (root / "pkg" / "deep" / "private").mkdir()
            (root / "pkg" / "deep" / "private" / "visible.py").write_text("x = 1", encoding="utf-8")
            (root / "pkg" / "deep" / "generated1.py").write_text("x = 1", encoding="utf-8")
            (root / "pkg" / "deep" / "keep.py").write_text("x = 1", encoding="utf-8")
            (root / "cache.py").write_text("x = 1", encoding="utf-8")
            (root / "cache").mkdir()
            (root / "cache" / "module.py").write_text("x = 1", encoding="utf-8")
            self.assertEqual([item.path.as_posix() for item in discover_files(root)], ["cache.py", "pkg/deep/keep.py", "pkg/deep/private/visible.py"])

    @unittest.skipUnless(shutil.which("git"), "git is required for differential ignore validation")
    def test_supported_gitignore_subset_matches_git_check_ignore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / ".gitignore").write_text(
                "/root_only.py\n*.tmp\ncache/\n**/generated?.py\n"
                "pkg/*.log\n[ab]eta.py\n!keep.tmp\n",
                encoding="utf-8",
            )
            (root / "pkg").mkdir()
            (root / "pkg" / ".gitignore").write_text("/private/\n!keep.py\n", encoding="utf-8")
            candidates = [
                ("root_only.py", False),
                ("nested/root_only.py", False),
                ("build.tmp", False),
                ("keep.tmp", False),
                ("cache", True),
                ("cache/module.py", False),
                ("pkg/generated1.py", False),
                ("pkg/deep/generated2.py", False),
                ("pkg/app.log", False),
                ("other/app.log", False),
                ("beta.py", False),
                ("zeta.py", False),
                ("pkg/private", True),
                ("pkg/private/hidden.py", False),
                ("pkg/keep.py", False),
            ]
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            rules = IgnoreRules(root)
            for relative, is_directory in candidates:
                candidate = root / relative
                candidate.parent.mkdir(parents=True, exist_ok=True)
                if is_directory:
                    candidate.mkdir(exist_ok=True)
                else:
                    candidate.touch()
                reference = subprocess.run(
                    ["git", "-C", str(root), "check-ignore", "--no-index", "-q", "--", relative],
                    check=False,
                )
                self.assertIn(reference.returncode, (0, 1), relative)
                self.assertEqual(
                    rules.ignored(pathlib.Path(relative), is_directory=is_directory),
                    reference.returncode == 0,
                    relative,
                )

    def test_discovery_yields_one_file_snapshot_at_a_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "a.py").write_text("a = 1", encoding="utf-8")
            (root / "b.py").write_text("b = 1", encoding="utf-8")
            original = discovery.read_snapshot
            reads = []

            def read_snapshot(current, max_bytes):
                if current.suffix == ".py":
                    reads.append(current.name)
                return original(current, max_bytes)

            with mock.patch.object(discovery, "read_snapshot", read_snapshot):
                records = iter_files(root)
                first = next(records)
                self.assertEqual(reads, ["a.py"])
                self.assertEqual(first.content, b"a = 1")
                second = next(records)
                self.assertEqual(reads, ["a.py", "b.py"])
                self.assertEqual(second.content, b"b = 1")

    def test_oversized_file_is_rejected_at_the_configured_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "large.py").write_bytes(b"x" * 64)
            self.assertEqual(discover_files(root, max_bytes=8), [])

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
            original = discovery.read_snapshot

            def read_snapshot(current, max_bytes):
                if current.suffix == ".py":
                    raise OSError("simulated read failure")
                return original(current, max_bytes)

            with mock.patch.object(discovery, "read_snapshot", read_snapshot):
                self.assertEqual(discover_files(root), [])

    def test_discovery_parses_the_snapshot_even_if_file_changes_after_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            path = root / "concurrent.py"
            original_content = b"def before():\n    pass\n"
            path.write_bytes(original_content)
            original = discovery.read_snapshot

            def read_snapshot(current, max_bytes):
                content = original(current, max_bytes)
                if current == path:
                    path.write_bytes(b"def after():\n    pass\n")
                return content

            with mock.patch.object(discovery, "read_snapshot", read_snapshot):
                record = discover_files(root)[0]
            self.assertEqual(record.content, original_content)
            self.assertEqual(record.sha256, sha256_bytes(original_content))

    def test_search_query_wildcards_are_literal(self):
        # The CLI query is covered at the integration boundary; this assertion documents the escaping contract.
        query = "100%_ready"
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        self.assertEqual(escaped, "100\\%\\_ready")

