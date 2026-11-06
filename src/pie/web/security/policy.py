"""Fail-closed policy checks independent from relevance ranking."""

from __future__ import annotations

from ..contracts import (
    BrowserSession,
    ElementCandidate,
    ElementSupport,
    PageSnapshot,
    ReferenceState,
    SessionState,
    SnapshotState,
    TaskIntent,
    WebStateError,
)
from .models import PolicyEvaluation, RiskAssessment, RiskCategory


class PolicyEngine:
    def __init__(self, *, max_navigation_steps: int = 8) -> None:
        if not isinstance(max_navigation_steps, int) or isinstance(max_navigation_steps, bool) or not 1 <= max_navigation_steps <= 64:
            raise WebStateError("max_navigation_steps is outside the safe bound")
        self.max_navigation_steps = max_navigation_steps

    def evaluate(
        self,
        session: BrowserSession,
        snapshot: PageSnapshot,
        intent: TaskIntent,
        candidate: ElementCandidate | None,
        *,
        action: str,
        risk: RiskAssessment,
        origin_allowed: bool,
        origin_reason: str,
        navigation_steps: int = 0,
    ) -> PolicyEvaluation:
        reasons: list[str] = []
        if not isinstance(action, str) or action.casefold() not in {"back", "click", "forward", "hover", "navigate", "open", "scroll", "select", "submit", "type", "wait"}:
            return PolicyEvaluation(False, False, ("unknown_action",))
        action = action.casefold()
        if not isinstance(session, BrowserSession) or not isinstance(snapshot, PageSnapshot) or not isinstance(intent, TaskIntent):
            raise WebStateError("invalid policy inputs")
        if session.state is not SessionState.READY:
            reasons.append("session_not_ready")
        if snapshot.state is not SnapshotState.CURRENT:
            reasons.append("snapshot_not_current")
        if session.session_id != snapshot.session_id or session.current_page_id != snapshot.page_id:
            reasons.append("session_page_mismatch")
        if intent.session_id != session.session_id or (intent.page_id is not None and intent.page_id != snapshot.page_id):
            reasons.append("intent_scope_mismatch")
        if intent.action is not None and intent.action != action:
            reasons.append("intent_action_mismatch")
        if not origin_allowed:
            reasons.append(origin_reason)
        if isinstance(navigation_steps, bool) or not isinstance(navigation_steps, int) or not 0 <= navigation_steps <= self.max_navigation_steps:
            reasons.append("navigation_limit")
        elif action in {"navigate", "open", "back", "forward"} and navigation_steps >= self.max_navigation_steps:
            reasons.append("navigation_limit")
        needs_candidate = action not in {"navigate", "open", "back", "forward", "scroll", "wait"}
        if needs_candidate and candidate is None:
            reasons.append("target_required")
        if candidate is not None:
            if candidate.session_id != session.session_id or candidate.page_id != snapshot.page_id or candidate.snapshot_id != snapshot.snapshot_id:
                reasons.append("target_scope_mismatch")
            if candidate.reference_state is not ReferenceState.CURRENT:
                reasons.append("stale_reference")
            if candidate.support is not ElementSupport.SUPPORTED:
                reasons.append("unsupported_target")
            if not candidate.visible:
                reasons.append("target_not_visible")
            if not candidate.enabled:
                reasons.append("target_not_enabled")
            if action not in candidate.available_actions and action not in {"hover", "scroll", "wait"}:
                reasons.append("action_not_declared")
            classification_categories = set(risk.categories)
            if RiskCategory.PAGE_INSTRUCTION in classification_categories:
                reasons.append("page_instruction_ignored")
        if reasons:
            return PolicyEvaluation(False, False, tuple(dict.fromkeys(reasons)))
        if any(
            category in risk.categories
            for category in (
                RiskCategory.CREDENTIALS,
                RiskCategory.FINANCIAL,
                RiskCategory.DESTRUCTIVE,
                RiskCategory.EXTERNAL_COMMUNICATION,
                RiskCategory.PAGE_INSTRUCTION,
                RiskCategory.UNKNOWN,
            )
        ) or risk.score >= 0.80:
            return PolicyEvaluation(False, False, tuple(dict.fromkeys((*risk.reasons, "high_impact_denied"))))
        if risk.requires_approval:
            return PolicyEvaluation(False, True, tuple(dict.fromkeys((*risk.reasons, "explicit_approval_required"))))
        if action in {"click", "select", "type", "submit"}:
            return PolicyEvaluation(False, True, ("mutation_requires_approval",))
        return PolicyEvaluation(True, False, ("policy_allowed",))


__all__ = ["PolicyEngine"]
