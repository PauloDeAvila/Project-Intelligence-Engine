"""Execute only after a fresh security decision and verify the driver outcome."""

from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable

from ...runtime.replay import ExecutionJournal, ReplayConflict
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
    def __init__(
        self,
        driver: ActionDriver,
        *,
        preflight: PreflightValidator | None = None,
        verifier: PostActionVerifier | None = None,
        journal: ExecutionJournal | None = None,
    ) -> None:
        if not isinstance(driver, ActionDriver):
            raise WebStateError("driver must implement ActionDriver")
        self.driver = driver
        self.preflight = preflight or PreflightValidator()
        self.verifier = verifier or PostActionVerifier()
        self.journal = journal

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
        if self.journal is None:
            return self._execute_driver(plan, before, input_value)
        return self._execute_with_journal(plan, before, input_value)

    def _execute_with_journal(self, plan: ActionPlan, before: PageSnapshot, input_value: str | None) -> ActionResult:
        operation_key = f"{plan.session_id}:{plan.page_id}:{plan.action_id}"
        operation_id = "web-action-" + hashlib.sha256(operation_key.encode("utf-8")).hexdigest()[:32]
        input_bytes = None if input_value is None else input_value.encode("utf-8")
        payload = {
            "action_id": plan.action_id,
            "intent_id": plan.intent_id,
            "session_id": plan.session_id,
            "page_id": plan.page_id,
            "snapshot_id": plan.snapshot_id,
            "action": plan.action,
            "input_sha256": None if input_bytes is None else hashlib.sha256(input_bytes).hexdigest(),
            "input_length": None if input_bytes is None else len(input_bytes),
        }
        try:
            ledger = self.journal.execute_once(
                operation_id, payload,
                lambda: self._safe_action_metadata(plan, before, input_value),
                result_metadata=lambda metadata: metadata,
            )
        except ReplayConflict:
            raise
        except Exception:
            return ActionResult(
                plan.action_id, plan.intent_id, ActionStatus.FAILED, ExecutionState.UNKNOWN,
                VerificationState.NOT_RUN, plan.session_id, plan.page_id, plan.snapshot_id,
                target_ref=plan.target_ref, error_code="journal_error",
            )
        if ledger["status"] == "REQUIRES_RECONCILIATION":
            return ActionResult(
                plan.action_id, plan.intent_id, ActionStatus.FAILED, ExecutionState.UNKNOWN,
                VerificationState.NOT_RUN, plan.session_id, plan.page_id, plan.snapshot_id,
                target_ref=plan.target_ref, error_code="reconciliation_required",
            )
        if ledger["status"] not in {"EXECUTED", "REPLAYED"}:
            return ActionResult(
                plan.action_id, plan.intent_id, ActionStatus.FAILED, ExecutionState.UNKNOWN,
                VerificationState.NOT_RUN, plan.session_id, plan.page_id, plan.snapshot_id,
                target_ref=plan.target_ref, error_code=str(ledger.get("error_code") or "journal_failed"),
            )
        metadata = ledger.get("result_metadata")
        if not isinstance(metadata, dict):
            return ActionResult(
                plan.action_id, plan.intent_id, ActionStatus.FAILED, ExecutionState.UNKNOWN,
                VerificationState.NOT_RUN, plan.session_id, plan.page_id, plan.snapshot_id,
                target_ref=plan.target_ref, error_code="journal_metadata_missing",
            )
        return self._result_from_metadata(plan, metadata)

    def _execute_driver(self, plan: ActionPlan, before: PageSnapshot, input_value: str | None) -> ActionResult:
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

    def _safe_action_metadata(self, plan: ActionPlan, before: PageSnapshot, input_value: str | None) -> dict[str, object]:
        return self._metadata_from_result(self._execute_driver(plan, before, input_value))

    @staticmethod
    def _metadata_from_result(result: ActionResult) -> dict[str, object]:
        return {
            "status": result.status.value,
            "execution_state": result.execution_state.value,
            "verification": result.verification.value,
            "snapshot_after": result.snapshot_after,
            "target_ref": result.target_ref,
            "latency_ms": result.latency_ms,
            "error_code": result.error_code,
        }

    @staticmethod
    def _result_from_metadata(plan: ActionPlan, metadata: dict[str, object]) -> ActionResult:
        expected = {
            "status", "execution_state", "verification", "snapshot_after",
            "target_ref", "latency_ms", "error_code",
        }
        if set(metadata) != expected:
            return ActionResult(
                plan.action_id, plan.intent_id, ActionStatus.FAILED, ExecutionState.UNKNOWN,
                VerificationState.NOT_RUN, plan.session_id, plan.page_id, plan.snapshot_id,
                target_ref=plan.target_ref, error_code="journal_metadata_invalid",
            )
        try:
            return ActionResult(
                plan.action_id, plan.intent_id, ActionStatus(metadata["status"]),
                ExecutionState(metadata["execution_state"]), VerificationState(metadata["verification"]),
                plan.session_id, plan.page_id, plan.snapshot_id,
                snapshot_after=metadata["snapshot_after"], target_ref=metadata["target_ref"],
                latency_ms=metadata["latency_ms"], error_code=metadata["error_code"],
            )
        except (TypeError, ValueError, WebStateError):
            return ActionResult(
                plan.action_id, plan.intent_id, ActionStatus.FAILED, ExecutionState.UNKNOWN,
                VerificationState.NOT_RUN, plan.session_id, plan.page_id, plan.snapshot_id,
                target_ref=plan.target_ref, error_code="journal_metadata_invalid",
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
