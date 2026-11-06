"""Bounded action plans and driver outcomes for controlled web execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..contracts import ExecutionState, WebStateError
from ..security.models import SecurityDecisionStatus


class RecoveryAction(str, Enum):
    NONE = "NONE"
    REFRESH_SNAPSHOT = "REFRESH_SNAPSHOT"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    STOP = "STOP"


@dataclass(frozen=True, slots=True)
class ActionPlan:
    action_id: str
    intent_id: str
    session_id: str
    page_id: str
    snapshot_id: str
    generation: int
    target_ref: str | None
    action: str
    expected_transition: str | None
    input_is_sensitive: bool
    security_fingerprint: str
    security_status: SecurityDecisionStatus

    def __post_init__(self) -> None:
        for name in ("action_id", "intent_id", "session_id", "page_id", "snapshot_id", "action", "security_fingerprint"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 128:
                raise WebStateError(f"{name} is outside the safe bound")
        if self.target_ref is not None and (not isinstance(self.target_ref, str) or not self.target_ref or len(self.target_ref) > 128):
            raise WebStateError("target_ref is outside the safe bound")
        if self.expected_transition is not None and (not isinstance(self.expected_transition, str) or not self.expected_transition or len(self.expected_transition) > 128):
            raise WebStateError("expected_transition is outside the safe bound")
        if not isinstance(self.generation, int) or isinstance(self.generation, bool) or self.generation < 0:
            raise WebStateError("generation must be a non-negative integer")
        if not isinstance(self.input_is_sensitive, bool) or not isinstance(self.security_status, SecurityDecisionStatus):
            raise WebStateError("invalid action plan security fields")
        if len(self.security_fingerprint) != 64 or any(char not in "0123456789abcdef" for char in self.security_fingerprint):
            raise WebStateError("security_fingerprint must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class DriverOutcome:
    execution_state: ExecutionState
    after_snapshot_id: str | None
    after_page_id: str | None
    observed_transition: str | None
    latency_ms: float = 0.0
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.execution_state, ExecutionState):
            raise WebStateError("execution_state must be an ExecutionState")
        for name in ("after_snapshot_id", "after_page_id", "observed_transition", "error_code"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value or len(value) > 128):
                raise WebStateError(f"{name} is outside the safe bound")
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, (int, float)) or self.latency_ms < 0:
            raise WebStateError("latency_ms must be non-negative")
        if self.execution_state is ExecutionState.COMPLETED and self.error_code is not None:
            raise WebStateError("completed driver outcomes cannot contain errors")


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    action: RecoveryAction
    reason_code: str
    automatic_retry: bool

    def __post_init__(self) -> None:
        if not isinstance(self.action, RecoveryAction) or not isinstance(self.automatic_retry, bool):
            raise WebStateError("invalid recovery plan")
        if not isinstance(self.reason_code, str) or not self.reason_code or len(self.reason_code) > 128:
            raise WebStateError("reason_code is outside the safe bound")
        if self.action is not RecoveryAction.NONE and self.reason_code == "none":
            raise WebStateError("non-empty recovery needs a reason")


__all__ = ["ActionPlan", "DriverOutcome", "RecoveryAction", "RecoveryPlan"]
