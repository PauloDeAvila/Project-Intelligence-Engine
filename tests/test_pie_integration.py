import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pie.indexing.indexer import index_project
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

