"""Bounded cache and delta models for the fast browser path."""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import WebStateError


@dataclass(frozen=True, slots=True)
class CacheKey:
    session_id: str
    page_id: str
    generation: int
    region: str
    task_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("session_id", "page_id", "region", "task_fingerprint"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 128:
                raise WebStateError(f"{name} is outside the safe bound")
        if not isinstance(self.generation, int) or isinstance(self.generation, bool) or self.generation < 0:
            raise WebStateError("generation must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class SnapshotDelta:
    before_snapshot_id: str
    after_snapshot_id: str
    added_refs: tuple[str, ...]
    removed_refs: tuple[str, ...]
    changed_refs: tuple[str, ...]
    unchanged_count: int

    def __post_init__(self) -> None:
        for name in ("before_snapshot_id", "after_snapshot_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 128:
                raise WebStateError(f"{name} is outside the safe bound")
        for name in ("added_refs", "removed_refs", "changed_refs"):
            value = getattr(self, name)
            if not isinstance(value, tuple) or len(value) > 512 or not all(isinstance(item, str) and item for item in value):
                raise WebStateError(f"{name} is outside the safe bound")
        if not isinstance(self.unchanged_count, int) or self.unchanged_count < 0:
            raise WebStateError("unchanged_count must be non-negative")


@dataclass(frozen=True, slots=True)
class FastPathResult:
    value: object
    cache_hit: bool
    validation_required: bool = True
    reused_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.cache_hit, bool) or self.validation_required is not True:
            raise WebStateError("fast path must require validation")
        if len(self.reused_refs) > 512 or not all(isinstance(item, str) and item for item in self.reused_refs):
            raise WebStateError("reused_refs are outside the safe bound")


@dataclass(frozen=True, slots=True)
class PrefetchPlan:
    session_id: str
    page_id: str
    generation: int
    regions: tuple[str, ...]
    task_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("session_id", "page_id", "task_fingerprint"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 128:
                raise WebStateError(f"{name} is outside the safe bound")
        if not isinstance(self.generation, int) or isinstance(self.generation, bool) or self.generation < 0:
            raise WebStateError("generation must be a non-negative integer")
        if not isinstance(self.regions, tuple) or len(self.regions) > 32 or not all(isinstance(item, str) and item for item in self.regions):
            raise WebStateError("regions are outside the safe bound")


__all__ = ["CacheKey", "FastPathResult", "PrefetchPlan", "SnapshotDelta"]
