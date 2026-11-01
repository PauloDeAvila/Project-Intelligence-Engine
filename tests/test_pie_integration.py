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

