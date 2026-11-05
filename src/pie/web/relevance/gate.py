"""Quantified Web Context gate built on immutable PageSnapshot values."""

from __future__ import annotations

from ..contracts import PageSnapshot, SnapshotState, WebStateError
from .models import QuantifiedWebContext
from .ranker import CandidateRanker
from .reducer import RedundancyReducer
from .scorer import RelevanceScorer
from .threshold import DecisionThresholdController


class WebRelevanceGate:
    """Score, rank and reduce page candidates before any model delivery."""

    def __init__(
        self,
        *,
        scorer: RelevanceScorer | None = None,
        ranker: CandidateRanker | None = None,
        reducer: RedundancyReducer | None = None,
        thresholds: DecisionThresholdController | None = None,
    ) -> None:
        self.scorer = scorer or RelevanceScorer()
        self.ranker = ranker or CandidateRanker()
        self.reducer = reducer or RedundancyReducer()
        self.thresholds = thresholds or DecisionThresholdController()

    def quantify(
        self,
        snapshot: PageSnapshot,
        query: str,
        *,
        semantic_role: str | None = None,
        region: str | None = None,
        context_budget_chars: int = 4096,
        max_candidates: int = 8,
    ) -> QuantifiedWebContext:
        if not isinstance(snapshot, PageSnapshot):
            raise WebStateError("snapshot must be a PageSnapshot")
        if snapshot.state in {SnapshotState.STALE, SnapshotState.BLOCKED}:
            raise WebStateError("stale or blocked snapshots cannot be quantified")
        if not isinstance(query, str) or not query.strip() or len(query) > 256:
            raise WebStateError("query is outside the safe bound")
        if not isinstance(max_candidates, int) or isinstance(max_candidates, bool) or not 1 <= max_candidates <= 32:
            raise WebStateError("max_candidates is outside the safe bound")
        scored = tuple(
            self.scorer.score(
                candidate,
                ordinal=ordinal,
                query=query,
                semantic_role=semantic_role,
                region=region,
            )
            for ordinal, candidate in enumerate(snapshot.elements)
        )
        ranked = self.ranker.rank(scored)
        preliminary_ambiguous = len(ranked) > 1 and ranked[0].score - ranked[1].score <= 0.05
        threshold = self.thresholds.choose(
            candidate_count=len(ranked),
            max_candidates=max_candidates,
            context_budget_chars=context_budget_chars,
            ambiguous=preliminary_ambiguous,
        )
        reduction = self.reducer.reduce(
            ranked,
            threshold=threshold,
            context_budget_chars=context_budget_chars,
            max_candidates=max_candidates,
        )
        ambiguous = preliminary_ambiguous or (bool(reduction.selected) and reduction.selected[0].score < 0.5)
        return QuantifiedWebContext(
            snapshot_id=snapshot.snapshot_id,
            state=snapshot.state,
            query=query,
            selected=reduction.selected,
            omissions=reduction.omitted,
            threshold=threshold,
            context_budget_chars=context_budget_chars,
            estimated_chars=reduction.estimated_chars,
            ambiguous=ambiguous,
            source_omitted_count=snapshot.omitted_count,
            expansion_available=bool(reduction.omitted or snapshot.omitted_count),
        )


__all__ = ["WebRelevanceGate"]
