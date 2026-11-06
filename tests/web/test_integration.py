from __future__ import annotations

import unittest

from pie.web import (
    AccessibilityNode,
    SnapshotNormalizer,
    WebIntelligenceService,
    WebStateError,
)


def _snapshot():
    return SnapshotNormalizer().normalize(
        session_id="s1", page_id="p1", frame_id="main", generation=1,
        origin="https://example.test", path="/", title="Home",
        tree=AccessibilityNode(role="main", name="Home", children=(AccessibilityNode(role="button", name="Open", region="main"),)),
        captured_at="2026-01-01T00:00:00Z",
    ).snapshot


class IntegrationTests(unittest.TestCase):
    def test_capability_registry_separates_read_plan_and_execute(self):
        names = {item["name"]: item for item in WebIntelligenceService.capabilities()}
        self.assertFalse(names["pie_web_observe"]["execution"])
        self.assertFalse(names["pie_web_plan"]["execution"])
        self.assertTrue(names["pie_web_execute"]["execution"])

    def test_context_pipeline_returns_non_authorizing_pack(self):
        pack = WebIntelligenceService().context(_snapshot(), "open")
        self.assertFalse(pack.execution_authorized)
        self.assertEqual(pack.provenance.snapshot_id, _snapshot().snapshot_id)

    def test_observation_is_bounded_and_has_no_actions(self):
        observed = WebIntelligenceService().observe(_snapshot())
        self.assertEqual(observed["execution_authorized"], False)
        self.assertNotIn("accessible_name", observed)

    def test_execution_requires_explicit_driver_registration(self):
        service = WebIntelligenceService()
        with self.assertRaisesRegex(WebStateError, "action_driver_unconfigured"):
            service.execute(None)


if __name__ == "__main__":
    unittest.main()
