"""Compact, provenance-rich web evidence pack models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..contracts import SnapshotState, WebStateError


class PermissionState(str, Enum):
    NOT_CHECKED = "NOT_CHECKED"
    ALLOWED = "ALLOWED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class EvidenceProvenance:
    session_id: str
    page_id: str
    snapshot_id: str
    snapshot_sha256: str
    generation: int
    origin: str
    path: str
    captured_at: str
    state: SnapshotState

    def __post_init__(self) -> None:
        for name in ("session_id", "page_id", "snapshot_id", "origin", "path", "captured_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > (4096 if name in {"origin", "path", "captured_at"} else 128):
                raise WebStateError(f"{name} is outside the safe bound")
        if len(self.snapshot_sha256) != 64 or any(char not in "0123456789abcdef" for char in self.snapshot_sha256):
            raise WebStateError("snapshot_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(self.generation, int) or isinstance(self.generation, bool) or self.generation < 0:
            raise WebStateError("generation must be a non-negative integer")
        if not isinstance(self.state, SnapshotState):
            raise WebStateError("state must be a SnapshotState")


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    ref: str
    label: str
    role: str
    region: str | None
    actions: tuple[str, ...]
    relevance_score: float
    risk_categories: tuple[str, ...]
    permission: PermissionState
    estimated_chars: int

    def __post_init__(self) -> None:
        for name in ("ref", "label", "role"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 512:
                raise WebStateError(f"{name} is outside the safe bound")
        if self.region is not None and (not isinstance(self.region, str) or len(self.region) > 128):
            raise WebStateError("region is outside the safe bound")
        if not isinstance(self.actions, tuple) or len(self.actions) > 8 or not all(isinstance(item, str) and item for item in self.actions):
            raise WebStateError("actions are outside the safe bound")
        if isinstance(self.relevance_score, bool) or not isinstance(self.relevance_score, (int, float)) or not 0.0 <= float(self.relevance_score) <= 1.0:
            raise WebStateError("relevance_score must be between 0 and 1")
        if not isinstance(self.risk_categories, tuple) or len(self.risk_categories) > 8 or not all(isinstance(item, str) and item for item in self.risk_categories):
            raise WebStateError("risk_categories are outside the safe bound")
        if not isinstance(self.permission, PermissionState):
            raise WebStateError("permission must be a PermissionState")
        if not isinstance(self.estimated_chars, int) or isinstance(self.estimated_chars, bool) or not 1 <= self.estimated_chars <= 4096:
            raise WebStateError("estimated_chars is outside the safe bound")


@dataclass(frozen=True, slots=True)
class EvidenceOmission:
    ref: str
    reason: str
    score: float
    expandable: bool

    def __post_init__(self) -> None:
        if not isinstance(self.ref, str) or not self.ref or len(self.ref) > 128:
            raise WebStateError("omission ref is outside the safe bound")
        if self.reason not in {"below_threshold", "budget", "duplicate", "limit", "unsupported", "source_omitted"}:
            raise WebStateError("unsupported evidence omission reason")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)) or not 0.0 <= float(self.score) <= 1.0:
            raise WebStateError("omission score must be between 0 and 1")
        if not isinstance(self.expandable, bool):
            raise WebStateError("expandable must be boolean")


@dataclass(frozen=True, slots=True)
class ExpansionPlan:
    available: bool
    omitted_refs: tuple[str, ...]
    suggested_budget_chars: int

    def __post_init__(self) -> None:
        if not isinstance(self.available, bool) or len(self.omitted_refs) > 512:
            raise WebStateError("invalid expansion plan")
        if not all(isinstance(item, str) and item for item in self.omitted_refs):
            raise WebStateError("expansion refs must be non-empty strings")
        if not isinstance(self.suggested_budget_chars, int) or not 1 <= self.suggested_budget_chars <= 1_000_000:
            raise WebStateError("suggested budget is outside the safe bound")


@dataclass(frozen=True, slots=True)
class WebEvidencePack:
    pack_id: str
    query: str
    provenance: EvidenceProvenance
    items: tuple[EvidenceItem, ...]
    omissions: tuple[EvidenceOmission, ...]
    context_budget_chars: int
    used_chars: int
    expansion: ExpansionPlan
    execution_authorized: bool = False

    def __post_init__(self) -> None:
        for name in ("pack_id", "query"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > (128 if name == "pack_id" else 256):
                raise WebStateError(f"{name} is outside the safe bound")
        if not isinstance(self.provenance, EvidenceProvenance):
            raise WebStateError("provenance must be EvidenceProvenance")
        if not isinstance(self.items, tuple) or len(self.items) > 32 or not all(isinstance(item, EvidenceItem) for item in self.items):
            raise WebStateError("items are outside the safe bound")
        if not isinstance(self.omissions, tuple) or len(self.omissions) > 512 or not all(isinstance(item, EvidenceOmission) for item in self.omissions):
            raise WebStateError("omissions are outside the safe bound")
        if not isinstance(self.context_budget_chars, int) or not 1 <= self.context_budget_chars <= 1_000_000:
            raise WebStateError("context budget is outside the safe bound")
        if not isinstance(self.used_chars, int) or self.used_chars < 0 or self.used_chars > self.context_budget_chars:
            raise WebStateError("used_chars exceeds the context budget")
        if not isinstance(self.expansion, ExpansionPlan):
            raise WebStateError("expansion must be an ExpansionPlan")
        if self.execution_authorized is not False:
            raise WebStateError("evidence delivery cannot authorize execution")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "pie-web-evidence-pack-v1",
            "pack_id": self.pack_id,
            "query": self.query,
            "provenance": {
                "session_id": self.provenance.session_id,
                "page_id": self.provenance.page_id,
                "snapshot_id": self.provenance.snapshot_id,
                "snapshot_sha256": self.provenance.snapshot_sha256,
                "generation": self.provenance.generation,
                "origin": self.provenance.origin,
                "path": self.provenance.path,
                "captured_at": self.provenance.captured_at,
                "state": self.provenance.state.value,
            },
            "items": [
                {
                    "ref": item.ref,
                    "label": item.label,
                    "role": item.role,
                    "region": item.region,
                    "actions": list(item.actions),
                    "relevance_score": item.relevance_score,
                    "risk_categories": list(item.risk_categories),
                    "permission": item.permission.value,
                }
                for item in self.items
            ],
            "omissions": [
                {"ref": item.ref, "reason": item.reason, "score": item.score, "expandable": item.expandable}
                for item in self.omissions
            ],
            "context_budget_chars": self.context_budget_chars,
            "used_chars": self.used_chars,
            "expansion": {
                "available": self.expansion.available,
                "omitted_refs": list(self.expansion.omitted_refs),
                "suggested_budget_chars": self.expansion.suggested_budget_chars,
            },
            "execution_authorized": False,
        }


__all__ = [
    "EvidenceItem",
    "EvidenceOmission",
    "EvidenceProvenance",
    "ExpansionPlan",
    "PermissionState",
    "WebEvidencePack",
]
