import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pie.indexing.indexer import index_project
from pie.scanning import discovery
from pie.storage.database import connect


class IndexPersistenceTests(unittest.TestCase):
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
            connection = connect(root / ".pie" / "index.sqlite3")
            try:
                self.assertEqual(connection.execute("SELECT name FROM symbols").fetchone()[0], "stable")
            finally:
                connection.close()
            source.unlink()
            deleted = index_project(root)
            self.assertEqual((deleted["files"], deleted["symbols"]), (0, 0))

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
            shutil.rmtree(nested)
            after_deletion = index_project(root)
            self.assertEqual((after_deletion["files"], after_deletion["symbols"]), (0, 0))

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
                self.assertEqual(integrity, "ok")
                self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            finally:
                connection.close()

