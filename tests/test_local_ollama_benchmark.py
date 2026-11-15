"""Offline tests for the experimental Ollama MCP replay benchmark."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from benchmark_local_ollama import (
    _check_response, _provider_usage, _tool_calls, compare_pair, correct_answer,
    fixture_pass, run_local_model, ensure_local_model, collect_mcp, _recover_web_when_required,
    _visible_tool_schemas, local_experiment_scenario,
    grounded_blender_exact_answer, model_source_mismatches,
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
        large = _tool_calls("web", "optimized",
                            scenario={"fixture_url": "http://127.0.0.1:8767/index.html"})
        self.assertEqual(large[0][1]["url"], "http://127.0.0.1:8767/index.html")

    def test_mcp_errors_do_not_start_local_model(self):
        with self.assertRaisesRegex(RuntimeError, "tool error"):
            _check_response({"result": {"isError": True}}, "tool")
        with self.assertRaisesRegex(RuntimeError, "JSON-RPC error"):
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

    def test_exact_source_rendering_preserves_identifiers_without_model_copy(self):
        value = {
            "object_name": "PIE_Large_Cube_00",
            "object_type": "MESH",
            "location": [0.0, 0.0, 0.0],
            "material_names": ["PIE_Large_Material_00"],
        }
        observation = {"observations_json": json.dumps([{
            "content": [{"type": "text", "text": json.dumps(value)}]
        }])}
        source = grounded_blender_exact_answer(observation, "PIE_Large_Cube_00")
        self.assertEqual(json.loads(source), value)
        bad_model = source.replace("PIE_Large_Cube_00", "PIE_Large_Cube_0:00")
        self.assertEqual(model_source_mismatches(bad_model, source), ["object_name"])
        self.assertEqual(model_source_mismatches(source, source), [])
        self.assertEqual(model_source_mismatches("not json", source), ["INVALID_MODEL_JSON"])
        with self.assertRaises(ValueError):
            grounded_blender_exact_answer(observation, "PIE_Large_Cube_0:00")
        for invalid in (
            {"content": [{"type": "text", "text": json.dumps({"name": "Cube"})}]},
            {"content": [{"type": "text", "text": json.dumps(value)}],
             "structuredContent": value},
            {"content": [{"type": "text", "text": json.dumps(value)},
                         {"type": "text", "text": "duplicate"}]},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                grounded_blender_exact_answer(
                    {"observations_json": json.dumps([invalid])}, "PIE_Large_Cube_00")

    def test_copy_error_never_promoted_to_model_oracle_pass(self):
        value = {"object_name": "PIE_Large_Cube_00", "object_type": "MESH",
                 "location": [0.0, 0.0, 0.0], "material_names": ["PIE_Large_Material_00"]}
        source = json.dumps(value, separators=(",", ":"))
        model_response = source.replace("PIE_Large_Cube_00", "PIE_Large_Cube_0:00")
        scenario = {"application": "blender", "expected_exact": source, "prompt": "Read object"}
        obs = {"schema_json": "[]", "observations_json": "[]", "grounded_answer": source}
        reply = {"done": True, "prompt_eval_count": 355, "eval_count": 64,
                 "message": {"content": model_response}}

        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self, *_):return False
            def read(self, _):return json.dumps(reply).encode()

        with patch("benchmark_local_ollama.urlopen", return_value=FakeResponse()):
            result = run_local_model(scenario, obs, "qwen3:4b", 10, 8192)
        self.assertFalse(result["oracle_pass"])
        self.assertTrue(result["source_oracle_pass"])
        self.assertEqual(result["usage"]["total_tokens"], 419)
        self.assertEqual(result["model_mismatch_fields"], ["object_name"])
        self.assertEqual(result["source_rendering"],
                         "DETERMINISTIC_TOOL_DATA_NOT_MODEL_OUTPUT")
        self.assertEqual(compare_pair(
            {"oracle_pass": True, "usage": {"total_tokens": 647, "input_tokens": 584}},
            result)["state"], "ORACLE_FAILED")

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

    def test_local_model_reports_http_status_without_response_body(self):
        scenario = {"application": "web", "expected_exact": '{"title":"T"}',
                    "prompt": "Extract title."}
        obs = {"schema_json": "[]", "observations_json": "[]"}
        error = HTTPError("http://127.0.0.1:11434/api/chat", 500,
                          "server error", hdrs=None, fp=None)
        with patch("benchmark_local_ollama.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, r"HTTP error 500: server error"):
                run_local_model(scenario, obs, "qwen3:4b", 20, 4096)

    def test_local_model_distinguishes_invalid_json_from_unavailable(self):
        scenario = {"application": "web", "expected_exact": '{"title":"T"}',
                    "prompt": "Extract title."}
        obs = {"schema_json": "[]", "observations_json": "[]"}

        class FakeResponse:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def getcode(self): return self.status
            def read(self, _): return b"not-json"

        with patch("benchmark_local_ollama.urlopen", return_value=FakeResponse()):
            with self.assertRaisesRegex(RuntimeError, r"invalid JSON \(HTTP 200\)"):
                run_local_model(scenario, obs, "qwen3:4b", 20, 4096)

    def test_openai_compatible_provider_usage_and_response(self):
        scenario = {"application": "web", "expected_exact": '{"title":"T"}',
                    "prompt": "Extract title."}
        obs = {"schema_json": "[]", "observations_json": "[]"}
        reply = {"model": "gambiarraapi/glm-5.3-flash",
                 "choices": [{"message": {"content": '{"title":"T"}'}}],
                 "usage": {"prompt_tokens": 10, "completion_tokens": 8,
                            "total_tokens": 18,
                            "completion_tokens_details": {"reasoning_tokens": 8}}}

        class FakeResponse:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def getcode(self): return self.status
            def read(self, _): return json.dumps(reply).encode()

        with patch.dict("os.environ", {"PIE_PROVIDER_BASE_URL": "http://127.0.0.1:8080/v1",
                                        "PIE_PROVIDER_API_KEY": "local-test"}, clear=False):
            with patch("benchmark_local_ollama.urlopen", return_value=FakeResponse()):
                result = run_local_model(scenario, obs, "gambiarraapi/glm-5.3-flash", 20, 4096)
        self.assertTrue(result["oracle_pass"])
        self.assertEqual(result["usage"]["total_tokens"], 18)
        self.assertEqual(result["usage"]["reasoning_output_tokens"], 8)


if __name__ == "__main__":
    unittest.main()
