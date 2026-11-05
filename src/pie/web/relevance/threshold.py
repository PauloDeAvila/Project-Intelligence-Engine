"""Deterministic threshold selection for quantified context."""

from __future__ import annotations

from ..contracts import WebStateError


class DecisionThresholdController:
    """Choose a conservative threshold from bounded workload signals."""

    def choose(
        self,
        *,
        candidate_count: int,
        max_candidates: int,
        context_budget_chars: int,
        ambiguous: bool,
    ) -> float:
        for name, value in (("candidate_count", candidate_count), ("max_candidates", max_candidates), ("context_budget_chars", context_budget_chars)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise WebStateError(f"{name} must be a positive integer")
        if max_candidates > 32 or context_budget_chars > 1_000_000 or not isinstance(ambiguous, bool):
            raise WebStateError("threshold inputs are outside the safe bound")
        threshold = 0.30
        if candidate_count > max_candidates * 4:
            threshold += 0.15
        if context_budget_chars < max_candidates * 128:
            threshold += 0.10
        if ambiguous:
            threshold -= 0.10
        return round(max(0.15, min(0.75, threshold)), 6)


__all__ = ["DecisionThresholdController"]
