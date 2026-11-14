import os
import time
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
    metrics: dict[str, float] | None = None,
    selected_paths: set[str] | None = None,
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
        if selected_paths is not None:
            if len(selected_paths) > 10000:
                raise ValueError("Too many incremental file paths")
            for name in sorted(selected_paths):
                if not isinstance(name, str) or not name or "\\x00" in name:
                    raise ValueError("Invalid incremental file path")
                relative = Path(name)
                if (relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts)
                        or "\\\\" in name):
                    raise ValueError("Incremental path must stay inside workspace")
                target = root / relative
                # No traversal through directory symlinks; preserve stale records
                # until an unambiguous deletion/replace can be confirmed.
                for i in range(1, len(relative.parts)+1):
                    if (root.joinpath(*relative.parts[:i])).is_symlink():
                        if unreadable_paths is not None:
                            unreadable_paths.add(relative)
                        break
                else:
                    if target.is_file():
                        yield target
                    elif target.exists() and unreadable_paths is not None:
                        unreadable_paths.add(relative)
            return
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
        # Non-Python files cannot enter the index. Skip them before filesystem
        # metadata and ignore-rule checks; directory traversal rules remain
        # unchanged in scan_paths().
        language = LANGUAGES.get(path.suffix.lower())
        if language is None:
            continue
        if path.is_symlink() or any(part in IGNORED_DIRECTORIES for part in relative.parts) or ignore.ignored(relative):
            continue
        try:
            read_started = time.perf_counter()
            content = read_snapshot(path, max_bytes)
            if metrics is not None: metrics["read_seconds"] = metrics.get("read_seconds", 0.0) + time.perf_counter() - read_started
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
        hash_started = time.perf_counter()
        digest = sha256_bytes(content)
        if metrics is not None: metrics["hash_seconds"] = metrics.get("hash_seconds", 0.0) + time.perf_counter() - hash_started
        yield FileRecord(relative, digest, len(content), language, content)


def discover_files(root: Path, max_bytes: int = 5_000_000) -> list[FileRecord]:
    """Return eligible source files below root, in stable relative-path order."""
    return list(iter_files(root, max_bytes))

