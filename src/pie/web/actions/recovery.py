"""Safe recovery plans with no automatic retry of non-idempotent actions."""

from __future__ import annotations

from ..contracts import ActionResult, ActionStatus, WebStateError
from .models import ActionPlan, RecoveryAction, RecoveryPlan


class RecoveryController:
    def recover(self, plan: ActionPlan, result: ActionResult) -> RecoveryPlan:
        if not isinstance(plan, ActionPlan) or not isinstance(result, ActionResult):
            raise WebStateError("plan and result are required")
        if result.status is ActionStatus.STALE:
            return RecoveryPlan(RecoveryAction.REFRESH_SNAPSHOT, "stale_reference", False)
        if result.status is ActionStatus.REJECTED:
            return RecoveryPlan(RecoveryAction.REQUEST_APPROVAL, "approval_required", False)
        if result.status in {ActionStatus.BLOCKED, ActionStatus.FAILED, ActionStatus.TIMEOUT}:
            return RecoveryPlan(RecoveryAction.STOP, result.error_code or "action_failed", False)
        return RecoveryPlan(RecoveryAction.NONE, "none", False)


__all__ = ["RecoveryController"]
