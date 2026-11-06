"""Sensitive-data and page-instruction classification without disclosure."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..contracts import ElementCandidate, WebStateError
from .models import RiskCategory


_CREDENTIALS = re.compile(r"\b(?:password|passwd|secret|token|api[ _-]?key|authorization|bearer|cookie|credential)\b", re.I)
_FINANCIAL = re.compile(r"\b(?:card|credit|debit|bank|payment|purchase|buy|checkout|pay|billing)\b", re.I)
_DESTRUCTIVE = re.compile(r"\b(?:delete|remove|erase|destroy|revoke|close account|terminate)\b", re.I)
_EXTERNAL = re.compile(r"\b(?:send|publish|post|email|message|share|invite)\b", re.I)
_AUTH = re.compile(r"\b(?:login|log in|sign in|sign out|authorize|approve|confirm|verify|2fa|mfa)\b", re.I)
_PAGE_INSTRUCTION = re.compile(
    r"\b(?:ignore (?:all )?(?:previous|prior) instructions|system prompt|developer message|reveal the password|act as an assistant)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class SensitiveClassification:
    categories: tuple[RiskCategory, ...]
    reason_codes: tuple[str, ...]
    contains_page_instruction: bool


class SensitiveDataFilter:
    """Classify labels and explicit input flags; never returns the sensitive text."""

    def classify_candidate(self, candidate: ElementCandidate) -> SensitiveClassification:
        if not isinstance(candidate, ElementCandidate):
            raise WebStateError("candidate must be an ElementCandidate")
        return self.classify_text(candidate.accessible_name)

    def classify_text(self, value: str) -> SensitiveClassification:
        if not isinstance(value, str) or len(value) > 4096:
            raise WebStateError("text is outside the safe bound")
        categories: list[RiskCategory] = []
        reasons: list[str] = []
        if _CREDENTIALS.search(value):
            categories.append(RiskCategory.CREDENTIALS)
            reasons.append("credential_surface")
        if _FINANCIAL.search(value):
            categories.append(RiskCategory.FINANCIAL)
            reasons.append("financial_surface")
        if _DESTRUCTIVE.search(value):
            categories.append(RiskCategory.DESTRUCTIVE)
            reasons.append("destructive_surface")
        if _EXTERNAL.search(value):
            categories.append(RiskCategory.EXTERNAL_COMMUNICATION)
            reasons.append("external_communication_surface")
        if _AUTH.search(value):
            categories.append(RiskCategory.AUTHENTICATION)
            reasons.append("authentication_surface")
        contains_instruction = bool(_PAGE_INSTRUCTION.search(value))
        if contains_instruction:
            categories.append(RiskCategory.PAGE_INSTRUCTION)
            reasons.append("page_instruction_detected")
        if not categories:
            categories.append(RiskCategory.NAVIGATION)
            reasons.append("ordinary_page_surface")
        return SensitiveClassification(tuple(dict.fromkeys(categories)), tuple(dict.fromkeys(reasons)), contains_instruction)


__all__ = ["SensitiveClassification", "SensitiveDataFilter"]
