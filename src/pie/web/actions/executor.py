"""Execute only after a fresh security decision and verify the driver outcome."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..contracts import (
    ActionResult,
    ActionStatus,
    BrowserSession,
    ElementCandidate,
    ExecutionState,
    PageSnapshot,
    TaskIntent,
    VerificationState,
    WebStateError,
)
from ..security.models import SecurityDecisionStatus
from .models import ActionPlan, DriverOutcome
from .preflight import PreflightValidator
from .verifier import PostActionVerifier


@runtime_checkable
class ActionDriver(Protocol):
    def execute(self, plan: ActionPlan, input_value: str | None = None) -> DriverOutcome: ...


class ActionExecutor:
    def __init__(self, driver: ActionDriver, *, preflight: PreflightValidator | None = None, verifier: PostActionVerifier | None = None) -> None:
        if not isinstance(driver, ActionDriver):
            raise WebStateError("driver must implement ActionDriver")
        self.driver = driver
        self.preflight = preflight or PreflightValidator()
        self.verifier = verifier or PostActionVerifier()

    def execute(
        self,
        plan: ActionPlan,
        *,
        session: BrowserSession,
        before: PageSnapshot,
        intent: TaskIntent,
        candidate: ElementCandidate | None = None,
        target_url: str | None = None,
        navigation_steps: int = 0,
        approval_id: str | None = None,
        input_value: str | None = None,
    ) -> ActionResult:
        try:
            decision = self.preflight.validate(
                plan, session, before, intent, candidate,
                target_url=target_url, navigation_steps=navigation_steps, approval_id=approval_id,
            )
        except WebStateError:
            return self._blocked(plan, "stale_reference")
        if decision.status is SecurityDecisionStatus.BLOCKED:
            return self._blocked(plan, "action_blocked")
        if decision.status is not SecurityDecisionStatus.ALLOWED:
            return self._blocked(plan, "action_rejected")
        try:
            outcome = self.driver.execute(plan, input_value)
        except Exception:
            return ActionResult(
                plan.action_id, plan.intent_id, ActionStatus.FAILED, ExecutionState.STARTED,
                VerificationState.NOT_RUN, plan.session_id, plan.page_id, plan.snapshot_id,
                target_ref=plan.target_ref, error_code="execution_failed",
            )
        if outcome.execution_state is ExecutionState.UNKNOWN:
            return ActionResult(
                plan.action_id, plan.intent_id, ActionStatus.TIMEOUT, ExecutionState.UNKNOWN,
                VerificationState.NOT_RUN, plan.session_id, plan.page_id, plan.snapshot_id,
                target_ref=plan.target_ref, latency_ms=outcome.latency_ms, error_code="timeout",
            )
        verified = self.verifier.verify(plan, before, outcome)
        if not verified:
            return ActionResult(
                plan.action_id, plan.intent_id, ActionStatus.FAILED, ExecutionState.COMPLETED,
                VerificationState.FAILED, plan.session_id, plan.page_id, plan.snapshot_id,
                snapshot_after=outcome.after_snapshot_id, target_ref=plan.target_ref,
                latency_ms=outcome.latency_ms, error_code="verification_failed",
            )
        return ActionResult(
            plan.action_id, plan.intent_id, ActionStatus.SUCCEEDED, ExecutionState.COMPLETED,
            VerificationState.VERIFIED, plan.session_id, plan.page_id, plan.snapshot_id,
            snapshot_after=outcome.after_snapshot_id, target_ref=plan.target_ref,
            latency_ms=outcome.latency_ms,
        )

    @staticmethod
    def _blocked(plan: ActionPlan, code: str) -> ActionResult:
        status = ActionStatus.BLOCKED if code == "action_blocked" else ActionStatus.REJECTED if code == "action_rejected" else ActionStatus.STALE
        return ActionResult(
            plan.action_id, plan.intent_id, status, ExecutionState.NOT_STARTED,
            VerificationState.NOT_RUN, plan.session_id, plan.page_id, plan.snapshot_id,
            target_ref=plan.target_ref, error_code=code if code != "stale_reference" else "stale_reference",
        )


__all__ = ["ActionDriver", "ActionExecutor"]
