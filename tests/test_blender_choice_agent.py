"""Offline fail-closed tests for the Blender multi-choice evidence agent."""
import json
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from benchmark_blender_choice_agent import (
    TASKS, ChoicePlanError, _read_only_blender_code, compare_pair,
    deterministic_choice, planning_catalog,
    independent_fixture_oracle, ordered_catalog, plan_choice, plan_target_choice,
    plan_observation_target, add_usage, model_observation_payload, run_arm,
    safe_plan_failure, main, validate_task,
)
from benchmark_blender_evidence_agent import AgentPlanError
from verify_phase3_mcp_profiles import Probe


class MultiChoiceAgentTests(unittest.TestCase):
    def test_add_usage_requires_reported_provider_fields(self):
        self.assertEqual(add_usage(
            {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
            {"input_tokens": 4, "output_tokens": 1, "total_tokens": 5}),
            {"input_tokens": 6, "output_tokens": 4, "total_tokens": 10})
        with self.assertRaises(ValueError):
            add_usage({"total_tokens": 5}, {"input_tokens": 1,
                                             "output_tokens": 1,
                                             "total_tokens": 2})

    def test_model_observation_deduplicates_equal_structured_result(self):
        content = [{"type": "text", "text": "same"}]
        self.assertEqual(model_observation_payload({
            "content": content, "structuredContent": {"result": "same"}}),
            {"content": content})
        self.assertIn("structuredContent", model_observation_payload({
            "content": content, "structuredContent": {"result": "different"}}))

    def test_target_plan_accepts_only_target_index(self):
        from benchmark_blender_choice_agent import _parse_target_plan
        response = {"message": {"content": '{"target_index": 1}'}}
        self.assertEqual(_parse_target_plan(response, target_count=3), 1)
        with self.assertRaises(AgentPlanError):
            _parse_target_plan({"message": {"content":
                '{"target_index": 1, "tool_index": 0}'}}, target_count=3)

    def test_planner_catalog_excludes_execution_schemas(self):
        catalog = [
            {"name": "pie_blender_get_object", "description": "exact",
             "inputSchema": {"properties": {"name": {"type": "string"}}}},
            {"name": "pie_blender_query_scene", "description": "broad",
             "inputSchema": {"properties": {"fields": {"enum": ["x"]}}}},
        ]
        self.assertEqual(planning_catalog(catalog), [
            {"index": 0, "name": "pie_blender_get_object", "description": "exact"},
            {"index": 1, "name": "pie_blender_query_scene", "description": "broad"},
        ])

    def test_probe_close_closes_all_stdio_streams_after_exit(self):
        process = mock.Mock()
        process.stdin = io.StringIO()
        process.stdout = io.StringIO()
        process.stderr = io.StringIO()
        process.wait.return_value = 0
        Probe(process).close()
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)
        self.assertTrue(process.stderr.closed)

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

    def test_failure_codes_record_actual_bad_selection_and_usage(self):
        task = TASKS[0]
        catalog = [{"name": "pie_blender_query_scene"}, {"name": "pie_blender_get_object"}]
        cases = (
            ('{"tool_index":0,"target_index":1}', "NON_EXACT_TOOL_SELECTED", (0, 1)),
            ('{"tool_index":1,"target_index":0}', "WRONG_TARGET_SELECTED", (1, 0)),
            ('{"tool_index":17,"target_index":1}', "INVALID_TOOL_INDEX", None),
            ('{"tool_index":false,"target_index":1}', "INVALID_TOOL_INDEX", None),
            ('{"tool_index":1,"target_index":8}', "INVALID_TARGET_INDEX", None),
            ('{"tool_index":1}', "INVALID_PLAN_SHAPE", None),
            ('not json', "INVALID_MODEL_JSON", None),
        )
        for response_text, code, indices in cases:
            calls = []
            class FakeResponse:
                def __enter__(self): return self
                def __exit__(self, *_): return False
                def read(self, _): return json.dumps({
                    "done": True, "prompt_eval_count": 75, "eval_count": 19,
                    "message": {"content": response_text},
                }).encode()

            def once(req, timeout):
                calls.append(True)
                return FakeResponse()

            with self.subTest(code=code), patch(
                "benchmark_blender_choice_agent.urlopen", side_effect=once
            ):
                with self.assertRaises(ChoicePlanError) as failure:
                    plan_choice("qwen3:4b", catalog, task)
            self.assertEqual(len(calls), 1)
            details = safe_plan_failure(failure.exception, "baseline")
            self.assertEqual(details["failure_code"], code)
            self.assertEqual(details["failed_condition"], "baseline")
            self.assertEqual(details["mcp_tool_calls_executed"], 0)
            self.assertEqual(details["failed_plan_usage"]["total_tokens"], 94)
            self.assertTrue(details["model_request_attempted"])
            self.assertEqual(len(details["failed_plan_sha256"]), 64)
            self.assertNotIn(response_text, str(details))
            if indices is not None:
                self.assertEqual(
                    (details["selected_tool_index"], details["selected_target_index"]),
                    indices)
            else:
                self.assertNotIn("selected_target_index", details)

    def test_diagnostic_handles_missing_response_without_inventing_usage(self):
        catalog = [{"name": "pie_blender_query_scene"}, {"name": "pie_blender_get_object"}]
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, _): return json.dumps({
                "done": True, "prompt_eval_count": 75, "eval_count": 19,
                "message": {"content": None},
            }).encode()

        with patch("benchmark_blender_choice_agent.urlopen", return_value=FakeResponse()):
            with self.assertRaises(ChoicePlanError) as caught:
                plan_choice("qwen3:4b", catalog, TASKS[0])
        info = safe_plan_failure(caught.exception, "optimized")
        self.assertEqual(info["failure_code"], "MISSING_MODEL_CONTENT")
        self.assertNotIn("failed_plan_sha256", info)
        self.assertTrue(info["model_request_attempted"])
        for pre_model in ("INVALID_CATALOG_SIZE", "PLANNING_PAYLOAD_OVERSIZED"):
            with self.subTest(pre_model=pre_model):
                diagnostic = safe_plan_failure(
                    ChoicePlanError(pre_model), "baseline")
                self.assertFalse(diagnostic["model_request_attempted"])
                self.assertNotIn("failed_plan_usage", diagnostic)

    def test_deterministic_exact_route_picks_different_indices_without_model(self):
        for condition, names in (
            ("baseline", ["get_scene_info", "execute_blender_code"]),
            ("optimized", ["pie_blender_query_scene", "pie_blender_get_object"]),
        ):
            catalog = [{"name": name} for name in names]
            actual = []
            for task in TASKS:
                ordered = ordered_catalog(catalog, condition, task)
                route = deterministic_choice(ordered, task, condition)
                actual.append((route["tool_index"], route["target_index"]))
                self.assertEqual(route["provider_requests"], 0)
                self.assertIsNone(route["usage"])
                self.assertIsNone(route["plan_sha256"])
            self.assertEqual(actual, [(1, 1), (0, 2), (1, 0)])

    def test_deterministic_arm_executes_real_mcp_path_without_ollama(self):
        for condition, names, server in (
            ("baseline", ["get_scene_info", "execute_blender_code"], "blender"),
            ("optimized", ["pie_blender_query_scene", "pie_blender_get_object"],
             "pie-blender-optimized"),
        ):
            for task in TASKS:
                events = []
                fixture = independent_fixture_oracle(task["target"])
                class FakeProbe:
                    def __init__(self, process): pass
                    def call(self, identifier, method, params=None):
                        events.append(method)
                        if method == "initialize":
                            return {"result": {}}
                        if method == "tools/list":
                            return {"result": {"tools": [
                                {"name": name, "inputSchema": {"type": "object"}}
                                for name in names]}}
                        self_outer.assertEqual(params["name"],
                            "execute_blender_code" if condition == "baseline"
                            else "pie_blender_get_object")
                        if condition == "baseline":
                            return {"result": {"content": [{"type": "text",
                                "text": "PIE_LOCAL_OBJECT_V1=" + json.dumps(fixture)}]}}
                        return {"result": {"content": [{"type": "text",
                            "text": json.dumps(fixture)}]}}
                    def notify(self, method): pass
                    def close(self): pass
                self_outer = self
                with (
                    self.subTest(condition=condition, task=task["task_id"]),
                    patch("benchmark_blender_choice_agent._profile", return_value=(
                        {"command": "python", "enabled_tools": names},
                        server, [], {})),
                    patch("benchmark_blender_choice_agent.subprocess.Popen"),
                    patch("benchmark_blender_choice_agent.Probe", FakeProbe),
                    patch("benchmark_blender_choice_agent.plan_choice") as qwen,
                ):
                    arm = run_arm(Path("mcp.toml"), Path.cwd(), condition, task,
                                  "qwen3:4b", route_mode="deterministic")
                    qwen.assert_not_called()
                    self.assertTrue(arm["oracle_pass"])
                    self.assertEqual(arm["mcp_calls"], 1)
                    self.assertEqual(arm["provider_requests"], 0)
                    self.assertIsNone(arm["usage"])
                    self.assertEqual(events, ["initialize", "tools/list", "tools/call"])

    def test_deterministic_pair_is_not_misreported_as_token_savings(self):
        baseline = {"oracle_pass": True, "usage": None}
        optimized = {"oracle_pass": True, "usage": None}
        result = compare_pair(baseline, optimized)
        self.assertEqual(result["state"], "DETERMINISTIC_ROUTING_NO_MODEL")
        self.assertIsNone(result["planning_token_savings_percent"])
        self.assertEqual(result["provider_requests"], 0)
        with self.assertRaises(ValueError):
            # An unsafe tool cannot be promoted into an exact route.
            deterministic_choice([{"name": "delete_object"}], TASKS[0], "optimized")

    def test_main_preserves_fail_closed_report_without_second_arm_or_retries(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            scenario = base / "fixture.json"
            scenario.write_text("{}", encoding="utf-8")
            left = base / "baseline.toml"
            right = base / "optimized.toml"
            left.write_text("", encoding="utf-8")
            right.write_text("", encoding="utf-8")
            report = base / "failure.json"
            calls = []
            class FailedSession:
                def run_task(self, *args, **kwargs):
                    calls.append(True)
                    raise ChoicePlanError(
                        "WRONG_TARGET_SELECTED",
                        usage={"input_tokens": 75, "output_tokens": 19,
                               "total_tokens": 94},
                        plan_sha256="a" * 64, indices=(1, 0),
                        model_request_attempted=True)

                def close(self):
                    pass
            with (
                patch("benchmark_blender_choice_agent.ensure_local_model"),
                patch("benchmark_blender_choice_agent.ChoiceMcpSession",
                      return_value=FailedSession()),
            ):
                code = main([
                    "--workspace", str(base),
                    "--baseline-profile", str(left),
                    "--optimized-profile", str(right),
                    "--output", str(report),
                    "--max-tasks", "3",
                ])
            self.assertEqual(code, 2)
            self.assertEqual(len(calls), 1)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(len(data["rows"]), 1)
            row = data["rows"][0]
            self.assertEqual(row["status"], "FAILED_CLOSED")
            self.assertEqual(row["failure_code"], "WRONG_TARGET_SELECTED")
            self.assertEqual(row["failed_condition"], "baseline")
            self.assertEqual(row["mcp_tool_calls_executed"], 0)
            self.assertEqual(row["arms"], {})
            self.assertNotIn("comparison", row)
            self.assertEqual(row["failed_plan_usage"]["total_tokens"], 94)

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
                                 task, "qwen3:4b", route_mode="model")
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
            result = run_arm(Path("mcp.toml"), Path.cwd(), "optimized", task,
                             "qwen3:4b", route_mode="model")
            self.assertFalse(result["oracle_pass"])

    def test_usage_and_correctness_must_both_pass(self):
        left = {"oracle_pass": True, "usage": {"total_tokens": 340}}
        right = {"oracle_pass": True, "usage": {"total_tokens": 196}}
        self.assertEqual(compare_pair(left, right)["planning_token_savings_percent"], 42.353)
        right["oracle_pass"] = False
        self.assertEqual(compare_pair(left, right)["state"], "ORACLE_FAILED")


if __name__ == "__main__":
    unittest.main()
