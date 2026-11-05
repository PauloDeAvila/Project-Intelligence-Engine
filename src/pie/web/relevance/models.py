"""Immutable quantified-context models with explicit omission provenance."""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import ElementCandidate, SnapshotState, WebStateError


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    candidate: ElementCandidate
    ordinal: int
    score: float
    reasons: tuple[str, ...]
    protected: bool
    estimated_chars: int

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, ElementCandidate):
            raise WebStateError("candidate must be an ElementCandidate")
        if not isinstance(self.ordinal, int) or isinstance(self.ordinal, bool) or self.ordinal < 0:
            raise WebStateError("ordinal must be a non-negative integer")
        if not isinstance(self.score, (int, float)) or isinstance(self.score, bool) or not 0.0 <= float(self.score) <= 1.0:
            raise WebStateError("score must be between 0 and 1")
        if not isinstance(self.reasons, tuple) or not self.reasons or len(self.reasons) > 16:
            raise WebStateError("reasons must be bounded and non-empty")
        if not all(isinstance(reason, str) and reason for reason in self.reasons):
            raise WebStateError("reasons must contain non-empty codes")
        if not isinstance(self.protected, bool):
            raise WebStateError("protected must be boolean")
        if not isinstance(self.estimated_chars, int) or isinstance(self.estimated_chars, bool) or not 1 <= self.estimated_chars <= 4096:
            raise WebStateError("estimated_chars is outside the safe bound")


@dataclass(frozen=True, slots=True)
class OmissionRecord:
    ref: str
    reason: str
    score: float
    expandable: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.ref, str) or not self.ref or len(self.ref) > 128:
            raise WebStateError("ref must be a bounded non-empty string")
        if self.reason not in {"below_threshold", "budget", "duplicate", "limit", "unsupported"}:
            raise WebStateError("reason is not a supported omission code")
        if not isinstance(self.score, (int, float)) or isinstance(self.score, bool) or not 0.0 <= float(self.score) <= 1.0:
            raise WebStateError("score must be between 0 and 1")
        if not isinstance(self.expandable, bool):
            raise WebStateError("expandable must be boolean")


@dataclass(frozen=True, slots=True)
class ReductionResult:
    selected: tuple[ScoredCandidate, ...]
    omitted: tuple[OmissionRecord, ...]
    estimated_chars: int
    budget_exceeded: bool


@dataclass(frozen=True, slots=True)
class QuantifiedWebContext:
    snapshot_id: str
    state: SnapshotState
    query: str
    selected: tuple[ScoredCandidate, ...]
    omissions: tuple[OmissionRecord, ...]
    threshold: float
    context_budget_chars: int
    estimated_chars: int
    ambiguous: bool
    source_omitted_count: int
    expansion_available: bool

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id:
            raise WebStateError("snapshot_id must be non-empty")
        if not isinstance(self.state, SnapshotState):
            raise WebStateError("state must be a SnapshotState")
        if not isinstance(self.query, str) or not self.query.strip() or len(self.query) > 256:
            raise WebStateError("query is outside the safe bound")
        if not isinstance(self.selected, tuple) or len(self.selected) > 32:
            raise WebStateError("selected is outside the safe bound")
        if not isinstance(self.omissions, tuple) or len(self.omissions) > 512:
            raise WebStateError("omissions are outside the safe bound")
        if not isinstance(self.threshold, (int, float)) or not 0.0 <= float(self.threshold) <= 1.0:
            raise WebStateError("threshold must be between 0 and 1")
        if not isinstance(self.context_budget_chars, int) or not 1 <= self.context_budget_chars <= 1_000_000:
            raise WebStateError("context budget is outside the safe bound")
        if not isinstance(self.estimated_chars, int) or self.estimated_chars < 0:
            raise WebStateError("estimated_chars must be non-negative")
        if not isinstance(self.ambiguous, bool) or not isinstance(self.source_omitted_count, int) or self.source_omitted_count < 0:
            raise WebStateError("invalid quantified context state")
        if not isinstance(self.expansion_available, bool):
            raise WebStateError("expansion_available must be boolean")


__all__ = ["OmissionRecord", "QuantifiedWebContext", "ReductionResult", "ScoredCandidate"]
