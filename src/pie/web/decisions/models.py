"""Bounded semantic-decision contracts with optional external classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..contracts import WebStateError


class DecisionSource(str, Enum):
    LOCAL = "LOCAL"
    EXTERNAL = "EXTERNAL"
    FALLBACK = "FALLBACK"


class DecisionRoute(str, Enum):
    LOCAL = "LOCAL"
    OPTIONAL_CLASSIFIER = "OPTIONAL_CLASSIFIER"
    MORE_CONTEXT = "MORE_CONTEXT"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class DecisionFeature:
    ref: str
    label: str
    role: str
    region: str | None
    action_count: int
    relevance_score: float
    sensitive: bool = False

    def __post_init__(self) -> None:
        for name in ("ref", "label", "role"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > (128 if name == "ref" else 256):
                raise WebStateError(f"{name} is outside the safe bound")
        if self.region is not None and (not isinstance(self.region, str) or len(self.region) > 128):
            raise WebStateError("region is outside the safe bound")
        if not isinstance(self.action_count, int) or isinstance(self.action_count, bool) or not 0 <= self.action_count <= 8:
            raise WebStateError("action_count is outside the safe bound")
        if isinstance(self.relevance_score, bool) or not isinstance(self.relevance_score, (int, float)) or not 0.0 <= float(self.relevance_score) <= 1.0:
            raise WebStateError("relevance_score must be between 0 and 1")
        if not isinstance(self.sensitive, bool):
            raise WebStateError("sensitive must be boolean")


@dataclass(frozen=True, slots=True)
class DecisionBatch:
    snapshot_id: str
    query: str
    features: tuple[DecisionFeature, ...]
    external_safe: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id or len(self.snapshot_id) > 128:
            raise WebStateError("snapshot_id is outside the safe bound")
        if not isinstance(self.query, str) or not self.query.strip() or len(self.query) > 256:
            raise WebStateError("query is outside the safe bound")
        if not isinstance(self.features, tuple) or not 1 <= len(self.features) <= 16 or not all(isinstance(item, DecisionFeature) for item in self.features):
            raise WebStateError("features are outside the safe bound")
        if not isinstance(self.external_safe, bool):
            raise WebStateError("external_safe must be boolean")
        if any(item.sensitive for item in self.features) and self.external_safe:
            raise WebStateError("sensitive features cannot be externally safe")

    def external_payload(self) -> tuple[dict[str, object], ...]:
        if not self.external_safe:
            raise WebStateError("external classification is not authorized for this batch")
        return tuple(
            {
                "ref": item.ref,
                "label": item.label,
                "role": item.role,
                "region": item.region,
                "action_count": item.action_count,
                "relevance_score": item.relevance_score,
            }
            for item in self.features
        )


@dataclass(frozen=True, slots=True)
class SemanticDecision:
    ref: str
    route: DecisionRoute
    source: DecisionSource
    confidence: float
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.ref, str) or not self.ref or len(self.ref) > 128:
            raise WebStateError("ref is outside the safe bound")
        if not isinstance(self.route, DecisionRoute) or not isinstance(self.source, DecisionSource):
            raise WebStateError("invalid decision route or source")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)) or not 0.0 <= float(self.confidence) <= 1.0:
            raise WebStateError("confidence must be between 0 and 1")
        if not isinstance(self.reason_code, str) or not self.reason_code or len(self.reason_code) > 128:
            raise WebStateError("reason_code is outside the safe bound")
        if self.source is DecisionSource.EXTERNAL and self.route is not DecisionRoute.LOCAL:
            raise WebStateError("external classification must return a local decision route")


__all__ = ["DecisionBatch", "DecisionFeature", "DecisionRoute", "DecisionSource", "SemanticDecision"]
