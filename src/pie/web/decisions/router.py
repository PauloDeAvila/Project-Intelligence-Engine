"""Fail-closed routing between local, optional classifier and more context."""

from __future__ import annotations

from ..contracts import WebStateError
from .models import DecisionRoute


class FallbackRouter:
    def __init__(self, *, confidence_threshold: float = 0.75) -> None:
        if isinstance(confidence_threshold, bool) or not isinstance(confidence_threshold, (int, float)) or not 0.5 <= confidence_threshold <= 0.99:
            raise WebStateError("confidence_threshold is outside the safe bound")
        self.confidence_threshold = float(confidence_threshold)

    def route(self, *, confidence: float, sensitive: bool, classifier_available: bool, allow_external: bool) -> DecisionRoute:
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
            raise WebStateError("confidence must be between 0 and 1")
        if not isinstance(sensitive, bool) or not isinstance(classifier_available, bool) or not isinstance(allow_external, bool):
            raise WebStateError("routing flags must be boolean")
        if sensitive:
            return DecisionRoute.BLOCKED
        if confidence >= self.confidence_threshold:
            return DecisionRoute.LOCAL
        if classifier_available and allow_external:
            return DecisionRoute.OPTIONAL_CLASSIFIER
        return DecisionRoute.MORE_CONTEXT


__all__ = ["FallbackRouter"]
