from __future__ import annotations

from dataclasses import replace
import unittest

from pie.web import (
    AccessibilityNode,
    CandidateRanker,
    DecisionThresholdController,
    RedundancyReducer,
    ReferenceState,
    RelevanceScorer,
    SnapshotNormalizer,
    SnapshotState,
    WebRelevanceGate,
    WebStateError,
)


def _snapshot(*, state: SnapshotState = SnapshotState.CURRENT, omitted: int = 0):
    tree = AccessibilityNode(
        role="main",
        name="Conta",
        children=(
            AccessibilityNode(
                role="form",
                name="Login",
                children=(
                    AccessibilityNode(role="textbox", name="Pesquisar"),
                    AccessibilityNode(role="button", name="Pesquisar"),
                    AccessibilityNode(role="button", name="Erro de segurança"),
                    AccessibilityNode(role="link", name="Termos de uso"),
                ),
            ),
        ),
    )
    return SnapshotNormalizer().normalize(
        session_id="s1", page_id="p1", frame_id="main", generation=1,
        origin="https://example.test", path="/home", title="Home", tree=tree,
        state=state, captured_at="2026-01-01T00:00:00Z",
    ).snapshot


class RelevanceGateTests(unittest.TestCase):
    def test_scorer_is_explainable_and_protects_safety_signals(self):
        snapshot = _snapshot()
        candidate = snapshot.elements[4]
        scored = RelevanceScorer().score(candidate, ordinal=4, query="pesquisar")
        self.assertTrue(scored.protected)
        self.assertGreaterEqual(scored.score, 0.8)
        self.assertIn("safety_signal", scored.reasons)

    def test_selector_like_query_fails_closed(self):
        candidate = _snapshot().elements[2]
        with self.assertRaises(WebStateError):
            RelevanceScorer().score(candidate, ordinal=2, query="[role=button]")

    def test_threshold_controller_is_bounded_and_deterministic(self):
        controller = DecisionThresholdController()
        first = controller.choose(candidate_count=100, max_candidates=8, context_budget_chars=256, ambiguous=False)
        second = controller.choose(candidate_count=100, max_candidates=8, context_budget_chars=256, ambiguous=False)
        self.assertEqual(first, second)
        self.assertGreaterEqual(first, 0.15)
        self.assertLessEqual(first, 0.75)
        with self.assertRaises(WebStateError):
            controller.choose(candidate_count=1, max_candidates=33, context_budget_chars=256, ambiguous=False)

    def test_ranker_prefers_score_then_protected_then_position(self):
        snapshot = _snapshot()
        scorer = RelevanceScorer()
        values = tuple(
            scorer.score(candidate, ordinal=index, query="unrelated")
            for index, candidate in enumerate(snapshot.elements[2:5], start=2)
        )
        ranked = CandidateRanker().rank(values)
        self.assertEqual(ranked[0].candidate.accessible_name, "Erro de segurança")

    def test_reducer_tracks_duplicates_threshold_budget_and_limit(self):
        snapshot = _snapshot()
        scorer = RelevanceScorer()
        values = tuple(
            scorer.score(candidate, ordinal=index, query="pesquisar")
            for index, candidate in enumerate(snapshot.elements[2:5], start=2)
        )
        duplicate = replace(values[0], ordinal=99)
        result = RedundancyReducer().reduce(
            CandidateRanker().rank(values + (duplicate,)),
            threshold=0.3,
            context_budget_chars=70,
            max_candidates=1,
        )
        self.assertEqual(len(result.selected), 1)
        self.assertTrue(result.omitted)
        self.assertTrue({item.reason for item in result.omitted}.intersection({"duplicate", "budget", "limit", "below_threshold"}))

    def test_gate_preserves_safety_signal_and_reports_expansion(self):
        snapshot = _snapshot(state=SnapshotState.PARTIAL)
        gate = WebRelevanceGate()
        context = gate.quantify(snapshot, "campo de busca", context_budget_chars=256, max_candidates=2)
        self.assertTrue(any(item.protected for item in context.selected))
        self.assertEqual(context.state, SnapshotState.PARTIAL)
        self.assertTrue(context.expansion_available)
        self.assertEqual(context.source_omitted_count, 0)

    def test_gate_carries_source_omissions_and_rejects_stale_or_blocked(self):
        partial = _snapshot(state=SnapshotState.PARTIAL)
        partial = replace(
            partial,
            elements=tuple(replace(item, reference_state=ReferenceState.CURRENT) for item in partial.elements),
            omitted_count=3,
        )
        context = WebRelevanceGate().quantify(partial, "pesquisar")
        self.assertEqual(context.source_omitted_count, 3)
        self.assertTrue(context.expansion_available)
        for state in (SnapshotState.STALE, SnapshotState.BLOCKED):
            with self.assertRaises(WebStateError):
                WebRelevanceGate().quantify(replace(partial, state=state), "pesquisar")

    def test_gate_budget_and_candidate_limits_are_explicit(self):
        with self.assertRaises(WebStateError):
            WebRelevanceGate().quantify(_snapshot(), "pesquisar", context_budget_chars=0)
        with self.assertRaises(WebStateError):
            WebRelevanceGate().quantify(_snapshot(), "pesquisar", max_candidates=33)


if __name__ == "__main__":
    unittest.main()
