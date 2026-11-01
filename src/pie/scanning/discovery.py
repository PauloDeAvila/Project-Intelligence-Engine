from pathlib import Path

from pie.core.models import FileRecord
from pie.scanning.hashing import sha256_bytes
from pie.scanning.ignore import IgnoreRules

IGNORED_DIRECTORIES = {".git", ".pie", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules"}
LANGUAGES = {".py": "python"}


def discover_files(root: Path, max_bytes: int = 5_000_000) -> list[FileRecord]:
    """Return eligible source files below root, in stable relative-path order."""
    root = root.resolve()
    ignore = IgnoreRules(root)
    records: list[FileRecord] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink() or not path.is_file() or any(part in IGNORED_DIRECTORIES for part in relative.parts) or ignore.ignored(relative):
            continue
        try:
            content = path.read_bytes()
        except OSError:
            # A file may disappear or become unreadable while the tree is scanned.
            # Such a transient filesystem race must not abort the whole index.
            continue
        if len(content) > max_bytes:
            continue
        language = LANGUAGES.get(path.suffix.lower())
        if language is None:
            continue
        records.append(FileRecord(relative, sha256_bytes(content), len(content), language, content))
    return records

