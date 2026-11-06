"""Deterministic, category-aware risk scoring for declarative web actions."""

from __future__ import annotations

from ..contracts import ElementCandidate, WebStateError
from .models import RiskAssessment, RiskCategory, RiskLevel
from .sensitive import SensitiveDataFilter


_BASE_SCORES = {
    "hover": 0.05,
    "scroll": 0.05,
    "wait": 0.05,
    "back": 0.15,
    "forward": 0.15,
    "open": 0.20,
    "navigate": 0.25,
    "select": 0.25,
    "type": 0.35,
    "submit": 0.45,
    "click": 0.15,
}
_HIGH_IMPACT = {
    RiskCategory.CREDENTIALS,
    RiskCategory.FINANCIAL,
    RiskCategory.DESTRUCTIVE,
    RiskCategory.EXTERNAL_COMMUNICATION,
}


class RiskScorer:
    def __init__(self, *, sensitive_filter: SensitiveDataFilter | None = None) -> None:
        self.sensitive_filter = sensitive_filter or SensitiveDataFilter()

    def score(
        self,
        candidate: ElementCandidate | None,
        action: str,
        *,
        input_is_sensitive: bool = False,
    ) -> RiskAssessment:
        if not isinstance(action, str) or action.casefold() not in _BASE_SCORES:
            return RiskAssessment(
                RiskLevel.CRITICAL,
                1.0,
                (RiskCategory.UNKNOWN,),
                ("unknown_action",),
                True,
            )
        action = action.casefold()
        if not isinstance(input_is_sensitive, bool):
            raise WebStateError("input_is_sensitive must be boolean")
        categories: list[RiskCategory] = []
        reasons: list[str] = []
        score = _BASE_SCORES[action]
        if action in {"navigate", "open", "back", "forward"}:
            categories.append(RiskCategory.NAVIGATION)
            reasons.append("navigation_action")
        if candidate is not None:
            classification = self.sensitive_filter.classify_candidate(candidate)
            for category in classification.categories:
                if category not in categories:
                    categories.append(category)
            reasons.extend(classification.reason_codes)
            if classification.contains_page_instruction:
                score = 1.0
        if input_is_sensitive:
            if RiskCategory.CREDENTIALS not in categories:
                categories.append(RiskCategory.CREDENTIALS)
            reasons.append("sensitive_input_declared")
        if not categories:
            categories.append(RiskCategory.NAVIGATION)
            reasons.append("ordinary_action")
        if RiskCategory.PAGE_INSTRUCTION in categories:
            level = RiskLevel.CRITICAL
            score = 1.0
            requires_approval = True
        elif any(category in _HIGH_IMPACT for category in categories):
            level = RiskLevel.CRITICAL
            score = max(score, 0.90)
            requires_approval = True
        elif RiskCategory.AUTHENTICATION in categories or action in {"submit", "type"}:
            level = RiskLevel.HIGH
            score = max(score, 0.70)
            requires_approval = True
        elif action in {"navigate", "open", "back", "forward", "select"}:
            level = RiskLevel.MEDIUM
            requires_approval = False
        else:
            level = RiskLevel.LOW
            requires_approval = False
        return RiskAssessment(level, min(1.0, score), tuple(dict.fromkeys(categories)), tuple(dict.fromkeys(reasons)), requires_approval)


__all__ = ["RiskScorer"]
