"""Content-authoritative project snapshot verification."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from pie.scanning.discovery import iter_files


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
        records = list(iter_files(self.root, unreadable_paths=unreadable,
                                  unreadable_directories=directories,
                                  oversized_paths=oversized))
        if unreadable or directories or oversized:
            raise SnapshotError("PARTIAL_PROJECT: unreadable or oversized sources")
        observed = {record.path.as_posix(): record.sha256 for record in records}
        if self.indexed != observed:
            raise SnapshotError("STALE_PROJECT: source inventory/hash mismatch; reindex required")
        return SnapshotResult(self.indexed, observed, len(records),
                              sum(record.size for record in records))
