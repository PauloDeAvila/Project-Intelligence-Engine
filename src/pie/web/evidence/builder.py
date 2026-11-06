"""Build compact web evidence packs from quantified context, never permissions."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping

from ..contracts import ElementCandidate, PageSnapshot, SnapshotState, WebStateError
from ..relevance.models import QuantifiedWebContext, ScoredCandidate
from ..security.models import RiskCategory, SecurityDecision, SecurityDecisionStatus
from ..security.sensitive import SensitiveDataFilter
from .budget import ContextBudgetController
from .ledger import ContextExpansionFallback, OmissionLedger
from .models import (
    EvidenceItem,
    EvidenceProvenance,
    ExpansionPlan,
    PermissionState,
    WebEvidencePack,
)


class WebEvidencePackBuilder:
    def __init__(
        self,
        *,
        budget_controller: ContextBudgetController | None = None,
        ledger: OmissionLedger | None = None,
        expansion: ContextExpansionFallback | None = None,
        sensitive_filter: SensitiveDataFilter | None = None,
    ) -> None:
        self.budget_controller = budget_controller or ContextBudgetController()
        self.ledger = ledger or OmissionLedger()
        self.expansion = expansion or ContextExpansionFallback()
        self.sensitive_filter = sensitive_filter or SensitiveDataFilter()

    def build(
        self,
        context: QuantifiedWebContext,
        snapshot: PageSnapshot,
        *,
        decisions: Mapping[str, SecurityDecision] | None = None,
        context_budget_chars: int | None = None,
        max_items: int = 32,
    ) -> WebEvidencePack:
        if not isinstance(context, QuantifiedWebContext) or not isinstance(snapshot, PageSnapshot):
            raise WebStateError("context and snapshot are required")
        if snapshot.state in {SnapshotState.STALE, SnapshotState.BLOCKED} or context.snapshot_id != snapshot.snapshot_id:
            raise WebStateError("evidence requires a matching non-stale snapshot")
        if decisions is not None and not isinstance(decisions, Mapping):
            raise WebStateError("decisions must be a mapping")
        budget = context.context_budget_chars if context_budget_chars is None else context_budget_chars
        if not isinstance(budget, int) or not 1 <= budget <= 1_000_000:
            raise WebStateError("context budget is outside the safe bound")
        selected = tuple(context.selected)
        allocation = self.budget_controller.allocate(
            selected,
            estimate=lambda item: self._estimate(item.candidate),
            context_budget_chars=budget,
            max_items=max_items,
        )
        items = tuple(self._item(item, decisions.get(item.candidate.ref) if decisions else None) for item in allocation.selected)
        omissions = self.ledger.merge(context.omissions, allocation.omitted, source_omitted_count=context.source_omitted_count)
        provenance = EvidenceProvenance(
            snapshot.session_id,
            snapshot.page_id,
            snapshot.snapshot_id,
            snapshot.snapshot_sha256,
            snapshot.generation,
            snapshot.origin,
            snapshot.path,
            snapshot.captured_at,
            snapshot.state,
        )
        pack_id = hashlib.sha256(f"{snapshot.snapshot_id}:{context.query}:{budget}".encode("utf-8")).hexdigest()[:32]
        pack = WebEvidencePack(
            pack_id,
            context.query,
            provenance,
            items,
            omissions,
            budget,
            allocation.used_chars,
            ExpansionPlan(bool(omissions), tuple(item.ref for item in omissions if item.expandable and item.ref != "__source__"), min(1_000_000, max(budget + 1, budget * 2))),
            False,
        )
        return pack

    def _item(self, scored: ScoredCandidate, decision: SecurityDecision | None) -> EvidenceItem:
        candidate = scored.candidate
        classification = self.sensitive_filter.classify_candidate(candidate)
        label = self._safe_label(candidate.accessible_name, classification.contains_page_instruction, bool(set(classification.categories) & {RiskCategory.CREDENTIALS, RiskCategory.FINANCIAL}))
        permission = PermissionState.NOT_CHECKED
        if decision is not None:
            permission = {
                SecurityDecisionStatus.ALLOWED: PermissionState.ALLOWED,
                SecurityDecisionStatus.REQUIRE_APPROVAL: PermissionState.APPROVAL_REQUIRED,
                SecurityDecisionStatus.BLOCKED: PermissionState.BLOCKED,
            }[decision.status]
        return EvidenceItem(
            candidate.ref,
            label,
            candidate.role,
            candidate.region,
            candidate.available_actions,
            scored.score,
            tuple(category.value for category in classification.categories),
            permission,
            self._estimate(candidate),
        )

    @staticmethod
    def _safe_label(value: str, page_instruction: bool, sensitive: bool) -> str:
        if page_instruction:
            return "[UNTRUSTED_PAGE_INSTRUCTION]"
        if sensitive:
            return "[REDACTED_SENSITIVE_LABEL]"
        value = re.sub(r"\s+", " ", value).strip()
        return value[:256] or "[UNNAMED_ELEMENT]"

    def _estimate(self, candidate: ElementCandidate) -> int:
        classification = self.sensitive_filter.classify_candidate(candidate)
        label = self._safe_label(candidate.accessible_name, classification.contains_page_instruction, bool(set(classification.categories) & {RiskCategory.CREDENTIALS, RiskCategory.FINANCIAL}))
        return max(1, min(4096, len(label) + len(candidate.role) + len(candidate.ref) + sum(len(action) for action in candidate.available_actions) + (len(candidate.region) if candidate.region else 0) + 48))


__all__ = ["WebEvidencePackBuilder"]
