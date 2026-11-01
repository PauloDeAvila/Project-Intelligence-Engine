import pathlib
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pie.indexing import indexer
from pie.indexing.indexer import index_project
from pie.interfaces.cli import command_status
from pie.scanning import discovery
from pie.storage.database import connect


class IndexPersistenceTests(unittest.TestCase):
    def test_existing_database_migrates_and_preserves_repeated_symbol_definitions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            database = root / ".pie" / "index.sqlite3"
            database.parent.mkdir()
            connection = sqlite3.connect(database)
            connection.executescript(
                "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
                "CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, "
                "size INTEGER NOT NULL, language TEXT, parse_status TEXT NOT NULL);"
                "CREATE TABLE symbols (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE, "
                "qualified_name TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, start_line INTEGER NOT NULL, "
                "end_line INTEGER NOT NULL, start_col INTEGER NOT NULL, end_col INTEGER NOT NULL, "
                "UNIQUE(file_id, qualified_name, kind));"
                "CREATE TABLE imports (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE, "
                "module TEXT NOT NULL, imported_name TEXT, alias TEXT, line INTEGER NOT NULL);"
                "INSERT INTO files VALUES (1, 'app.py', 'hash', 1, 'python', 'parsed');"
                "INSERT INTO symbols VALUES (1, 1, 'App.value', 'value', 'method', 1, 2, 4, 20);"
                "INSERT INTO metadata VALUES ('root', 'legacy');"
            )
            connection.commit()
            connection.close()

            connection = connect(database)
            try:
                rows = connection.execute(
                    "SELECT qualified_name, start_line FROM symbols ORDER BY start_line"
                ).fetchall()
                self.assertEqual([(row["qualified_name"], row["start_line"]) for row in rows], [("App.value", 1)])
                connection.execute(
                    "INSERT INTO symbols(file_id, qualified_name, name, kind, start_line, end_line, start_col, end_col) "
                    "VALUES (1, 'App.value', 'value', 'method', 5, 6, 4, 20)"
                )
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM symbols").fetchone()[0], 2)
                self.assertEqual(connection.execute("SELECT value FROM metadata WHERE key = 'root'").fetchone()[0], "legacy")
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                connection.close()

    def test_index_preserves_same_qualified_name_at_distinct_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "app.py").write_text(
                "class Value:\n    @property\n    def state(self):\n        return 1\n"
                "    @state.setter\n    def state(self, value):\n        self._state = value\n",
                encoding="utf-8",
            )
            result = index_project(root)
            self.assertEqual((result["files"], result["symbols"], result["index_state"]), (1, 3, "CURRENT"))
            matches = command_status(root)
            self.assertEqual(matches["symbols"], 3)

    def test_index_persists_symbols_and_updates_changed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "app.py"
            source.write_text("class App:\n    pass\n", encoding="utf-8")
            first = index_project(root)
            self.assertEqual((first["files"], first["symbols"]), (1, 1))
            source.write_text("def run():\n    return 1\n", encoding="utf-8")
            second = index_project(root)
            self.assertEqual((second["files"], second["symbols"]), (1, 1))
            connection = connect(root / ".pie" / "index.sqlite3")
            try:
                names = [row[0] for row in connection.execute("SELECT qualified_name FROM symbols")]
                self.assertEqual(names, ["run"])
            finally:
                connection.close()

    def test_index_removes_deleted_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "app.py"
            source.write_text("def run():\n    pass\n", encoding="utf-8")
            index_project(root)
            source.unlink()
            result = index_project(root)
            self.assertEqual((result["files"], result["symbols"]), (0, 0))

    def test_transient_read_failure_preserves_existing_index_until_actual_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "app.py"
            source.write_text("def stable():\n    pass\n", encoding="utf-8")
            index_project(root)
            original = discovery.read_snapshot

            def fail_for_source(path, max_bytes):
                if path == source:
                    raise OSError("temporary sharing violation")
                return original(path, max_bytes)

            with mock.patch.object(discovery, "read_snapshot", fail_for_source):
                failed_scan = index_project(root)
            self.assertEqual((failed_scan["files"], failed_scan["symbols"]), (1, 1))
            self.assertEqual(failed_scan["index_state"], "STALE")
            self.assertEqual(failed_scan["diagnostics"][0]["code"], "file_unreadable")
            self.assertEqual(command_status(root)["index_state"], "STALE")
            connection = connect(root / ".pie" / "index.sqlite3")
            try:
                self.assertEqual(connection.execute("SELECT name FROM symbols").fetchone()[0], "stable")
            finally:
                connection.close()
            source.unlink()
            deleted = index_project(root)
            self.assertEqual((deleted["files"], deleted["symbols"]), (0, 0))
            self.assertEqual(deleted["index_state"], "CURRENT")
            self.assertEqual(deleted["diagnostics"], [])

    def test_new_unreadable_file_is_reported_as_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "new.py"
            source.write_text("def not_indexed():\n    pass\n", encoding="utf-8")
            original = discovery.read_snapshot

            def fail_for_source(path, max_bytes):
                if path == source:
                    raise OSError("temporary access failure")
                return original(path, max_bytes)

            with mock.patch.object(discovery, "read_snapshot", fail_for_source):
                result = index_project(root)
            self.assertEqual((result["files"], result["index_state"]), (0, "PARTIAL"))
            status = command_status(root)
            self.assertEqual(status["index_state"], "PARTIAL")
            self.assertEqual(
                status["diagnostics"],
                [
                    {"code": "file_unreadable", "path": "new.py"},
                    {"code": "files_not_processed", "count": 1},
                ],
            )

    def test_directory_walk_failure_preserves_prior_rows_under_that_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            nested = root / "package"
            nested.mkdir()
            (nested / "module.py").write_text("def retained():\n    pass\n", encoding="utf-8")
            index_project(root)
            original_walk = discovery.os.walk

            def walk_with_unavailable_directory(top, topdown=True, onerror=None):
                for current, directories, filenames in original_walk(top, topdown=topdown, onerror=onerror):
                    if pathlib.Path(current) == root:
                        if onerror:
                            onerror(OSError(13, "temporary directory access failure", str(nested)))
                        directories[:] = [name for name in directories if name != "package"]
                    yield current, directories, filenames

            with mock.patch.object(discovery.os, "walk", walk_with_unavailable_directory):
                during_failure = index_project(root)
            self.assertEqual((during_failure["files"], during_failure["symbols"]), (1, 1))
            self.assertEqual(during_failure["index_state"], "PARTIAL")
            self.assertEqual(during_failure["diagnostics"][-1], {"code": "preserved_stale_files", "count": 1})
            shutil.rmtree(nested)
            after_deletion = index_project(root)
            self.assertEqual((after_deletion["files"], after_deletion["symbols"]), (0, 0))

    def test_failed_index_transaction_is_visible_as_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "app.py"
            source.write_text("def stable():\n    pass\n", encoding="utf-8")
            index_project(root)
            source.write_text("def changed():\n    pass\n", encoding="utf-8")
            with mock.patch.object(indexer, "parse_python_content", side_effect=RuntimeError("parser unavailable")):
                with self.assertRaisesRegex(RuntimeError, "parser unavailable"):
                    index_project(root)
            status = command_status(root)
            self.assertEqual(status["index_state"], "ERROR")
            self.assertEqual(status["diagnostics"][0]["code"], "indexing_failed")
            connection = connect(root / ".pie" / "index.sqlite3")
            try:
                self.assertEqual(connection.execute("SELECT name FROM symbols").fetchone()[0], "stable")
            finally:
                connection.close()
            recovered = index_project(root)
            self.assertEqual(recovered["index_state"], "CURRENT")
            self.assertEqual(recovered["diagnostics"], [])

    def test_oversized_file_does_not_silently_delete_prior_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "app.py"
            source.write_text("def stable():\n    pass\n", encoding="utf-8")
            index_project(root)
            original = discovery.read_snapshot

            def enforce_small_limit(path, max_bytes):
                if path == source:
                    return None
                return original(path, max_bytes)

            with mock.patch.object(discovery, "read_snapshot", enforce_small_limit):
                result = index_project(root)
            self.assertEqual((result["files"], result["index_state"]), (1, "STALE"))
            self.assertIn({"code": "file_exceeds_size_limit", "path": "app.py"}, result["diagnostics"])

    def test_invalid_file_is_retained_with_parse_error_and_database_is_integrity_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
            index_project(root)
            connection = connect(root / ".pie" / "index.sqlite3")
            try:
                status = connection.execute("SELECT parse_status FROM files WHERE path = 'broken.py'").fetchone()[0]
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                self.assertEqual(status, "error:SyntaxError")
                self.assertEqual(command_status(root)["index_state"], "PARTIAL")
                self.assertEqual(command_status(root)["diagnostics"], [{"code": "parse_error", "path": "broken.py", "error": "SyntaxError"}])
                self.assertEqual(index_project(root)["index_state"], "PARTIAL")
                self.assertEqual(integrity, "ok")
                self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            finally:
                connection.close()

