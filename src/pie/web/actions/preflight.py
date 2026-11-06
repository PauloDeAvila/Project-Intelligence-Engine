"""Final validation immediately before a driver call."""

from __future__ import annotations

from ..contracts import BrowserSession, ElementCandidate, PageSnapshot, TaskIntent, WebStateError
from ..security.gate import SecurityGate
from ..security.models import SecurityDecision, SecurityDecisionStatus
from .models import ActionPlan


class PreflightValidator:
    def __init__(self, *, security: SecurityGate | None = None) -> None:
        self.security = security or SecurityGate()

    def validate(
        self,
        plan: ActionPlan,
        session: BrowserSession,
        snapshot: PageSnapshot,
        intent: TaskIntent,
        candidate: ElementCandidate | None = None,
        *,
        target_url: str | None = None,
        navigation_steps: int = 0,
        approval_id: str | None = None,
    ) -> SecurityDecision:
        if not isinstance(plan, ActionPlan):
            raise WebStateError("plan must be an ActionPlan")
        if plan.session_id != session.session_id or plan.snapshot_id != snapshot.snapshot_id or plan.generation != snapshot.generation:
            raise WebStateError("action plan is stale")
        if candidate is not None and plan.target_ref != candidate.ref:
            raise WebStateError("action target changed")
        decision = self.security.authorize(
            session,
            snapshot,
            intent,
            candidate,
            action=plan.action,
            target_url=target_url,
            input_is_sensitive=plan.input_is_sensitive,
            navigation_steps=navigation_steps,
            approval_id=approval_id,
        )
        if decision.fingerprint != plan.security_fingerprint:
            raise WebStateError("security fingerprint changed")
        return decision


__all__ = ["PreflightValidator"]
