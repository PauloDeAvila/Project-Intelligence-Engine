"""Snapshot-local element registry with literal, non-selector lookup."""

from __future__ import annotations

from threading import RLock

from ..contracts import ElementCandidate, PageSnapshot, ReferenceState, SnapshotState, WebStateError

MAX_REGISTERED_SNAPSHOTS = 1024


class ElementRegistry:
    """Index candidates by snapshot, role and literal accessible-name text."""

    def __init__(self, *, max_snapshots: int = MAX_REGISTERED_SNAPSHOTS) -> None:
        if not isinstance(max_snapshots, int) or isinstance(max_snapshots, bool) or not 1 <= max_snapshots <= 8192:
            raise WebStateError("max_snapshots is outside the safe bound")
        self._lock = RLock()
        self._max_snapshots = max_snapshots
        self._snapshots: dict[str, PageSnapshot] = {}
        self._current_by_context: dict[tuple[str, str, str], str] = {}

    def register(self, snapshot: PageSnapshot) -> None:
        if not isinstance(snapshot, PageSnapshot):
            raise WebStateError("registry accepts PageSnapshot values only")
        with self._lock:
            existing = self._snapshots.get(snapshot.snapshot_id)
            if existing is not None:
                if existing != snapshot:
                    raise WebStateError("snapshot_id collision with different snapshot content")
                return
            if len(self._snapshots) >= self._max_snapshots:
                raise WebStateError("snapshot registry capacity exceeded")
            if snapshot.state is not SnapshotState.CURRENT:
                self._snapshots[snapshot.snapshot_id] = snapshot
                return
            context = (snapshot.session_id, snapshot.page_id, snapshot.frame_id)
            current_id = self._current_by_context.get(context)
            if current_id is None:
                self._snapshots[snapshot.snapshot_id] = snapshot
                self._current_by_context[context] = snapshot.snapshot_id
                return
            current = self._snapshots[current_id]
            if snapshot.generation < current.generation:
                self._snapshots[snapshot.snapshot_id] = snapshot
                return
            if snapshot.generation == current.generation:
                raise WebStateError("different CURRENT snapshots cannot share a generation")
            self._snapshots[snapshot.snapshot_id] = snapshot
            self._current_by_context[context] = snapshot.snapshot_id

    def get(self, snapshot_id: str) -> PageSnapshot | None:
        with self._lock:
            return self._snapshots.get(snapshot_id)

    def find(
        self,
        snapshot_id: str,
        *,
        role: str | None = None,
        name_contains: str | None = None,
        include_unsupported: bool = True,
    ) -> tuple[ElementCandidate, ...]:
        snapshot = self.get(snapshot_id)
        if snapshot is None:
            return ()
        role_value = role.casefold() if role is not None else None
        literal = name_contains.casefold() if name_contains is not None else None
        if literal is not None and len(literal) > 256:
            raise WebStateError("name_contains is too long")
        values = []
        for element in snapshot.elements:
            if not include_unsupported and element.support.value == "UNSUPPORTED":
                continue
            if role_value is not None and element.role != role_value:
                continue
            if literal is not None and literal not in element.accessible_name.casefold():
                continue
            values.append(element)
        return tuple(values)

    def resolve(
        self,
        reference: ElementCandidate,
        *,
        session_id: str,
        page_id: str,
        frame_id: str,
        generation: int,
        snapshot_sha256: str,
    ) -> ElementCandidate | None:
        if reference.reference_state is not ReferenceState.CURRENT:
            return None
        if (
            reference.session_id != session_id
            or reference.page_id != page_id
            or reference.frame_id != frame_id
            or reference.generation != generation
            or reference.snapshot_sha256 != snapshot_sha256
        ):
            return None
        context = (session_id, page_id, frame_id)
        with self._lock:
            snapshot = self._snapshots.get(reference.snapshot_id)
            if snapshot is None or snapshot.state is not SnapshotState.CURRENT:
                return None
            if self._current_by_context.get(context) != snapshot.snapshot_id:
                return None
            if (
                snapshot.session_id != session_id
                or snapshot.page_id != page_id
                or snapshot.frame_id != frame_id
                or snapshot.generation != generation
                or snapshot.snapshot_sha256 != snapshot_sha256
            ):
                return None
            stored = snapshot.find(reference.ref)
            if stored is None or stored != reference:
                return None
            return stored


__all__ = ["ElementRegistry"]
