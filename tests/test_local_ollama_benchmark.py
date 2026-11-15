"""Offline tests for the experimental Ollama MCP replay benchmark."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from benchmark_local_ollama import (
    _check_response, _provider_usage, _tool_calls, compare_pair, correct_answer,
    fixture_pass, run_local_model, ensure_local_model, collect_mcp, _recover_web_when_required,
    _visible_tool_schemas, local_experiment_scenario,
)


class LocalOllamaBenchmarkTests(unittest.TestCase):
    def test_tool_paths_are_fixed_and_read_only(self):
        base = _tool_calls("blender", "baseline")
        opt = _tool_calls("blender", "optimized")
        self.assertEqual(base[0][0], "execute_blender_code")
        self.assertIn('bpy.data.objects.get("PIE_Large_Cube_00")', base[0][1]["code"])
        self.assertNotIn("bpy.ops", base[0][1]["code"])
        self.assertEqual(opt[0][0], "pie_blender_query_scene")
        self.assertEqual(opt[0][1]["limit"], 1)
        exact = _tool_calls("blender", "optimized", blender_mode="exact")
        self.assertEqual(exact, [("pie_blender_get_object", {"name": "PIE_Large_Cube_00"})])
        self.assertEqual([x[0] for x in _tool_calls("web", "baseline")],
                         ["browser_navigate", "browser_snapshot"])

    def test_mcp_errors_do_not_start_local_model(self):
        with self.assertRaises(RuntimeError):
            _check_response({"result": {"isError": True}}, "tool")
        with self.assertRaises(RuntimeError):
            _check_response({"error": {"code": -1}}, "tool")

    def test_ollama_reports_real_token_counts_or_fails(self):
        correct = {"done": True, "prompt_eval_count": 200, "eval_count": 30,
                   "total_duration": 5_000_000}
        self.assertEqual(_provider_usage(correct)["total_tokens"], 230)
        for invalid in ({"done": False, "prompt_eval_count": 20, "eval_count": 10},
                        {"done": True, "prompt_eval_count": "100", "eval_count": 20}):
            with self.subTest(invalid=invalid), self.assertRaises(RuntimeError):
                _provider_usage(invalid)

    def test_oracles_fail_closed(self):
        scenario = {"application": "web", "expected_exact": '{"title":"T"}'}
        self.assertEqual(correct_answer(scenario, '{"title":"T"}'), (True, True))
        self.assertEqual(correct_answer(scenario, '{ "title" : "T" }'), (True, False))
        self.assertEqual(correct_answer(scenario, '{"title":"wrong"}'), (False, False))
        self.assertEqual(correct_answer(scenario, 'not json'), (False, False))
        payload = [{"content": [{"type": "text", "text":
            'Code executed successfully: PIE_LOCAL_OBJECT_V1={"object_name":"PIE_Large_Cube_00","object_type":"MESH","location":[0,0,0],"material_names":["PIE_Large_Material_00"]}'}]}]
        blender_scenario = {"application": "blender", "expected_exact": json.dumps({
            "object_name": "PIE_Large_Cube_00", "object_type": "MESH",
            "location": [0.0, 0.0, 0.0], "material_names": ["PIE_Large_Material_00"]})}
        self.assertTrue(fixture_pass(blender_scenario, payload))
        self.assertFalse(fixture_pass(blender_scenario, [{"content": [{"type": "text", "text": "PIE_Large_Cube_00 PIE_Large_Material_00"}]}]))
        self.assertFalse(fixture_pass({"application": "web"}, payload))
        direct = [{"content": [{"type": "text", "text": blender_scenario["expected_exact"]}]}]
        self.assertTrue(fixture_pass(blender_scenario, direct))

    def test_pair_comparison_requires_both_correct(self):
        a = {"oracle_pass": True, "usage": {"input_tokens": 800, "total_tokens": 1000}}
        b = {"oracle_pass": True, "usage": {"input_tokens": 400, "total_tokens": 500}}
        self.assertEqual(compare_pair(a, b)["total_token_savings_percent"], 50.0)
        b["oracle_pass"] = False
        self.assertEqual(compare_pair(a, b)["state"], "ORACLE_FAILED")

    def test_local_model_must_be_installed_not_cloud(self):
        with self.assertRaises(RuntimeError):
            ensure_local_model("qwen3:cloud")
        reply = {"models": [{"name": "qwen3:4b"}]}

        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self, *_):return False
            def read(self, _):return json.dumps(reply).encode()

        with patch("benchmark_local_ollama.urlopen", return_value=FakeResponse()):
            ensure_local_model("qwen3:4b")
            with self.assertRaises(RuntimeError):
                ensure_local_model("missing:2b")

    def test_client_tool_allowlist_eliminates_raw_server_schema_confound(self):
        tools = [{"name": "execute_blender_code", "inputSchema": {"type": "object"}},
                 {"name": "get_scene_info", "inputSchema": {"type": "object"}},
                 {"name": "delete_object", "inputSchema": {"type": "object"}}]
        config = {"enabled_tools": ["execute_blender_code"]}
        effective = _visible_tool_schemas(tools, config, "profile")
        self.assertEqual([item["name"] for item in effective], ["execute_blender_code"])
        self.assertEqual(len(_visible_tool_schemas(tools, config, "server")), 3)
        for invalid in ({"enabled_tools": ["missing"]},
                        {"enabled_tools": []},
                        {"enabled_tools": ["execute_blender_code", "execute_blender_code"]},
                        {}):
            with self.subTest(invalid=invalid), self.assertRaises(RuntimeError):
                _visible_tool_schemas(tools, invalid, "profile")

    def test_web_recovers_compacted_snapshot_only_if_required(self):
        scenario = {"application": "web"}
        compact = [{"content": [{"type": "text", "text": json.dumps({
            "pie_gateway": "v1", "output_id": "valid-fixture-output", "preview": "PIE Web Fixture"})}]}]
        text = ("PIE Web Fixture Inspect materials "
                "Deterministic browser certification fixture.")
        class FakeProbe:
            def __init__(self):
                self.calls = []
            def call(self, identifier, method, params):
                self.calls.append((identifier, params))
                return {"result": {"content": [{"type": "text", "text": json.dumps({
                    "text": text, "next_start": None, "output_id": "valid-fixture-output"})}]}}
        probe = FakeProbe()
        result, count = _recover_web_when_required(
            probe, list(compact), {"pie_gateway_output_get"}, scenario, 5)
        self.assertEqual(count, 1)
        self.assertEqual(len(result), 2)
        self.assertEqual(probe.calls[0][1]["arguments"]["output_id"], "valid-fixture-output")
        self.assertTrue(fixture_pass(scenario, result))
        no_tool, no_calls = _recover_web_when_required(
            probe, list(compact), set(), scenario, 5)
        self.assertEqual(no_calls, 0)
        self.assertEqual(no_tool, compact)
        complete = [{"content": [{"type": "text", "text": text}]}]
        _, count = _recover_web_when_required(probe, complete, {"pie_gateway_output_get"}, scenario, 5)
        self.assertEqual(count, 0)
        self.assertEqual(len(probe.calls), 1)

    def test_blender_mcp_protocol_is_replayed_for_both_arms(self):
        scenario = {"application": "blender", "expected_exact": json.dumps({
            "object_name": "PIE_Large_Cube_00", "object_type": "MESH",
            "location": [0, 0, 0], "material_names": ["PIE_Large_Material_00"]})}

        class FakeProbe:
            def __init__(self, _process):
                self.requests = []
            def call(self, identifier, method, params=None):
                self.requests.append(method)
                if method == "initialize":
                    return {"result": {"protocolVersion": "2025-03-26"}}
                if method == "tools/list":
                    return {"result": {"tools": [
                        {"name": "execute_blender_code"}, {"name": "pie_blender_query_scene"},
                        {"name": "pie_blender_get_object"}]}}
                if params["name"] == "execute_blender_code":
                    item = json.loads(scenario["expected_exact"])
                    return {"result": {"content": [{"type": "text", "text":
                        "PIE_LOCAL_OBJECT_V1=" + json.dumps(item)}]}}
                if params["name"] == "pie_blender_get_object":
                    return {"result": {"content": [{"type": "text",
                        "text": scenario["expected_exact"]}]}}
                item = {"name": "PIE_Large_Cube_00", "type": "MESH",
                        "location": [0, 0, 0], "material_names": ["PIE_Large_Material_00"]}
                return {"result": {"structuredContent": {"items": [item]}, "content": []}}
            def notify(self, _method):pass
            def close(self):pass

        for condition, server in (("baseline", "blender"),
                                  ("optimized", "pie-blender-optimized")):
            with (
                self.subTest(condition=condition),
                patch("benchmark_local_ollama._profile", return_value=(
                    {"command": "python", "enabled_tools": [
                        "execute_blender_code" if condition == "baseline" else "pie_blender_query_scene"
                    ]}, server, [], {})),
                patch("benchmark_local_ollama.subprocess.Popen"),
                patch("benchmark_local_ollama.Probe", FakeProbe),
            ):
                result = collect_mcp(Path("profile.toml"), Path.cwd(), scenario, condition)
                self.assertEqual(result["server"], server)
                self.assertGreater(result["observation_chars"], 0)
                self.assertEqual(len(result["tool_names"]), 1)

    def test_exact_blender_benchmark_routes_via_minimal_mcp_tool(self):
        scenario = {"application": "blender", "expected_exact": json.dumps({
            "object_name": "PIE_Large_Cube_00", "object_type": "MESH",
            "location": [0, 0, 0], "material_names": ["PIE_Large_Material_00"]})}

        class FakeProbe:
            def __init__(self, process):pass
            def call(self, identifier, method, params=None):
                if method == "initialize":
                    return {"result": {"protocolVersion": "2025-03-26"}}
                if method == "tools/list":
                    return {"result": {"tools": [{"name": "pie_blender_get_object",
                                                   "inputSchema": {"type": "object"}}]}}
                return {"result": {"content": [{"type": "text",
                                                "text": scenario["expected_exact"]}]}}
            def notify(self, method):pass
            def close(self):pass

        with (patch("benchmark_local_ollama._profile", return_value=(
                    {"command": "python", "enabled_tools": ["pie_blender_get_object"]},
                    "pie-blender-optimized", [], {})),
              patch("benchmark_local_ollama.subprocess.Popen"),
              patch("benchmark_local_ollama.Probe", FakeProbe)):
            result = collect_mcp(Path("profile.toml"), Path.cwd(), scenario,
                                 "optimized", blender_mode="exact")
            self.assertEqual(result["tool_names"], ["pie_blender_get_object"])
            self.assertEqual(result["tool_count"], 1)
            self.assertEqual(result["recovery_calls"], 0)
            self.assertIn("PIE_Large_Cube_00", result["observations_json"])

    def test_exact_mode_changes_only_local_prompt_and_is_paired(self):
        original = {"application": "blender", "prompt":
                    "in the optimized configuration, use pie_blender_query_scene only"}
        revised = local_experiment_scenario(original, "exact")
        self.assertIn("pie_blender_get_object only", revised["prompt"])
        self.assertEqual(original["prompt"],
                         "in the optimized configuration, use pie_blender_query_scene only")
        self.assertEqual(local_experiment_scenario(original, "query"), original)
        with self.assertRaises(ValueError):
            local_experiment_scenario({"application": "blender", "prompt": "unrelated"}, "exact")

    def test_local_model_request_is_local_and_records_usage(self):
        scenario = {"application": "web", "expected_exact": '{"title":"T"}', "prompt": "Extract title."}
        obs = {"schema_json": "[]", "observations_json": "[]"}
        reply = {"done": True, "prompt_eval_count": 500, "eval_count": 25,
                 "message": {"content": '{"title":"T"}'}}

        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self, *_):return False
            def read(self, _):return json.dumps(reply).encode()

        def call(req, timeout):
            self.assertTrue(req.full_url.startswith("http://127.0.0.1:11434/"))
            self.assertEqual(json.loads(req.data)["stream"], False)
            return FakeResponse()

        with patch("benchmark_local_ollama.urlopen", side_effect=call):
            result = run_local_model(scenario, obs, "qwen3:4b", 20, 4096)
        self.assertTrue(result["oracle_pass"])
        self.assertEqual(result["usage"]["total_tokens"], 525)


if __name__ == "__main__":
    unittest.main()
