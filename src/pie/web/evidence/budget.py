"""Strict deterministic context allocation for evidence packs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..contracts import WebStateError
from ..relevance.models import ScoredCandidate
from .models import EvidenceOmission


@dataclass(frozen=True, slots=True)
class BudgetAllocation:
    selected: tuple[ScoredCandidate, ...]
    omitted: tuple[EvidenceOmission, ...]
    used_chars: int


class ContextBudgetController:
    def allocate(
        self,
        candidates: tuple[ScoredCandidate, ...],
        *,
        estimate: Callable[[ScoredCandidate], int],
        context_budget_chars: int,
        max_items: int,
    ) -> BudgetAllocation:
        if not isinstance(candidates, tuple) or not 1 <= max_items <= 32:
            raise WebStateError("invalid candidates or max_items")
        if not isinstance(context_budget_chars, int) or not 1 <= context_budget_chars <= 1_000_000:
            raise WebStateError("context budget is outside the safe bound")
        selected: list[ScoredCandidate] = []
        omitted: list[EvidenceOmission] = []
        used = 0
        for index, candidate in enumerate(candidates):
            size = estimate(candidate)
            if not isinstance(size, int) or not 1 <= size <= 4096:
                raise WebStateError("candidate estimate is outside the safe bound")
            if len(selected) >= max_items:
                omitted.append(EvidenceOmission(candidate.candidate.ref, "limit", candidate.score, True))
            elif used + size > context_budget_chars:
                omitted.append(EvidenceOmission(candidate.candidate.ref, "budget", candidate.score, True))
            else:
                selected.append(candidate)
                used += size
        return BudgetAllocation(tuple(selected), tuple(omitted), used)


__all__ = ["BudgetAllocation", "ContextBudgetController"]
