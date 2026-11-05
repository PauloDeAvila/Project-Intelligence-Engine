"""Page snapshot freshness tracking for dynamic pages."""

from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock

from ..contracts import PageSnapshot, ReferenceState, SnapshotState, WebStateError

MAX_TRACKED_CONTEXTS = 1024


@dataclass(frozen=True, slots=True)
class TrackingResult:
    snapshot: PageSnapshot
    changed: bool
    stale: bool


class PageStateTracker:
    """Keep only the newest observation authoritative for each page/frame."""

    def __init__(self, *, max_contexts: int = MAX_TRACKED_CONTEXTS) -> None:
        if not isinstance(max_contexts, int) or isinstance(max_contexts, bool) or not 1 <= max_contexts <= 8192:
            raise WebStateError("max_contexts is outside the safe bound")
        self._lock = RLock()
        self._max_contexts = max_contexts
        self._current: dict[tuple[str, str, str], PageSnapshot] = {}

    def observe(self, snapshot: PageSnapshot) -> TrackingResult:
        if not isinstance(snapshot, PageSnapshot):
            raise WebStateError("tracker accepts PageSnapshot values only")
        key = (snapshot.session_id, snapshot.page_id, snapshot.frame_id)
        with self._lock:
            previous = self._current.get(key)
            if previous is None:
                if len(self._current) >= self._max_contexts:
                    raise WebStateError("page tracker capacity exceeded")
                current = snapshot
                changed = True
                stale = False
            elif snapshot.generation < previous.generation:
                current = self._with_state(snapshot, SnapshotState.STALE)
                changed = False
                stale = True
            elif snapshot.generation == previous.generation and snapshot.snapshot_sha256 != previous.snapshot_sha256:
                current = self._with_state(snapshot, SnapshotState.PARTIAL)
                changed = True
                stale = False
            else:
                current = snapshot
                changed = snapshot.snapshot_sha256 != previous.snapshot_sha256
                stale = False
            if not stale:
                self._current[key] = current
            return TrackingResult(current, changed, stale)

    @staticmethod
    def _with_state(snapshot: PageSnapshot, state: SnapshotState) -> PageSnapshot:
        elements = tuple(replace(item, reference_state=ReferenceState.CURRENT) for item in snapshot.elements)
        return replace(snapshot, elements=elements, state=state)

    def current(self, session_id: str, page_id: str, frame_id: str) -> PageSnapshot | None:
        with self._lock:
            return self._current.get((session_id, page_id, frame_id))

    def invalidate(self, session_id: str, page_id: str, frame_id: str) -> PageSnapshot | None:
        key = (session_id, page_id, frame_id)
        with self._lock:
            previous = self._current.pop(key, None)
            return self._with_state(previous, SnapshotState.STALE) if previous is not None else None


__all__ = ["PageStateTracker", "TrackingResult"]
