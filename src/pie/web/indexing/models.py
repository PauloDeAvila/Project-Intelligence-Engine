"""Bounded immutable models for local web search."""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import ElementCandidate, ElementSupport, SnapshotState, WebStateError


@dataclass(frozen=True, slots=True)
class SearchDocument:
    """A tokenized view of one snapshot candidate with no executable metadata."""

    candidate: ElementCandidate
    ordinal: int
    tokens: tuple[str, ...]
    region_tokens: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, ElementCandidate):
            raise WebStateError("candidate must be an ElementCandidate")
        if not isinstance(self.ordinal, int) or isinstance(self.ordinal, bool) or self.ordinal < 0:
            raise WebStateError("ordinal must be a non-negative integer")
        for field_name, values in (("tokens", self.tokens), ("region_tokens", self.region_tokens)):
            if not isinstance(values, tuple) or len(values) > 128:
                raise WebStateError(f"{field_name} must be a bounded tuple")
            if not all(isinstance(value, str) and value for value in values):
                raise WebStateError(f"{field_name} must contain non-empty strings")


@dataclass(frozen=True, slots=True)
class SearchMatch:
    """One ranked candidate and the deterministic reasons for its score."""

    candidate: ElementCandidate
    score: float
    reasons: tuple[str, ...]
    matched_terms: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, ElementCandidate):
            raise WebStateError("candidate must be an ElementCandidate")
        if not isinstance(self.score, (int, float)) or isinstance(self.score, bool):
            raise WebStateError("score must be numeric")
        if not 0.0 <= float(self.score) <= 1.0:
            raise WebStateError("score must be between 0 and 1")
        if not isinstance(self.reasons, tuple) or not self.reasons or len(self.reasons) > 16:
            raise WebStateError("reasons must be a bounded non-empty tuple")
        if not all(isinstance(reason, str) and reason for reason in self.reasons):
            raise WebStateError("reasons must contain non-empty strings")
        if not isinstance(self.matched_terms, tuple) or len(self.matched_terms) > 64:
            raise WebStateError("matched_terms must be a bounded tuple")


@dataclass(frozen=True, slots=True)
class SearchResponse:
    """Deterministic local-search output; ambiguity is explicit."""

    snapshot_id: str
    state: SnapshotState
    matches: tuple[SearchMatch, ...]
    ambiguous: bool
    total_candidates: int
    omitted_candidates: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id:
            raise WebStateError("snapshot_id must be non-empty")
        if not isinstance(self.state, SnapshotState):
            raise WebStateError("state must be a SnapshotState")
        if not isinstance(self.matches, tuple) or len(self.matches) > 32:
            raise WebStateError("matches must be a bounded tuple")
        if not all(isinstance(match, SearchMatch) for match in self.matches):
            raise WebStateError("matches must contain SearchMatch values")
        if not isinstance(self.ambiguous, bool):
            raise WebStateError("ambiguous must be boolean")
        for field_name, value in (("total_candidates", self.total_candidates), ("omitted_candidates", self.omitted_candidates)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise WebStateError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class RegionIndex:
    """Immutable region and role lookup tables for one snapshot."""

    snapshot_id: str
    by_region: tuple[tuple[str, tuple[str, ...]], ...]
    by_role: tuple[tuple[str, tuple[str, ...]], ...]

    def refs_for_region(self, region: str) -> tuple[str, ...]:
        key = region.casefold()
        for name, refs in self.by_region:
            if name == key:
                return refs
        return ()

    def refs_for_role(self, role: str) -> tuple[str, ...]:
        key = role.casefold()
        for name, refs in self.by_role:
            if name == key:
                return refs
        return ()


__all__ = ["RegionIndex", "SearchDocument", "SearchMatch", "SearchResponse"]
