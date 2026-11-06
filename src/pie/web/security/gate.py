"""Security gate applied immediately before any future browser execution."""

from __future__ import annotations

import hashlib
import json

from ..contracts import BrowserSession, ElementCandidate, PageSnapshot, TaskIntent, WebStateError
from .approval import ApprovalManager
from .models import SecurityDecision, SecurityDecisionStatus
from .origin import OriginGuard
from .policy import PolicyEngine
from .risk import RiskScorer


class SecurityGate:
    """Authorize declarative actions without executing them or trusting page text."""

    POLICY_VERSION = "pie-web-security-v1"

    def __init__(
        self,
        *,
        risk_scorer: RiskScorer | None = None,
        policy: PolicyEngine | None = None,
        origin_guard: OriginGuard | None = None,
        approvals: ApprovalManager | None = None,
    ) -> None:
        self.risk_scorer = risk_scorer or RiskScorer()
        self.policy = policy or PolicyEngine()
        self.origin_guard = origin_guard or OriginGuard()
        self.approvals = approvals or ApprovalManager()

    def authorize(
        self,
        session: BrowserSession,
        snapshot: PageSnapshot,
        intent: TaskIntent,
        candidate: ElementCandidate | None = None,
        *,
        action: str | None = None,
        target_url: str | None = None,
        input_is_sensitive: bool = False,
        navigation_steps: int = 0,
        approval_id: str | None = None,
    ) -> SecurityDecision:
        if not all(isinstance(value, expected) for value, expected in ((session, BrowserSession), (snapshot, PageSnapshot), (intent, TaskIntent))):
            raise WebStateError("session, snapshot and intent are required")
        selected_action = (action or intent.action or "").casefold()
        if not selected_action:
            selected_action = "unknown"
        origin = self.origin_guard.check(session, snapshot, target_url=target_url)
        risk = self.risk_scorer.score(candidate, selected_action, input_is_sensitive=input_is_sensitive)
        evaluation = self.policy.evaluate(
            session,
            snapshot,
            intent,
            candidate,
            action=selected_action,
            risk=risk,
            origin_allowed=origin.allowed,
            origin_reason=origin.reason_code,
            navigation_steps=navigation_steps,
        )
        fingerprint = self.fingerprint(
            session,
            snapshot,
            intent,
            candidate,
            action=selected_action,
            target_url=target_url,
            input_is_sensitive=input_is_sensitive,
            target_origin=origin.origin,
        )
        if not evaluation.allowed and not evaluation.requires_approval:
            status = SecurityDecisionStatus.BLOCKED
            approval = None
        elif evaluation.requires_approval:
            if approval_id is not None and self.approvals.consume(approval_id, fingerprint=fingerprint):
                status = SecurityDecisionStatus.ALLOWED
                approval = approval_id
            else:
                status = SecurityDecisionStatus.REQUIRE_APPROVAL
                approval = None
        else:
            status = SecurityDecisionStatus.ALLOWED
            approval = None
        return SecurityDecision(
            status,
            selected_action,
            session.session_id,
            snapshot.page_id,
            snapshot.snapshot_id,
            candidate.ref if candidate is not None else None,
            origin.origin,
            risk,
            evaluation.reason_codes,
            fingerprint,
            approval,
        )

    def request_approval(self, decision: SecurityDecision) -> object:
        if not isinstance(decision, SecurityDecision) or decision.status is not SecurityDecisionStatus.REQUIRE_APPROVAL:
            raise WebStateError("only approval-required decisions can create approval requests")
        return self.approvals.request(
            fingerprint=decision.fingerprint,
            session_id=decision.session_id,
            page_id=decision.page_id,
            snapshot_id=decision.snapshot_id,
            target_ref=decision.target_ref,
            categories=decision.risk.categories,
        )

    @staticmethod
    def fingerprint(
        session: BrowserSession,
        snapshot: PageSnapshot,
        intent: TaskIntent,
        candidate: ElementCandidate | None,
        *,
        action: str,
        target_url: str | None,
        input_is_sensitive: bool,
        target_origin: str,
    ) -> str:
        values = {
            "session_id": session.session_id,
            "page_id": snapshot.page_id,
            "snapshot_id": snapshot.snapshot_id,
            "intent_id": intent.intent_id,
            "target_ref": candidate.ref if candidate is not None else None,
            "action": action.casefold(),
            "target_origin": target_origin,
            "generation": snapshot.generation,
            "input_is_sensitive": input_is_sensitive,
            "policy_version": SecurityGate.POLICY_VERSION,
        }
        return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


__all__ = ["SecurityGate"]
