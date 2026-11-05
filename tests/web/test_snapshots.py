from __future__ import annotations

import unittest
from dataclasses import replace

from pie.web import (
    AccessibilityExtractor,
    AccessibilityNode,
    ElementRegistry,
    ElementSupport,
    PageStateTracker,
    SnapshotNormalizer,
    SnapshotState,
    WebStateError,
)
from pie.web.contracts import ElementCandidate


def _tree() -> AccessibilityNode:
    return AccessibilityNode(
        role="main",
        name="Account area",
        children=(
            AccessibilityNode(
                role="form",
                name="Search form",
                children=(
                    AccessibilityNode(role="textbox", name="Pesquisar"),
                    AccessibilityNode(role="button", name="Enviar"),
                    AccessibilityNode(role="custom-widget", name="Third-party widget"),
                ),
            ),
            AccessibilityNode(
                role="table",
                name="Results",
                children=(
                    AccessibilityNode(role="row", name="First row"),
                    AccessibilityNode(role="cell", name="Value"),
                ),
            ),
        ),
    )


class SnapshotIntelligenceTests(unittest.TestCase):
    def make_snapshot(self, *, generation: int = 1, tree: AccessibilityNode | None = None):
        return SnapshotNormalizer().normalize(
            session_id="s1",
            page_id="p1",
            frame_id="main",
            generation=generation,
            origin="https://example.test",
            path="/search",
            title="Results",
            tree=tree or _tree(),
            captured_at="2026-01-01T00:00:00Z",
        ).snapshot

    def test_extractor_preserves_unsupported_nodes_without_actions(self):
        result = AccessibilityExtractor().extract(_tree())

        self.assertEqual(len(result.elements), 8)
        unsupported = [item for item in result.elements if item.support is ElementSupport.UNSUPPORTED]
        self.assertEqual(len(unsupported), 4)
        self.assertTrue(all(item.available_actions == () for item in unsupported))
        self.assertEqual(
            [item.available_actions for item in result.elements if item.accessible_name == "Pesquisar"],
            [("type",)],
        )

    def test_normalization_is_deterministic_and_snapshot_bound(self):
        first = self.make_snapshot()
        second = self.make_snapshot()

        self.assertEqual(first.snapshot_id, second.snapshot_id)
        self.assertEqual(first.snapshot_sha256, second.snapshot_sha256)
        self.assertEqual(first.to_json(), second.to_json())
        self.assertTrue(all(item.content_trust.value == "UNTRUSTED_PAGE_DATA" for item in first.elements))
        self.assertTrue(all(item.snapshot_id == first.snapshot_id for item in first.elements))

    def test_mapping_input_is_inert_and_sensitive_text_is_not_serialized(self):
        snapshot = SnapshotNormalizer().normalize(
            session_id="s1",
            page_id="p1",
            frame_id="main",
            generation=1,
            origin="https://example.test",
            path="/reset/[REDACTED]",
            title="password=secret-value",
            tree={
                "role": "button",
                "name": "Authorization: Bearer private-token",
                "children": [],
            },
        ).snapshot

        encoded = snapshot.to_json()
        self.assertNotIn("private-token", encoded)
        self.assertNotIn("password=secret-value", encoded)
        self.assertNotIn("javascript:", encoded)

    def test_partial_snapshot_is_bounded_and_reports_omissions(self):
        root = AccessibilityNode(
            role="main",
            name="Root",
            children=tuple(AccessibilityNode(role="button", name=f"B{i}") for i in range(10)),
        )
        result = SnapshotNormalizer(extractor=AccessibilityExtractor(max_elements=4)).normalize(
            session_id="s1",
            page_id="p1",
            frame_id="main",
            generation=1,
            origin="https://example.test",
            path="/",
            title="Home",
            tree=root,
        )
        self.assertTrue(result.partial)
        self.assertEqual(result.snapshot.state, SnapshotState.PARTIAL)
        self.assertGreater(result.snapshot.omitted_count, 0)
        self.assertEqual(len(result.snapshot.elements), 4)

    def test_registry_uses_literal_name_search_and_snapshot_bound_resolution(self):
        snapshot = self.make_snapshot()
        registry = ElementRegistry()
        registry.register(snapshot)

        found = registry.find(snapshot.snapshot_id, role="button", name_contains="enviar")
        self.assertEqual(len(found), 1)
        self.assertEqual(registry.find(snapshot.snapshot_id, name_contains="[role=button]"), ())
        self.assertIsNotNone(
            registry.resolve(
                found[0],
                session_id="s1",
                page_id="p1",
                frame_id="main",
                generation=1,
                snapshot_sha256=snapshot.snapshot_sha256,
            )
        )
        self.assertIsNone(
            registry.resolve(
                found[0],
                session_id="s1",
                page_id="p1",
                frame_id="main",
                generation=2,
                snapshot_sha256=snapshot.snapshot_sha256,
            )
        )

    def test_tracker_rejects_older_observation_and_marks_same_generation_change_partial(self):
        tracker = PageStateTracker()
        first = self.make_snapshot(generation=2)
        self.assertTrue(tracker.observe(first).changed)

        altered = self.make_snapshot(
            generation=2,
            tree=AccessibilityNode(role="main", name="Changed", children=()),
        )
        changed = tracker.observe(altered)
        self.assertEqual(changed.snapshot.state, SnapshotState.PARTIAL)
        self.assertTrue(changed.changed)

        older = self.make_snapshot(generation=1)
        stale = tracker.observe(older)
        self.assertTrue(stale.stale)
        self.assertEqual(stale.snapshot.state, SnapshotState.STALE)
        self.assertIs(tracker.current("s1", "p1", "main"), changed.snapshot)

    def test_invalid_tree_and_path_fail_closed(self):
        with self.assertRaises(WebStateError):
            AccessibilityNode.from_mapping({"role": "button", "children": "not-a-list"})
        with self.assertRaises(WebStateError):
            SnapshotNormalizer().normalize(
                session_id="s1",
                page_id="p1",
                frame_id="main",
                generation=1,
                origin="https://example.test",
                path="/private?token=secret",
                title="Home",
                tree=_tree(),
            )
        with self.assertRaises(WebStateError):
            AccessibilityNode.from_mapping({"role": "button"}, depth=-1)

    def test_current_partial_and_unsafe_candidate_contracts_fail_closed(self):
        root = AccessibilityNode(
            role="main",
            name="Root",
            children=tuple(AccessibilityNode(role="button", name=f"B{i}") for i in range(3)),
        )
        with self.assertRaises(WebStateError):
            SnapshotNormalizer(extractor=AccessibilityExtractor(max_elements=2)).normalize(
                session_id="s1", page_id="p1", frame_id="main", generation=1,
                origin="https://example.test", path="/", title="Home", tree=root,
                state=SnapshotState.CURRENT,
            )
        with self.assertRaises(WebStateError):
            ElementCandidate(
                ref="r", session_id="s1", snapshot_id="s", page_id="p1", generation=1,
                snapshot_sha256="0" * 64, role="button", accessible_name="x",
                available_actions=("click",), support=ElementSupport.UNSUPPORTED,
                unsupported_reason="unsupported_role",
            )

    def test_registry_rejects_collisions_context_mismatch_and_stale_authority(self):
        snapshot = self.make_snapshot(generation=1)
        registry = ElementRegistry()
        registry.register(snapshot)
        with self.assertRaises(WebStateError):
            registry.register(replace(snapshot, title="Other"))
        found = registry.find(snapshot.snapshot_id, role="button", name_contains="enviar")[0]
        self.assertIsNone(registry.resolve(
            found, session_id="s1", page_id="p1", frame_id="child", generation=1,
            snapshot_sha256=snapshot.snapshot_sha256,
        ))
        newer = self.make_snapshot(generation=2)
        registry.register(newer)
        self.assertIsNone(registry.resolve(
            found, session_id="s1", page_id="p1", frame_id="main", generation=1,
            snapshot_sha256=snapshot.snapshot_sha256,
        ))

    def test_input_node_bound_and_source_provenance_are_enforced(self):
        root = AccessibilityNode(
            role="main", name="Root",
            children=tuple(AccessibilityNode(role="button", name=f"B{i}") for i in range(100)),
        )
        result = AccessibilityExtractor(max_elements=512, max_input_nodes=5).extract(root)
        self.assertTrue(result.partial)
        self.assertGreater(result.omitted_count, 0)
        self.assertEqual(
            AccessibilityNode(role="button", name="x", source="dom_snapshot").source,
            "dom_snapshot",
        )

    def test_public_candidate_cannot_forge_capabilities(self):
        for role, action in (("button", "type"), ("input", "click"), ("button", "click")):
            kwargs = {
                "ref": "r", "session_id": "s1", "snapshot_id": "s", "page_id": "p1",
                "generation": 1, "snapshot_sha256": "0" * 64, "role": role,
                "accessible_name": "x", "available_actions": (action,),
            }
            if role == "button" and action == "click":
                self.assertEqual(ElementCandidate(**kwargs).available_actions, ("click",))
            else:
                with self.assertRaises(WebStateError):
                    ElementCandidate(**kwargs)
        with self.assertRaises(WebStateError):
            ElementCandidate(
                ref="r", session_id="s1", snapshot_id="s", page_id="p1", generation=1,
                snapshot_sha256="0" * 64, role="button", accessible_name="x",
                enabled=False, available_actions=("click",),
            )


if __name__ == "__main__":
    unittest.main()
