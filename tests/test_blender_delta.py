"""Deterministic contract tests for Blender scene delta without Blender installation."""
from pathlib import Path
import copy
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pie.integrations.blender_delta import (
    QUERY_SCHEMA, QUERY_MARKER, GET_OBJECT_MARKER, SceneDeltaCache, parse_execution_reply,
    parse_query_reply, snapshot_code, get_object_code, parse_get_object_reply,
    validate_get_object_arguments,
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
    def test_exact_object_code_and_reply_are_minimal_and_read_only(self):
        name = 'Cube"); __import__("os").system("echo bad") #'
        code = get_object_code({"name": name})
        self.assertIn("bpy.context.scene.objects.get(pie_object_name)", code)
        self.assertNotIn("bpy.ops", code)
        self.assertNotIn("exec(", code)
        self.assertIn(json.dumps(name, ensure_ascii=True), code)
        value = {"object_name": "PIE_Large_Cube_00", "object_type": "MESH",
                 "location": [0.0, 0.0, 0.0],
                 "material_names": ["PIE_Large_Material_00"]}
        reply = {"result": {"content": [{"type": "text",
                  "text": "Code executed successfully: " + GET_OBJECT_MARKER
                          + json.dumps(value)}]}}
        self.assertEqual(parse_get_object_reply(reply), value)
        self.assertEqual(len(parse_get_object_reply(reply)), 4)
        for invalid in ({}, {"name": ""}, {"name": "Cube", "code": "print(1)"},
                        {"name": 7}, {"name": "a" * 129}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_get_object_arguments(invalid)
        with self.assertRaisesRegex(ValueError, "not found"):
            parse_get_object_reply({"result": {"content": [{"type": "text",
                "text": GET_OBJECT_MARKER + '{"error":"OBJECT_NOT_FOUND"}'}]}})
        with self.assertRaises(ValueError):
            parse_get_object_reply({"result": {"content": [{"type": "text",
                "text": GET_OBJECT_MARKER + '{"object_name":"only"}'}]}})
        with self.assertRaises(ValueError):
            parse_get_object_reply({"result": {"isError": True, "content": []}})

    def test_query_parser_accepts_structured_content_result(self):
        query = {"schema": QUERY_SCHEMA, "query": "find_objects", "scene": "Scene",
                 "items": [], "total": 0, "offset": 0, "limit": 20,
                 "next_offset": None, "complete": True}
        encoded = QUERY_MARKER + json.dumps(query, separators=(",", ":"))
        self.assertEqual(parse_query_reply({"result": {"structuredContent": {"result": encoded}}}), query)

    def test_query_parser_reports_structured_execution_failure(self):
        message = {"result": {"content": [{"type": "text", "text": "Error executing code: failed"}],
                               "structuredContent": {"result": "Error executing code: failed"}}}
        with self.assertRaisesRegex(ValueError, "execution failed"):
            parse_query_reply(message)

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
