"""Create action plans from declarative intents and current evidence."""

from __future__ import annotations

from ..contracts import ElementCandidate, PageSnapshot, TaskIntent, WebStateError
from ..security.gate import SecurityGate
from .models import ActionPlan


class ActionPlanner:
    def __init__(self, *, security: SecurityGate | None = None) -> None:
        self.security = security or SecurityGate()

    def plan(
        self,
        *,
        action_id: str,
        session,
        snapshot: PageSnapshot,
        intent: TaskIntent,
        candidate: ElementCandidate | None = None,
        action: str | None = None,
        target_url: str | None = None,
        input_is_sensitive: bool = False,
        navigation_steps: int = 0,
        approval_id: str | None = None,
    ) -> ActionPlan:
        if not isinstance(action_id, str) or not action_id or len(action_id) > 128:
            raise WebStateError("action_id is outside the safe bound")
        decision = self.security.authorize(
            session,
            snapshot,
            intent,
            candidate,
            action=action,
            target_url=target_url,
            input_is_sensitive=input_is_sensitive,
            navigation_steps=navigation_steps,
            approval_id=approval_id,
        )
        return ActionPlan(
            action_id,
            intent.intent_id,
            session.session_id,
            snapshot.page_id,
            snapshot.snapshot_id,
            snapshot.generation,
            candidate.ref if candidate is not None else None,
            decision.action,
            intent.expected_transition,
            input_is_sensitive,
            decision.fingerprint,
            decision.status,
        )


__all__ = ["ActionPlanner"]
