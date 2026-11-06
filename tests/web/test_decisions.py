from __future__ import annotations

from dataclasses import replace
import unittest

from pie.web import (
    AccessibilityNode,
    DecisionBatcher,
    DecisionRoute,
    DecisionSource,
    SemanticDecision,
    SnapshotNormalizer,
    WebRelevanceGate,
)


def _context(query: str = "open", *, include_sensitive: bool = True):
    children = [AccessibilityNode(role="button", name="Open dashboard", region="main")]
    if include_sensitive:
        children.append(AccessibilityNode(role="button", name="Password token", region="main"))
    tree = AccessibilityNode(
        role="main", name="Home", children=(
            *children,
        )
    )
    snapshot = SnapshotNormalizer().normalize(
        session_id="s1", page_id="p1", frame_id="main", generation=1,
        origin="https://example.test", path="/", title="Home", tree=tree,
        captured_at="2026-01-01T00:00:00Z",
    ).snapshot
    return WebRelevanceGate().quantify(snapshot, query, context_budget_chars=512, max_candidates=4)


class _Classifier:
    def __init__(self):
        self.calls = 0

    def classify(self, batch):
        self.calls += 1
        return tuple(SemanticDecision(item.ref, DecisionRoute.LOCAL, DecisionSource.EXTERNAL, 0.91, "external_structured_result") for item in batch.features)


class DecisionLayerTests(unittest.TestCase):
    def test_local_path_is_default_and_does_not_call_classifier(self):
        classifier = _Classifier()
        decisions = DecisionBatcher().decide(_context(), classifier=classifier)
        self.assertTrue(decisions)
        self.assertEqual(classifier.calls, 0)
        self.assertTrue(all(item.source is not DecisionSource.EXTERNAL for item in decisions))

    def test_sensitive_candidate_is_not_sent_externally(self):
        classifier = _Classifier()
        decisions = DecisionBatcher().decide(_context("password"), classifier=classifier, allow_external=True)
        self.assertEqual(classifier.calls, 0)
        self.assertTrue(any(item.route is DecisionRoute.BLOCKED for item in decisions))

    def test_external_classifier_requires_explicit_opt_in_and_safe_batch(self):
        classifier = _Classifier()
        context = replace(_context("open", include_sensitive=False), query="unrelated", ambiguous=True)
        decisions = DecisionBatcher().decide(context, classifier=classifier, allow_external=True)
        self.assertEqual(classifier.calls, 1)
        self.assertTrue(any(item.source is DecisionSource.EXTERNAL for item in decisions))

    def test_external_payload_is_minimized_and_does_not_contain_query(self):
        batch = DecisionBatcher().build(_context("open", include_sensitive=False))
        self.assertNotIn("'query'", str(batch.external_payload()))
        self.assertNotIn("Password token", str(batch.external_payload()))


if __name__ == "__main__":
    unittest.main()
