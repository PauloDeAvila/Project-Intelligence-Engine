from __future__ import annotations

from dataclasses import replace
import unittest

from pie.web import (
    AccessibilityNode,
    PermissionState,
    SecurityDecisionStatus,
    SnapshotNormalizer,
    ReferenceState,
    SnapshotState,
    WebEvidencePackBuilder,
    WebRelevanceGate,
    WebStateError,
)


def _snapshot(*, state: SnapshotState = SnapshotState.CURRENT, omitted: int = 0):
    tree = AccessibilityNode(
        role="main",
        name="Pesquisa",
        children=(
            AccessibilityNode(
                role="form",
                name="Resultados",
                children=(
                    AccessibilityNode(role="button", name="Abrir resultado"),
                    AccessibilityNode(role="button", name="Password token"),
                    AccessibilityNode(role="link", name="Termos"),
                ),
            ),
        ),
    )
    snapshot = SnapshotNormalizer().normalize(
        session_id="s1", page_id="p1", frame_id="main", generation=1,
        origin="https://example.test", path="/search", title="Search", tree=tree,
        state=SnapshotState.CURRENT, captured_at="2026-01-01T00:00:00Z",
    ).snapshot
    if state is not SnapshotState.CURRENT or omitted:
        snapshot = replace(
            snapshot,
            state=state,
            elements=tuple(replace(item, reference_state=ReferenceState.CURRENT) for item in snapshot.elements),
            omitted_count=omitted,
        )
    return snapshot


class EvidencePackTests(unittest.TestCase):
    def test_pack_is_compact_traceable_and_never_authorizes_execution(self):
        snapshot = _snapshot()
        context = WebRelevanceGate().quantify(snapshot, "abrir resultado", context_budget_chars=512, max_candidates=4)
        pack = WebEvidencePackBuilder().build(context, snapshot)
        self.assertEqual(pack.provenance.snapshot_id, snapshot.snapshot_id)
        self.assertLessEqual(pack.used_chars, pack.context_budget_chars)
        self.assertFalse(pack.execution_authorized)
        self.assertEqual(pack.to_dict()["execution_authorized"], False)

    def test_sensitive_labels_are_redacted_and_permission_is_separate(self):
        snapshot = _snapshot()
        context = WebRelevanceGate().quantify(snapshot, "password", context_budget_chars=512, max_candidates=4)
        sensitive = next(item for item in context.selected if "Password" in item.candidate.accessible_name)
        decision = type("Decision", (), {"status": SecurityDecisionStatus.BLOCKED})()
        pack = WebEvidencePackBuilder().build(context, snapshot, decisions={sensitive.candidate.ref: decision})
        item = next(item for item in pack.items if item.ref == sensitive.candidate.ref)
        self.assertEqual(item.label, "[REDACTED_SENSITIVE_LABEL]")
        self.assertEqual(item.permission, PermissionState.BLOCKED)
        self.assertFalse(pack.execution_authorized)

    def test_budget_omissions_are_expandable(self):
        snapshot = _snapshot()
        context = WebRelevanceGate().quantify(snapshot, "resultado", context_budget_chars=4096, max_candidates=4)
        pack = WebEvidencePackBuilder().build(context, snapshot, context_budget_chars=70, max_items=1)
        self.assertTrue(pack.omissions)
        self.assertTrue(pack.expansion.available)
        self.assertTrue(pack.expansion.omitted_refs)
        self.assertEqual(pack.used_chars <= 70, True)

    def test_source_omission_is_preserved_without_page_text(self):
        snapshot = _snapshot(state=SnapshotState.PARTIAL, omitted=2)
        context = WebRelevanceGate().quantify(snapshot, "resultado", context_budget_chars=512, max_candidates=4)
        pack = WebEvidencePackBuilder().build(context, snapshot)
        self.assertTrue(any(item.reason == "source_omitted" for item in pack.omissions))
        self.assertNotIn("Password token", str(pack.to_dict()))

    def test_stale_and_blocked_snapshots_cannot_be_packed(self):
        for state in (SnapshotState.STALE, SnapshotState.BLOCKED):
            snapshot = _snapshot(state=state, omitted=1)
            with self.assertRaises(WebStateError):
                WebEvidencePackBuilder().build(
                    WebRelevanceGate().quantify(_snapshot(state=SnapshotState.CURRENT), "resultado"),
                    snapshot,
                )


if __name__ == "__main__":
    unittest.main()
