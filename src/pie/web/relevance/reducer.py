"""Budgeted redundancy reduction with an auditable omission ledger."""

from __future__ import annotations

from ..contracts import WebStateError
from ..indexing.extractor import tokenize
from .models import OmissionRecord, ReductionResult, ScoredCandidate


class RedundancyReducer:
    def reduce(
        self,
        ranked: tuple[ScoredCandidate, ...],
        *,
        threshold: float,
        context_budget_chars: int,
        max_candidates: int,
    ) -> ReductionResult:
        if not isinstance(ranked, tuple) or len(ranked) > 512 or not all(isinstance(item, ScoredCandidate) for item in ranked):
            raise WebStateError("ranked candidates are outside the safe bound")
        if not isinstance(threshold, (int, float)) or not 0.0 <= float(threshold) <= 1.0:
            raise WebStateError("threshold must be between 0 and 1")
        if not isinstance(context_budget_chars, int) or not 1 <= context_budget_chars <= 1_000_000:
            raise WebStateError("context budget is outside the safe bound")
        if not isinstance(max_candidates, int) or not 1 <= max_candidates <= 32:
            raise WebStateError("max_candidates is outside the safe bound")
        selected: list[ScoredCandidate] = []
        omitted: list[OmissionRecord] = []
        seen: set[tuple[str, tuple[str, ...], str | None, str]] = set()
        estimated = 0
        for item in ranked:
            candidate = item.candidate
            fingerprint = (candidate.role, tokenize(candidate.accessible_name), candidate.region, candidate.frame_id)
            if fingerprint in seen:
                omitted.append(OmissionRecord(candidate.ref, "duplicate", item.score))
                continue
            seen.add(fingerprint)
            if not item.protected and item.score < threshold:
                omitted.append(OmissionRecord(candidate.ref, "below_threshold", item.score))
                continue
            if len(selected) >= max_candidates and not item.protected:
                omitted.append(OmissionRecord(candidate.ref, "limit", item.score))
                continue
            if not item.protected and estimated + item.estimated_chars > context_budget_chars:
                omitted.append(OmissionRecord(candidate.ref, "budget", item.score))
                continue
            selected.append(item)
            estimated += item.estimated_chars
        return ReductionResult(tuple(selected), tuple(omitted), estimated, estimated > context_budget_chars)


__all__ = ["RedundancyReducer"]
