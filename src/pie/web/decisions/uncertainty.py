"""Deterministic uncertainty estimation for local semantic routing."""

from __future__ import annotations

from ..contracts import WebStateError
from ..relevance.models import QuantifiedWebContext, ScoredCandidate


class UncertaintyEstimator:
    def estimate(self, context: QuantifiedWebContext, candidate: ScoredCandidate) -> float:
        if not isinstance(context, QuantifiedWebContext) or not isinstance(candidate, ScoredCandidate):
            raise WebStateError("context and candidate are required")
        uncertainty = 0.20
        if context.ambiguous:
            uncertainty += 0.35
        if candidate.score < 0.60:
            uncertainty += 0.25
        if "query_match" not in candidate.reasons and "role_match" not in candidate.reasons:
            uncertainty += 0.15
        if candidate.protected:
            uncertainty = max(0.0, uncertainty - 0.15)
        return min(1.0, round(uncertainty, 6))


__all__ = ["UncertaintyEstimator"]
