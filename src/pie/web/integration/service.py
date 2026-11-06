"""Integrated web intelligence service for typed MCP/orchestration bridges."""

from __future__ import annotations

from collections.abc import Mapping

from ..actions import ActionExecutor, ActionPlan, ActionPlanner
from ..contracts import BrowserSession, ElementCandidate, PageSnapshot, TaskIntent, WebStateError
from ..evidence import WebEvidencePack, WebEvidencePackBuilder
from ..relevance import WebRelevanceGate
from ..security import SecurityGate


WEB_MCP_TOOLS = (
    {"name": "pie_web_observe", "permission": "read", "execution": False},
    {"name": "pie_web_context", "permission": "read", "execution": False},
    {"name": "pie_web_plan", "permission": "plan", "execution": False},
    {"name": "pie_web_execute", "permission": "execute", "execution": True},
)


class WebIntelligenceService:
    """Compose the certified local layers without owning browser transport."""

    def __init__(
        self,
        *,
        relevance: WebRelevanceGate | None = None,
        evidence: WebEvidencePackBuilder | None = None,
        security: SecurityGate | None = None,
        planner: ActionPlanner | None = None,
        executor: ActionExecutor | None = None,
    ) -> None:
        self.relevance = relevance or WebRelevanceGate()
        self.evidence = evidence or WebEvidencePackBuilder()
        self.security = security or SecurityGate()
        self.planner = planner or ActionPlanner(security=self.security)
        self.executor = executor

    @staticmethod
    def capabilities() -> tuple[dict[str, object], ...]:
        return tuple(dict(item) for item in WEB_MCP_TOOLS)

    def observe(self, snapshot: PageSnapshot) -> dict[str, object]:
        if not isinstance(snapshot, PageSnapshot):
            raise WebStateError("snapshot must be a PageSnapshot")
        return {
            "snapshot_id": snapshot.snapshot_id,
            "session_id": snapshot.session_id,
            "page_id": snapshot.page_id,
            "frame_id": snapshot.frame_id,
            "generation": snapshot.generation,
            "state": snapshot.state.value,
            "origin": snapshot.origin,
            "path": snapshot.path,
            "element_count": len(snapshot.elements),
            "omitted_count": snapshot.omitted_count,
            "execution_authorized": False,
        }

    def context(self, snapshot: PageSnapshot, query: str, *, context_budget_chars: int = 4096, max_candidates: int = 8) -> WebEvidencePack:
        quantified = self.relevance.quantify(snapshot, query, context_budget_chars=context_budget_chars, max_candidates=max_candidates)
        return self.evidence.build(quantified, snapshot)

    def plan(
        self,
        *,
        action_id: str,
        session: BrowserSession,
        snapshot: PageSnapshot,
        intent: TaskIntent,
        candidate: ElementCandidate | None = None,
        action: str | None = None,
        target_url: str | None = None,
        input_is_sensitive: bool = False,
        approval_id: str | None = None,
    ) -> ActionPlan:
        return self.planner.plan(
            action_id=action_id, session=session, snapshot=snapshot, intent=intent,
            candidate=candidate, action=action, target_url=target_url,
            input_is_sensitive=input_is_sensitive, approval_id=approval_id,
        )

    def execute(self, plan: ActionPlan, **kwargs):
        if self.executor is None:
            raise WebStateError("action_driver_unconfigured")
        return self.executor.execute(plan, **kwargs)


__all__ = ["WEB_MCP_TOOLS", "WebIntelligenceService"]
