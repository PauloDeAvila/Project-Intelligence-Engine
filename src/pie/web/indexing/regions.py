"""Role and region indexes for local web search."""

from __future__ import annotations

from collections import defaultdict

from ..contracts import PageSnapshot, WebStateError
from .extractor import CandidateExtractor
from .models import RegionIndex, SearchDocument


class RegionIndexer:
    """Create deterministic immutable indexes without selectors or external APIs."""

    def build(
        self,
        snapshot: PageSnapshot,
        documents: tuple[SearchDocument, ...] | None = None,
    ) -> RegionIndex:
        if not isinstance(snapshot, PageSnapshot):
            raise WebStateError("snapshot must be a PageSnapshot")
        docs = documents if documents is not None else CandidateExtractor().extract(snapshot)
        by_region: dict[str, list[str]] = defaultdict(list)
        by_role: dict[str, list[str]] = defaultdict(list)
        for document in docs:
            candidate = document.candidate
            by_role[candidate.role].append(candidate.ref)
            if candidate.region:
                by_region[candidate.region.casefold()].append(candidate.ref)
        return RegionIndex(
            snapshot_id=snapshot.snapshot_id,
            by_region=tuple((key, tuple(values)) for key, values in sorted(by_region.items())),
            by_role=tuple((key, tuple(values)) for key, values in sorted(by_role.items())),
        )


__all__ = ["RegionIndexer"]
