"""Deterministic contract tests for Blender scene delta without Blender installation."""
from pathlib import Path
import copy
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pie.integrations.blender_delta import (
    SceneDeltaCache, parse_execution_reply, snapshot_code,
)


def fixture():
    return {
        "schema": "pie-blender-scene-snapshot-v1",
        "scene": "Scene", "scope": "selected", "complete": True,
        "omissions": {"objects": 0, "materials": 0},
        "objects": [
            {"name": "Cube", "type": "MESH", "location": [0, 0, 0],
             "scale": [1, 1, 1], "materials": ["Steel"]}],
        "materials": [
            {"name": "Steel", "use_nodes": True, "metallic": 0.95,
             "nodes": [
                 {"name": "Principled BSDF", "type": "ShaderNodeBsdfPrincipled",
                  "inputs": {"Roughness": 0.35}}],
             "links": [], "node_count": 1, "link_count": 0}],
    }


class BlenderDeltaTests(unittest.TestCase):
    def test_first_unchanged_changed_and_manual_change(self):
        cache = SceneDeltaCache()
        old = fixture()
        start = cache.observe(old)
        self.assertEqual(start["state"], "INITIAL")
        self.assertEqual(cache.observe(copy.deepcopy(old))["state"], "UNCHANGED")
        update = copy.deepcopy(old)
        update["materials"][0]["nodes"][0]["inputs"]["Roughness"] = 0.28
        delta = cache.observe(update)
        self.assertEqual(delta["state"], "DELTA")
        self.assertEqual(delta["materials"]["counts"]["changed"], 1)
        self.assertIn("nodes", delta["materials"]["changed"][0]["details"])
        node_changes = delta["materials"]["changed"][0]["details"]["nodes"]["changed"]
        value = node_changes[0]["details"]["inputs"]["changed"]["Roughness"]
        self.assertEqual(value, {"before": 0.35, "after": 0.28})
        self.assertNotEqual(delta["digest"], delta["previous_digest"])
        self.assertEqual(cache.observe(update)["state"], "UNCHANGED")
        manual = copy.deepcopy(update)
        manual["objects"][0]["location"] = [2, 0, 0]
        self.assertEqual(cache.observe(manual)["objects"]["counts"]["changed"], 1)

    def test_added_and_removed_entities(self):
        cache = SceneDeltaCache()
        original = fixture()
        cache.observe(original)
        updated = copy.deepcopy(original)
        updated["objects"] = [{"name": "OtherCube", "type": "MESH"}]
        result = cache.observe(updated)
        self.assertEqual(result["objects"]["added"], ["OtherCube"])
        self.assertEqual(result["objects"]["removed"], ["Cube"])

    def test_partial_cannot_replace_baseline(self):
        cache = SceneDeltaCache()
        cache.observe(fixture())
        broken = copy.deepcopy(fixture())
        broken["complete"] = False
        broken["objects"] = []
        broken["omissions"] = {"objects": 1}
        partial = cache.observe(broken)
        self.assertEqual(partial["state"], "PARTIAL")
        self.assertFalse(partial["complete"])
        self.assertEqual(cache.observe(fixture())["state"], "UNCHANGED")

    def test_budget_failure_keeps_previous_baseline(self):
        cache = SceneDeltaCache()
        cache.observe(fixture())
        next_scene = copy.deepcopy(fixture())
        next_scene["objects"] = [{"name": f"Cube_{i}", "type": "MESH", "location": [i,0,0]} for i in range(120)]
        small = cache.observe(next_scene, max_chars=1000)
        self.assertEqual(small["state"], "BUDGET_EXCEEDED")
        large = cache.observe(next_scene, max_chars=64000)
        self.assertEqual(large["state"], "DELTA")
        self.assertEqual(large["objects"]["counts"]["added"], 120)

    def test_validation_rejects_bad_scope_duplicate_names_and_json(self):
        cache = SceneDeltaCache()
        with self.assertRaises(ValueError):
            snapshot_code("import os")
        self.assertIn("pie_scope = 'selected'", snapshot_code("selected"))
        bad = fixture()
        bad["objects"].append(copy.deepcopy(bad["objects"][0]))
        with self.assertRaises(ValueError):
            cache.observe(bad)
        with self.assertRaises(ValueError):
            cache.observe({"schema":"arbitrary"})

    def test_parse_upstream_success_and_errors(self):
        payload = json.dumps(fixture())
        msg = {"result": {"content": [
            {"type": "text", "text": "Code executed successfully: PIE_SCENE_SNAPSHOT_V1=" + payload}
        ]}}
        self.assertEqual(parse_execution_reply(msg), fixture())
        msg["result"]["content"][0]["text"] = "Error executing code: denied"
        with self.assertRaisesRegex(ValueError, "rejected"):
            parse_execution_reply(msg)

    def test_per_scene_scope_isolation(self):
        cache = SceneDeltaCache()
        x = fixture()
        cache.observe(x)
        other = copy.deepcopy(x)
        other["scope"] = "all"
        self.assertEqual(cache.observe(other)["state"], "INITIAL")
        other["scene"] = "OtherScene"
        self.assertEqual(cache.observe(other)["state"], "INITIAL")


if __name__ == "__main__":
    unittest.main()
