"""Content-authoritative project snapshot verification."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from pie.scanning.discovery import iter_files
import time


class SnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class SnapshotResult:
    indexed: dict[str, str]
    observed: dict[str, str]
    files_checked: int
    bytes_hashed: int


class SnapshotVerifier:
    def __init__(self, root: Path, indexed: dict[str, str]):
        self.root = Path(root).resolve(strict=True)
        self.indexed = dict(indexed)

    def verify(self) -> SnapshotResult:
        unreadable, directories, oversized = set(), set(), set()
        metrics = {"read_seconds": 0.0, "hash_seconds": 0.0}
        started = time.perf_counter()
        try:
            records = list(iter_files(self.root, unreadable_paths=unreadable,
                                      unreadable_directories=directories,
                                      oversized_paths=oversized, metrics=metrics))
        except OSError as exc:
            raise SnapshotError("PARTIAL_PROJECT: discovery failed") from exc
        if unreadable or directories or oversized:
            raise SnapshotError("PARTIAL_PROJECT: unreadable or oversized sources")
        observed = {record.path.as_posix(): record.sha256 for record in records}
        if self.indexed != observed:
            raise SnapshotError("STALE_PROJECT: source inventory/hash mismatch; reindex required")
        result = SnapshotResult(self.indexed, observed, len(records), sum(record.size for record in records))
        self.last_metrics = {"total_seconds": time.perf_counter() - started,
                             "read_seconds": metrics["read_seconds"],
                             "hash_seconds": metrics["hash_seconds"]}
        self.last_metrics["enumeration_seconds"] = max(0.0, self.last_metrics["total_seconds"] - self.last_metrics["read_seconds"] - self.last_metrics["hash_seconds"])
        return result
