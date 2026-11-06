"""Reuse only current candidate values whose bounded fingerprints are unchanged."""

from __future__ import annotations

from ..contracts import PageSnapshot, ReferenceState, WebStateError
from .delta import SnapshotDeltaEngine


class ElementReuseManager:
    def __init__(self, *, delta_engine: SnapshotDeltaEngine | None = None) -> None:
        self.delta_engine = delta_engine or SnapshotDeltaEngine()

    def reusable(self, before: PageSnapshot, after: PageSnapshot) -> tuple[str, ...]:
        delta = self.delta_engine.compare(before, after)
        changed = set(delta.added_refs) | set(delta.removed_refs) | set(delta.changed_refs)
        values = tuple(
            candidate.ref
            for candidate in after.elements
            if candidate.ref not in changed and candidate.reference_state is ReferenceState.CURRENT
        )
        return values


__all__ = ["ElementReuseManager"]
