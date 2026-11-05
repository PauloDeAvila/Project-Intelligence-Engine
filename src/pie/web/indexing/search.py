"""Fast deterministic in-memory search over one or more page snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from ..contracts import PageSnapshot, SnapshotState, WebStateError
from .extractor import CandidateExtractor, tokenize
from .models import RegionIndex, SearchDocument, SearchMatch, SearchResponse
from .regions import RegionIndexer
from .roles import SemanticRoleMatcher


@dataclass(frozen=True, slots=True)
class _IndexedSnapshot:
    snapshot: PageSnapshot
    documents: tuple[SearchDocument, ...]
    by_term: tuple[tuple[str, tuple[str, ...]], ...]
    regions: RegionIndex

    def refs_for_term(self, term: str) -> tuple[str, ...]:
        for key, refs in self.by_term:
            if key == term:
                return refs
        return ()


def _selector_like(query: str) -> bool:
    stripped = query.strip()
    return stripped.startswith(("#", ".", "[", ">")) or "]" in stripped or "=>" in stripped


class LocalWebSearch:
    """Index and search snapshots without embeddings, network or model calls."""

    def __init__(
        self,
        *,
        candidate_extractor: CandidateExtractor | None = None,
        region_indexer: RegionIndexer | None = None,
        role_matcher: SemanticRoleMatcher | None = None,
        max_snapshots: int = 256,
        ambiguity_margin: float = 0.05,
    ) -> None:
        if not isinstance(max_snapshots, int) or isinstance(max_snapshots, bool) or not 1 <= max_snapshots <= 2048:
            raise WebStateError("max_snapshots is outside the safe bound")
        if not isinstance(ambiguity_margin, (int, float)) or isinstance(ambiguity_margin, bool) or not 0.0 <= ambiguity_margin <= 0.5:
            raise WebStateError("ambiguity_margin is outside the safe bound")
        self._extractor = candidate_extractor or CandidateExtractor()
        self._region_indexer = region_indexer or RegionIndexer()
        self._role_matcher = role_matcher or SemanticRoleMatcher()
        self._max_snapshots = max_snapshots
        self._ambiguity_margin = float(ambiguity_margin)
        self._lock = RLock()
        self._indexes: dict[str, _IndexedSnapshot] = {}

    def register(self, snapshot: PageSnapshot) -> None:
        if not isinstance(snapshot, PageSnapshot):
            raise WebStateError("search accepts PageSnapshot values only")
        if snapshot.state in {SnapshotState.BLOCKED, SnapshotState.STALE}:
            raise WebStateError("blocked or stale snapshots cannot be indexed")
        documents = self._extractor.extract(snapshot)
        terms: dict[str, list[str]] = {}
        for document in documents:
            for term in document.tokens:
                terms.setdefault(term, []).append(document.candidate.ref)
        indexed = _IndexedSnapshot(
            snapshot=snapshot,
            documents=documents,
            by_term=tuple((key, tuple(dict.fromkeys(refs))) for key, refs in sorted(terms.items())),
            regions=self._region_indexer.build(snapshot, documents),
        )
        with self._lock:
            existing = self._indexes.get(snapshot.snapshot_id)
            if existing is not None:
                if existing.snapshot != snapshot:
                    raise WebStateError("snapshot_id collision with different search content")
                return
            if len(self._indexes) >= self._max_snapshots:
                raise WebStateError("search index capacity exceeded")
            self._indexes[snapshot.snapshot_id] = indexed

    def get(self, snapshot_id: str) -> _IndexedSnapshot | None:
        with self._lock:
            return self._indexes.get(snapshot_id)

    def search(
        self,
        snapshot_id: str,
        query: str,
        *,
        semantic_role: str | None = None,
        region: str | None = None,
        include_unsupported: bool = False,
        max_results: int = 10,
    ) -> SearchResponse:
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise WebStateError("snapshot_id must be non-empty")
        if not isinstance(query, str) or not query.strip() or len(query) > 256:
            raise WebStateError("query must be bounded and non-empty")
        if not isinstance(max_results, int) or isinstance(max_results, bool) or not 1 <= max_results <= 32:
            raise WebStateError("max_results is outside the safe bound")
        if region is not None and (not isinstance(region, str) or not region.strip() or len(region) > 128):
            raise WebStateError("region is outside the safe bound")
        indexed = self.get(snapshot_id)
        if indexed is None:
            raise WebStateError("snapshot is not indexed")
        if _selector_like(query):
            return SearchResponse(snapshot_id, indexed.snapshot.state, (), False, 0)
        terms = tokenize(query)
        inferred_roles = self._role_matcher.infer(query)
        explicit_targets = self._role_matcher.targets_for(semantic_role) if semantic_role else frozenset()
        requested_region = region.casefold() if region else None
        candidate_refs: set[str] = set()
        for term in terms:
            candidate_refs.update(indexed.refs_for_term(term))
        if inferred_roles:
            for document in indexed.documents:
                if any(document.candidate.role in self._role_matcher.targets_for(role) for role in inferred_roles):
                    candidate_refs.add(document.candidate.ref)
        if explicit_targets:
            candidate_refs.update(
                ref for role in explicit_targets for ref in indexed.regions.refs_for_role(role)
            )
        if requested_region:
            candidate_refs.intersection_update(set(indexed.regions.refs_for_region(requested_region)))
        matches: list[SearchMatch] = []
        for document in indexed.documents:
            candidate = document.candidate
            if candidate.ref not in candidate_refs:
                continue
            if not include_unsupported and candidate.support.value == "UNSUPPORTED":
                continue
            if explicit_targets and candidate.role not in explicit_targets:
                continue
            name_tokens = set(tokenize(candidate.accessible_name))
            matched = tuple(term for term in terms if term in name_tokens or term == candidate.role)
            name_coverage = len(set(matched)) / max(1, len(set(terms)))
            role_hit = bool(self._role_matcher.matches(query, candidate.role)) or candidate.role in explicit_targets
            region_hit = requested_region is not None and candidate.region is not None and candidate.region.casefold() == requested_region
            visible_bonus = 0.05 if candidate.visible else 0.0
            enabled_bonus = 0.05 if candidate.enabled else 0.0
            score = min(1.0, 0.55 * name_coverage + (0.25 if role_hit else 0.0) + (0.10 if region_hit else 0.0) + visible_bonus + enabled_bonus)
            reasons = [f"name_coverage:{name_coverage:.2f}"]
            if role_hit:
                reasons.append("semantic_role_match")
            if region_hit:
                reasons.append("region_match")
            if candidate.visible:
                reasons.append("visible")
            if candidate.enabled:
                reasons.append("enabled")
            matches.append(SearchMatch(candidate, round(score, 6), tuple(reasons), matched))
        matches.sort(key=lambda match: (-match.score, indexed.snapshot.elements.index(match.candidate), match.candidate.ref))
        total = len(matches)
        selected = tuple(matches[:max_results])
        ambiguous = bool(selected) and (
            selected[0].score < 0.5
            or (len(selected) > 1 and selected[0].score - selected[1].score <= self._ambiguity_margin)
        )
        return SearchResponse(
            snapshot_id,
            indexed.snapshot.state,
            selected,
            ambiguous,
            total,
            indexed.snapshot.omitted_count,
        )


__all__ = ["LocalWebSearch"]
