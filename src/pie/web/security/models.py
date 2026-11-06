"""Bounded security and approval models for PIE Web Intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..contracts import WebStateError


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskCategory(str, Enum):
    NAVIGATION = "navigation"
    AUTHENTICATION = "authentication"
    CREDENTIALS = "credentials"
    FINANCIAL = "financial"
    DESTRUCTIVE = "destructive"
    EXTERNAL_COMMUNICATION = "external_communication"
    PAGE_INSTRUCTION = "page_instruction"
    UNKNOWN = "unknown"


class SecurityDecisionStatus(str, Enum):
    ALLOWED = "ALLOWED"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    level: RiskLevel
    score: float
    categories: tuple[RiskCategory, ...]
    reasons: tuple[str, ...]
    requires_approval: bool

    def __post_init__(self) -> None:
        if not isinstance(self.level, RiskLevel):
            raise WebStateError("risk level must be a RiskLevel")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)) or not 0.0 <= float(self.score) <= 1.0:
            raise WebStateError("risk score must be between 0 and 1")
        if not self.categories or len(self.categories) > 8 or not all(isinstance(item, RiskCategory) for item in self.categories):
            raise WebStateError("risk categories are outside the safe bound")
        if not self.reasons or len(self.reasons) > 16 or not all(isinstance(item, str) and item for item in self.reasons):
            raise WebStateError("risk reasons are outside the safe bound")
        if not isinstance(self.requires_approval, bool):
            raise WebStateError("requires_approval must be boolean")


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    allowed: bool
    requires_approval: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool) or not isinstance(self.requires_approval, bool):
            raise WebStateError("policy flags must be boolean")
        if not self.reason_codes or len(self.reason_codes) > 24:
            raise WebStateError("policy reason codes are outside the safe bound")
        if not all(isinstance(item, str) and item for item in self.reason_codes):
            raise WebStateError("policy reason codes must be non-empty strings")
        if self.allowed and self.requires_approval:
            raise WebStateError("an allowed policy cannot still require approval")


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    request_id: str
    fingerprint: str
    session_id: str
    page_id: str
    snapshot_id: str
    target_ref: str | None
    categories: tuple[RiskCategory, ...]
    status: str = "PENDING"

    def __post_init__(self) -> None:
        for name in ("request_id", "fingerprint", "session_id", "page_id", "snapshot_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 128:
                raise WebStateError(f"{name} is outside the safe bound")
        if len(self.fingerprint) != 64 or any(char not in "0123456789abcdef" for char in self.fingerprint):
            raise WebStateError("fingerprint must be a lowercase SHA-256 digest")
        if self.target_ref is not None and (not isinstance(self.target_ref, str) or not self.target_ref or len(self.target_ref) > 128):
            raise WebStateError("target_ref is outside the safe bound")
        if not self.categories or not all(isinstance(item, RiskCategory) for item in self.categories):
            raise WebStateError("approval categories are invalid")
        if self.status not in {"PENDING", "APPROVED", "CONSUMED", "REJECTED"}:
            raise WebStateError("approval status is invalid")


@dataclass(frozen=True, slots=True)
class SecurityDecision:
    status: SecurityDecisionStatus
    action: str
    session_id: str
    page_id: str
    snapshot_id: str
    target_ref: str | None
    origin: str
    risk: RiskAssessment
    reason_codes: tuple[str, ...]
    fingerprint: str
    approval_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, SecurityDecisionStatus):
            raise WebStateError("decision status must be a SecurityDecisionStatus")
        for name in ("action", "session_id", "page_id", "snapshot_id", "origin", "fingerprint"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > (128 if name != "origin" else 4096):
                raise WebStateError(f"{name} is outside the safe bound")
        if self.target_ref is not None and (not isinstance(self.target_ref, str) or not self.target_ref or len(self.target_ref) > 128):
            raise WebStateError("target_ref is outside the safe bound")
        if not isinstance(self.risk, RiskAssessment):
            raise WebStateError("risk must be a RiskAssessment")
        if not self.reason_codes or len(self.reason_codes) > 24:
            raise WebStateError("decision reason codes are outside the safe bound")
        if len(self.fingerprint) != 64 or any(char not in "0123456789abcdef" for char in self.fingerprint):
            raise WebStateError("fingerprint must be a lowercase SHA-256 digest")
        if self.approval_id is not None and (not isinstance(self.approval_id, str) or not self.approval_id or len(self.approval_id) > 128):
            raise WebStateError("approval_id is outside the safe bound")


__all__ = [
    "ApprovalRequest",
    "PolicyEvaluation",
    "RiskAssessment",
    "RiskCategory",
    "RiskLevel",
    "SecurityDecision",
    "SecurityDecisionStatus",
]
