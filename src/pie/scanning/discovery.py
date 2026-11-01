import os
from collections.abc import Iterator
from pathlib import Path

from pie.core.models import FileRecord
from pie.scanning.hashing import sha256_bytes
from pie.scanning.ignore import IgnoreRules

IGNORED_DIRECTORIES = {".git", ".pie", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules"}
LANGUAGES = {".py": "python"}


def read_snapshot(path: Path, max_bytes: int) -> bytes | None:
    """Read at most the configured limit plus one byte to bound scanner memory."""
    with path.open("rb") as source:
        content = source.read(max_bytes + 1)
    return None if len(content) > max_bytes else content


def iter_files(
    root: Path,
    max_bytes: int = 5_000_000,
    unreadable_paths: set[Path] | None = None,
    unreadable_directories: set[Path] | None = None,
    oversized_paths: set[Path] | None = None,
) -> Iterator[FileRecord]:
    """Yield eligible files one at a time, keeping only one content snapshot in memory."""
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")
    root = root.resolve()
    ignore = IgnoreRules(root)
    def walk_error(error: OSError) -> None:
        if unreadable_directories is not None:
            failed = Path(error.filename) if error.filename else root
            try:
                unreadable_directories.add(failed.resolve().relative_to(root))
            except (OSError, ValueError):
                unreadable_directories.add(Path("."))

    def scan_paths() -> Iterator[Path]:
        for current, directories, filenames in os.walk(root, topdown=True, onerror=walk_error):
            current_path = Path(current)
            kept_directories = []
            for name in sorted(directories):
                candidate = current_path / name
                relative = candidate.relative_to(root)
                if candidate.is_symlink() or name in IGNORED_DIRECTORIES or ignore.ignored(relative, is_directory=True):
                    continue
                kept_directories.append(name)
            directories[:] = kept_directories
            for name in sorted(filenames):
                yield current_path / name

    for path in scan_paths():
        relative = path.relative_to(root)
        if path.is_symlink() or any(part in IGNORED_DIRECTORIES for part in relative.parts) or ignore.ignored(relative):
            continue
        language = LANGUAGES.get(path.suffix.lower())
        if language is None:
            continue
        try:
            content = read_snapshot(path, max_bytes)
        except OSError:
            # Keep the last indexed state for this path rather than treating a
            # transient read failure as a confirmed deletion.
            if unreadable_paths is not None:
                unreadable_paths.add(relative)
            continue
        if content is None:
            if oversized_paths is not None:
                oversized_paths.add(relative)
            continue
        yield FileRecord(relative, sha256_bytes(content), len(content), language, content)


def discover_files(root: Path, max_bytes: int = 5_000_000) -> list[FileRecord]:
    """Return eligible source files below root, in stable relative-path order."""
    return list(iter_files(root, max_bytes))

