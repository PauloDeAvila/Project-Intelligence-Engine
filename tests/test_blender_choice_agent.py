"""Offline fail-closed tests for the Blender multi-choice evidence agent."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from benchmark_blender_choice_agent import (
    TASKS, _read_only_blender_code, compare_pair,
    independent_fixture_oracle, ordered_catalog, plan_choice, run_arm,
    validate_task,
)
from benchmark_blender_evidence_agent import AgentPlanError


class MultiChoiceAgentTests(unittest.TestCase):
    def test_fixture_oracle_is_independent_of_tool_response(self):
        self.assertEqual(independent_fixture_oracle("PIE_Large_Cube_00"), {
            "object_name": "PIE_Large_Cube_00", "object_type": "MESH",
            "location": [0, 0, 0], "material_names": ["PIE_Large_Material_00"],
        })
        self.assertEqual(independent_fixture_oracle("PIE_Large_Cube_13"), {
            "object_name": "PIE_Large_Cube_13", "object_type": "MESH",
            "location": [5, 1, 0], "material_names": ["PIE_Large_Material_03"],
        })
        self.assertEqual(independent_fixture_oracle("PIE_Large_Cube_63"), {
            "object_name": "PIE_Large_Cube_63", "object_type": "MESH",
            "location": [7, 7, 0], "material_names": ["PIE_Large_Material_15"],
        })
        for target in ("Cube", "PIE_Large_Cube_64", "PIE_Large_Cube_-1",
                       'PIE_Large_Cube_00"); print("bad")'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                independent_fixture_oracle(target)

    def test_tasks_require_different_choices_and_unique_exact_names(self):
        self.assertEqual([t["candidates"].index(t["target"]) for t in TASKS],
                         [1, 2, 0])
        self.assertEqual([t["tool_order"].index("exact") for t in TASKS],
                         [1, 0, 1])
        for task in TASKS:
            self.assertEqual(validate_task(task)[0], task["target"])
        with self.assertRaises(ValueError):
            validate_task({"target": "PIE_Large_Cube_00",
                           "candidates": ["PIE_Large_Cube_00"] * 3})

    def test_real_tool_schemas_reordered_and_allowlisted(self):
        for condition, valid_names in (
            ("baseline", ["get_scene_info", "execute_blender_code"]),
            ("optimized", ["pie_blender_query_scene", "pie_blender_get_object"]),
        ):
            catalog = [{"name": name, "inputSchema": {"type": "object"}}
                       for name in valid_names]
            one = ordered_catalog(catalog, condition, TASKS[0])
            two = ordered_catalog(catalog, condition, TASKS[1])
            self.assertEqual(one[-1]["name"],
                             "execute_blender_code" if condition == "baseline"
                             else "pie_blender_get_object")
            self.assertEqual(two[0]["name"], one[-1]["name"])
            with self.assertRaises(ValueError):
                ordered_catalog(catalog[:1], condition, TASKS[0])
            with self.assertRaises(ValueError):
                ordered_catalog(catalog + [{"name": "delete_object"}],
                                condition, TASKS[0])

    def test_baseline_extraction_contains_validated_target_no_mutation(self):
        code = _read_only_blender_code("PIE_Large_Cube_63")
        self.assertIn('bpy.context.scene.objects.get("PIE_Large_Cube_63")', code)
        self.assertNotIn("bpy.ops", code)
        self.assertNotIn("PIE_Large_Cube_00", code)
        with self.assertRaises(ValueError):
            _read_only_blender_code('Cube"); delete_scene(); #')

    def test_ollama_multi_choice_returns_nonzero_indices_and_never_gold(self):
        target_index = 2
        tool_index = 0
        response = {
            "done": True, "prompt_eval_count": 172, "eval_count": 25,
            "message": {"content": json.dumps({
                "tool_index": tool_index, "target_index": target_index})},
        }
        task = TASKS[1]
        catalog = [{"name": "pie_blender_get_object", "inputSchema": {"type": "object"}},
                   {"name": "pie_blender_query_scene", "inputSchema": {"type": "object"}}]

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, _): return json.dumps(response).encode()

        def answer(req, timeout):
            self.assertEqual(req.full_url, "http://127.0.0.1:11434/api/chat")
            payload = json.loads(req.data)
            messages = str(payload["messages"])
            self.assertIn(task["target"], messages)
            self.assertNotIn("PIE_Large_Material_15", messages)
            self.assertNotIn("expected_exact", messages)
            return FakeResponse()

        with patch("benchmark_blender_choice_agent.urlopen", side_effect=answer):
            plan = plan_choice("qwen3:4b", catalog, task)
        self.assertEqual((plan["tool_index"], plan["target_index"]), (0, 2))
        self.assertEqual(plan["usage"]["total_tokens"], 197)

    def test_wrong_target_or_tool_rejected_without_retry(self):
        task = TASKS[0]
        catalog = [{"name": "pie_blender_query_scene"}, {"name": "pie_blender_get_object"}]
        for plan in ({"tool_index": 0, "target_index": 1},
                     {"tool_index": 1, "target_index": 0},
                     {"tool_index": 17, "target_index": 1}):
            calls = []

            class FakeResponse:
                def __enter__(self): return self
                def __exit__(self, *_): return False
                def read(self, _): return json.dumps({
                    "done": True, "prompt_eval_count": 75, "eval_count": 19,
                    "message": {"content": json.dumps(plan)},
                }).encode()

            def once(req, timeout):
                calls.append(True)
                return FakeResponse()

            with self.subTest(plan=plan), patch(
                "benchmark_blender_choice_agent.urlopen", side_effect=once
            ), self.assertRaises(AgentPlanError):
                plan_choice("qwen3:4b", catalog, task)
            self.assertEqual(len(calls), 1)

    def test_agent_routes_real_mcp_only_after_nontrivial_selection(self):
        for condition, names, server in (
            ("baseline", ["get_scene_info", "execute_blender_code"], "blender"),
            ("optimized", ["pie_blender_query_scene", "pie_blender_get_object"],
             "pie-blender-optimized"),
        ):
            task = TASKS[0]
            timeline = []
            self_outer = self
            class FakeProbe:
                def __init__(self, process): pass
                def call(self, identifier, method, params=None):
                    timeline.append(method)
                    if method == "initialize": return {"result": {}}
                    if method == "tools/list":
                        return {"result": {"tools": [
                            {"name": name, "inputSchema": {"type": "object"}}
                            for name in names]}}
                    selected = params["name"]
                    expected = ("execute_blender_code" if condition == "baseline"
                                else "pie_blender_get_object")
                    self_outer.assertEqual(selected, expected)
                    item = independent_fixture_oracle(task["target"])
                    if condition == "baseline":
                        return {"result": {"content": [{"type": "text",
                            "text": "PIE_LOCAL_OBJECT_V1=" + json.dumps(item)}]}}
                    return {"result": {"content": [{"type": "text",
                        "text": json.dumps(item)}]}}
                def notify(self, method): pass
                def close(self): pass

            def fake_plan(*args, **kwargs):
                timeline.append("model-plan")
                return {
                    "tool_index": 1, "target_index": 1,
                    "usage": {"total_tokens": 170, "input_tokens": 155,
                              "output_tokens": 15},
                    "planning_ms": 7, "plan_sha256": "fixture-plan",
                }

            with (
                self.subTest(condition=condition),
                patch("benchmark_blender_choice_agent._profile", return_value=(
                    {"command": "python", "enabled_tools": names}, server, [], {})),
                patch("benchmark_blender_choice_agent.subprocess.Popen"),
                patch("benchmark_blender_choice_agent.Probe", FakeProbe),
                patch("benchmark_blender_choice_agent.plan_choice", side_effect=fake_plan),
            ):
                result = run_arm(Path("mcp.toml"), Path.cwd(), condition,
                                 task, "qwen3:4b")
                self.assertEqual(timeline,
                                 ["initialize", "tools/list", "model-plan", "tools/call"])
                self.assertTrue(result["oracle_pass"])
                self.assertEqual(result["selected_tool"],
                                 "execute_blender_code" if condition == "baseline"
                                 else "pie_blender_get_object")
                self.assertEqual((result["tool_index"], result["target_index"]), (1, 1))
                self.assertEqual(result["mcp_calls"], 1)

    def test_independent_oracle_blocks_incorrect_mcp_data(self):
        task = TASKS[0]
        class FakeProbe:
            def __init__(self, process): pass
            def call(self, identifier, method, params=None):
                if method == "initialize": return {"result": {}}
                if method == "tools/list":
                    return {"result": {"tools": [{"name": "pie_blender_get_object"},
                                                {"name": "pie_blender_query_scene"}]}}
                bad = independent_fixture_oracle(task["target"])
                bad["material_names"] = ["incorrect_material"]
                return {"result": {"content": [{"type": "text", "text": json.dumps(bad)}]}}
            def notify(self, method): pass
            def close(self): pass

        def selected(*a, **k):
            return {"tool_index": 1, "target_index": 1,
                    "usage": {"total_tokens": 200}, "planning_ms": 1,
                    "plan_sha256": "test"}
        with (
            patch("benchmark_blender_choice_agent._profile", return_value=(
                {"command": "python", "enabled_tools":
                 ["pie_blender_query_scene", "pie_blender_get_object"]},
                "pie-blender-optimized", [], {})),
            patch("benchmark_blender_choice_agent.subprocess.Popen"),
            patch("benchmark_blender_choice_agent.Probe", FakeProbe),
            patch("benchmark_blender_choice_agent.plan_choice", side_effect=selected),
        ):
            result = run_arm(Path("mcp.toml"), Path.cwd(), "optimized", task, "qwen3:4b")
            self.assertFalse(result["oracle_pass"])

    def test_usage_and_correctness_must_both_pass(self):
        left = {"oracle_pass": True, "usage": {"total_tokens": 340}}
        right = {"oracle_pass": True, "usage": {"total_tokens": 196}}
        self.assertEqual(compare_pair(left, right)["planning_token_savings_percent"], 42.353)
        right["oracle_pass"] = False
        self.assertEqual(compare_pair(left, right)["state"], "ORACLE_FAILED")


if __name__ == "__main__":
    unittest.main()
