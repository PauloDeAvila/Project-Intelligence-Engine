"""Post-action verification that observes effects instead of assuming success."""

from __future__ import annotations

from ..contracts import ExecutionState, PageSnapshot, WebStateError
from .models import ActionPlan, DriverOutcome


class PostActionVerifier:
    def verify(self, plan: ActionPlan, before: PageSnapshot, outcome: DriverOutcome) -> bool:
        if not isinstance(plan, ActionPlan) or not isinstance(before, PageSnapshot) or not isinstance(outcome, DriverOutcome):
            raise WebStateError("invalid post-action verification inputs")
        if outcome.execution_state is not ExecutionState.COMPLETED:
            return False
        if outcome.after_snapshot_id is None or outcome.after_page_id is None:
            return False
        if outcome.after_page_id != before.page_id:
            return False
        if plan.expected_transition is not None:
            return outcome.observed_transition == plan.expected_transition
        return outcome.after_snapshot_id != before.snapshot_id or outcome.observed_transition is not None


__all__ = ["PostActionVerifier"]
