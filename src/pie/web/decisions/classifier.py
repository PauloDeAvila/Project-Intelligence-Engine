"""Optional classifier boundary; no provider or network dependency by default."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..contracts import WebStateError
from .models import DecisionBatch, SemanticDecision


@runtime_checkable
class ClassifierAdapter(Protocol):
    def classify(self, batch: DecisionBatch) -> tuple[SemanticDecision, ...]: ...


def validate_classifier_result(batch: DecisionBatch, values: tuple[SemanticDecision, ...]) -> tuple[SemanticDecision, ...]:
    if not isinstance(values, tuple) or len(values) != len(batch.features):
        raise WebStateError("classifier must return one decision per feature")
    refs = tuple(item.ref for item in batch.features)
    if tuple(item.ref for item in values) != refs:
        raise WebStateError("classifier result order or references changed")
    return values


__all__ = ["ClassifierAdapter", "validate_classifier_result"]
