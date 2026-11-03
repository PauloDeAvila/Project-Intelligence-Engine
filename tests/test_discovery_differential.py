"""Differential regressions for moving language filtering before metadata checks."""
from hashlib import sha256
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pie.retrieval.snapshot import SnapshotError, SnapshotVerifier
from pie.scanning import discovery
from pie.scanning.ignore import IgnoreRules


def legacy_manifest(root):
    """Pre-optimization eligibility order; no dependency on Git at test time."""
    ignore = IgnoreRules(root)
    manifest = {}
    for current, directories, filenames in os.walk(root, topdown=True):
        base = Path(current)
        directories[:] = [name for name in sorted(directories)
                          if not (base / name).is_symlink()
                          and name not in discovery.IGNORED_DIRECTORIES
                          and not ignore.ignored((base / name).relative_to(root), is_directory=True)]
        for name in sorted(filenames):
            path = base / name
            relative = path.relative_to(root)
            if path.is_symlink() or any(p in discovery.IGNORED_DIRECTORIES for p in relative.parts) or ignore.ignored(relative):
                continue
            if path.suffix.lower() not in discovery.LANGUAGES:
                continue
            raw = discovery.read_snapshot(path, 5_000_000)
            if raw is not None:
                manifest[relative.as_posix()] = sha256(raw).hexdigest()
    return manifest


class DiscoveryDifferentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, content="value = 1\n"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def assert_equivalent(self, expected):
        actual = {r.path.as_posix(): r.sha256 for r in discovery.iter_files(self.root)}
        self.assertEqual(actual, legacy_manifest(self.root))
        self.assertEqual(set(actual), set(expected))

    def test_mixed_extensions_unicode_and_non_source_control_files(self):
        for name in ("source.py", "UPPER.PY", "Mixed.pY", "nested/área 分析.py", "module.py.txt", "py", "picture.PNG"):
            self.write(name)
        self.write(".gitignore", "*.py.txt\n")
        self.assert_equivalent({"source.py", "UPPER.PY", "Mixed.pY", "nested/área 分析.py"})

    def test_nested_negations_and_excluded_parent_are_preserved(self):
        self.write(".gitignore", "*.py\n!keep.py\nexcluded/\n!excluded/rescue.py\n")
        self.write("pkg/.gitignore", "!allowed.PY\n!revived.py\n/private/\n")
        for name in ("keep.py", "drop.py", "pkg/revived.py", "pkg/allowed.PY", "pkg/drop.py",
                     "pkg/private/keep.py", "excluded/rescue.py", "excluded/keep.py"):
            self.write(name)
        self.assert_equivalent({"keep.py", "pkg/revived.py", "pkg/allowed.PY"})

    def test_symlink_files_and_directories_are_excluded(self):
        self.write("real.py")
        self.write("real_dir/child.py")
        try:
            (self.root / "link.PY").symlink_to(self.root / "real.py")
            (self.root / "linked_dir").symlink_to(self.root / "real_dir", target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        self.assert_equivalent({"real.py", "real_dir/child.py"})

    def test_content_changed_after_enumeration_is_read_and_rejected(self):
        source = self.write("source.py", "value = 1\n")
        indexed = legacy_manifest(self.root)
        stat = source.stat()
        original = discovery.read_snapshot

        def change_before_read(path, max_bytes):
            source.write_text("value = 2\n", encoding="utf-8")
            os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            return original(path, max_bytes)

        with patch.object(discovery, "read_snapshot", side_effect=change_before_read):
            with self.assertRaisesRegex(SnapshotError, "STALE_PROJECT"):
                SnapshotVerifier(self.root, indexed).verify()
        self.assertEqual(source.stat().st_size, stat.st_size)
        self.assertEqual(source.stat().st_mtime_ns, stat.st_mtime_ns)

    def test_deletion_after_enumeration_is_partial_not_silent_absence(self):
        source = self.write("source.py")
        indexed = legacy_manifest(self.root)
        original = discovery.read_snapshot

        def delete_before_read(path, max_bytes):
            source.unlink()
            return original(path, max_bytes)

        with patch.object(discovery, "read_snapshot", side_effect=delete_before_read):
            with self.assertRaisesRegex(SnapshotError, "PARTIAL_PROJECT"):
                SnapshotVerifier(self.root, indexed).verify()


if __name__ == "__main__":
    unittest.main()
