import tempfile
import unittest
from pathlib import Path

from pie.retrieval.snapshot import SnapshotVerifier, SnapshotError
from pie.scanning.discovery import iter_files


class SnapshotVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "a.py").write_text("value = 1\n", encoding="utf-8")
        self.manifest = {r.path.as_posix(): r.sha256 for r in iter_files(self.root)}

    def tearDown(self):
        self.temp.cleanup()

    def test_unchanged_manifest_is_current(self):
        result = SnapshotVerifier(self.root, self.manifest).verify()
        self.assertEqual(result.files_checked, 1)

    def test_same_size_content_change_is_stale(self):
        (self.root / "a.py").write_text("value = 2\n", encoding="utf-8")
        with self.assertRaisesRegex(SnapshotError, "STALE_PROJECT"):
            SnapshotVerifier(self.root, self.manifest).verify()

    def test_create_delete_and_rename_are_stale(self):
        for action in ("create", "delete", "rename"):
            with self.subTest(action=action):
                if action == "create": (self.root / "new.py").write_text("x=1\n", encoding="utf-8")
                elif action == "delete": (self.root / "a.py").unlink()
                else: (self.root / "a.py").rename(self.root / "renamed.py")
                with self.assertRaisesRegex(SnapshotError, "STALE_PROJECT"):
                    SnapshotVerifier(self.root, self.manifest).verify()
                if action == "create": (self.root / "new.py").unlink()
                elif action == "delete": (self.root / "a.py").write_text("value = 1\n", encoding="utf-8")
                else: (self.root / "renamed.py").rename(self.root / "a.py")


if __name__ == "__main__": unittest.main()
