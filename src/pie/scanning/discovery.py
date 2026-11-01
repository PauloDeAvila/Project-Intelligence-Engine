from pathlib import Path

from pie.core.models import FileRecord
from pie.scanning.hashing import sha256_file

IGNORED_DIRECTORIES = {".git", ".pie", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules"}
LANGUAGES = {".py": "python"}


def discover_files(root: Path, max_bytes: int = 5_000_000) -> list[FileRecord]:
    """Return eligible source files below root, in stable relative-path order."""
    root = root.resolve()
    records: list[FileRecord] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file() or any(part in IGNORED_DIRECTORIES for part in path.relative_to(root).parts):
            continue
        if path.stat().st_size > max_bytes:
            continue
        language = LANGUAGES.get(path.suffix.lower())
        if language is None:
            continue
        relative = path.relative_to(root)
        records.append(FileRecord(relative, sha256_file(path), path.stat().st_size, language))
    return records

