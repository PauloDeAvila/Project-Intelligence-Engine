"""Hash-based snapshot deltas without retaining raw page content."""

from __future__ import annotations

import hashlib
import json

from ..contracts import PageSnapshot, SnapshotState, WebStateError
from .models import SnapshotDelta


class SnapshotDeltaEngine:
    def compare(self, before: PageSnapshot, after: PageSnapshot) -> SnapshotDelta:
        if not isinstance(before, PageSnapshot) or not isinstance(after, PageSnapshot):
            raise WebStateError("before and after must be PageSnapshot values")
        if before.session_id != after.session_id or before.page_id != after.page_id:
            raise WebStateError("snapshot session or page changed")
        old = {item.ref: self._fingerprint(item) for item in before.elements}
        new = {item.ref: self._fingerprint(item) for item in after.elements}
        added = tuple(sorted(set(new) - set(old)))
        removed = tuple(sorted(set(old) - set(new)))
        changed = tuple(sorted(ref for ref in set(old) & set(new) if old[ref] != new[ref]))
        unchanged = sum(1 for ref in set(old) & set(new) if old[ref] == new[ref])
        return SnapshotDelta(before.snapshot_id, after.snapshot_id, added, removed, changed, unchanged)

    @staticmethod
    def _fingerprint(candidate) -> str:
        values = {
            "ref": candidate.ref,
            "role": candidate.role,
            "name": candidate.accessible_name,
            "region": candidate.region,
            "visible": candidate.visible,
            "enabled": candidate.enabled,
            "actions": candidate.available_actions,
            "support": candidate.support.value,
        }
        return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


__all__ = ["SnapshotDeltaEngine"]
