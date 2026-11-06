"""Omission ledger and bounded context expansion fallback."""

from __future__ import annotations

from ..contracts import WebStateError
from ..relevance.models import OmissionRecord
from .models import EvidenceOmission, ExpansionPlan, WebEvidencePack


class OmissionLedger:
    def merge(
        self,
        source: tuple[OmissionRecord, ...],
        additional: tuple[EvidenceOmission, ...],
        *,
        source_omitted_count: int = 0,
    ) -> tuple[EvidenceOmission, ...]:
        if not isinstance(source, tuple) or not isinstance(additional, tuple) or not isinstance(source_omitted_count, int) or source_omitted_count < 0:
            raise WebStateError("invalid omission ledger inputs")
        entries = [EvidenceOmission(item.ref, item.reason, item.score, item.expandable) for item in source]
        entries.extend(additional)
        if source_omitted_count:
            entries.append(EvidenceOmission("__source__", "source_omitted", 0.0, True))
        return tuple(entries[:512])


class ContextExpansionFallback:
    def plan(self, pack: WebEvidencePack) -> ExpansionPlan:
        if not isinstance(pack, WebEvidencePack):
            raise WebStateError("pack must be a WebEvidencePack")
        refs = tuple(item.ref for item in pack.omissions if item.expandable and item.ref != "__source__")
        suggested = min(1_000_000, max(pack.context_budget_chars + 1, pack.context_budget_chars * 2))
        return ExpansionPlan(bool(refs), refs, suggested)


__all__ = ["ContextExpansionFallback", "OmissionLedger"]
