"""Local region prefetch planning without browser or network side effects."""

from __future__ import annotations

import hashlib

from ..contracts import PageSnapshot, WebStateError
from ..relevance.models import QuantifiedWebContext
from .models import PrefetchPlan


class RegionPrefetcher:
    def plan(self, snapshot: PageSnapshot, context: QuantifiedWebContext, *, max_regions: int = 8) -> PrefetchPlan:
        if not isinstance(snapshot, PageSnapshot) or not isinstance(context, QuantifiedWebContext):
            raise WebStateError("snapshot and context are required")
        if context.snapshot_id != snapshot.snapshot_id:
            raise WebStateError("context does not belong to snapshot")
        if not isinstance(max_regions, int) or isinstance(max_regions, bool) or not 1 <= max_regions <= 32:
            raise WebStateError("max_regions is outside the safe bound")
        regions = tuple(dict.fromkeys(item.candidate.region for item in context.selected if item.candidate.region))[:max_regions]
        fingerprint = hashlib.sha256(context.query.casefold().encode("utf-8")).hexdigest()
        return PrefetchPlan(snapshot.session_id, snapshot.page_id, snapshot.generation, regions, fingerprint)


__all__ = ["RegionPrefetcher"]
