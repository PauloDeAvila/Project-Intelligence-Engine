"""Stable candidate ordering for quantified context."""

from __future__ import annotations

from ..contracts import WebStateError
from .models import ScoredCandidate


class CandidateRanker:
    def rank(self, candidates: tuple[ScoredCandidate, ...] | list[ScoredCandidate]) -> tuple[ScoredCandidate, ...]:
        values = tuple(candidates)
        if len(values) > 512 or not all(isinstance(item, ScoredCandidate) for item in values):
            raise WebStateError("candidates are outside the safe bound")
        return tuple(sorted(values, key=lambda item: (-item.score, not item.protected, item.ordinal, item.candidate.ref)))


__all__ = ["CandidateRanker"]
