from __future__ import annotations

from dataclasses import replace
import unittest

from pie.web import (
    AccessibilityNode,
    BrowserFastPath,
    ElementReuseManager,
    PageCache,
    RegionPrefetcher,
    SnapshotDeltaEngine,
    SnapshotNormalizer,
    SnapshotState,
    WebRelevanceGate,
    WebStateError,
)


def _snapshot(name: str = "Open", generation: int = 1):
    tree = AccessibilityNode(role="main", name="Home", children=(AccessibilityNode(role="button", name=name, region="main"),))
    return SnapshotNormalizer().normalize(
        session_id="s1", page_id="p1", frame_id="main", generation=generation,
        origin="https://example.test", path="/", title="Home", tree=tree,
        captured_at="2026-01-01T00:00:00Z",
    ).snapshot


class OptimizationTests(unittest.TestCase):
    def test_cache_is_session_page_task_and_generation_bound(self):
        fast = BrowserFastPath(cache=PageCache(max_entries=2))
        calls = [0]
        def compute():
            calls[0] += 1
            return {"value": calls[0]}
        first = fast.get_or_compute(_snapshot(), region="main", task="open", compute=compute)
        second = fast.get_or_compute(_snapshot(), region="main", task="open", compute=compute)
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(calls[0], 1)
        newer = _snapshot(generation=2)
        third = fast.get_or_compute(newer, region="main", task="open", compute=compute)
        self.assertFalse(third.cache_hit)
        self.assertEqual(calls[0], 2)
        self.assertTrue(third.validation_required)

    def test_delta_and_reuse_only_keep_unchanged_refs(self):
        before = _snapshot()
        after = _snapshot("Changed")
        delta = SnapshotDeltaEngine().compare(before, after)
        self.assertTrue(delta.added_refs or delta.removed_refs or delta.changed_refs)
        self.assertEqual(ElementReuseManager().reusable(before, after), (before.elements[0].ref,))
        unchanged = SnapshotDeltaEngine().compare(before, _snapshot())
        self.assertEqual(unchanged.unchanged_count, 2)

    def test_prefetch_is_local_and_fingerprint_only(self):
        snapshot = _snapshot()
        context = WebRelevanceGate().quantify(snapshot, "open")
        plan = RegionPrefetcher().plan(snapshot, context)
        self.assertEqual(plan.regions, ("main",))
        self.assertEqual(len(plan.task_fingerprint), 64)
        self.assertNotIn("open", plan.task_fingerprint)

    def test_fast_path_rejects_stale_and_requires_validation(self):
        stale = replace(_snapshot(), state=SnapshotState.STALE, elements=(), omitted_count=1)
        with self.assertRaises(WebStateError):
            BrowserFastPath().get_or_compute(stale, region="main", task="open", compute=lambda: None)


if __name__ == "__main__":
    unittest.main()
