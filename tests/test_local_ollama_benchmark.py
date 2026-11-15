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
    fixture_pass, run_local_model,
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
        payload = [{"content": [{"type": "text", "text": "PIE_Large_Cube_00 PIE_Large_Material_00"}]}]
        self.assertTrue(fixture_pass({"application": "blender"}, payload))
        self.assertFalse(fixture_pass({"application": "web"}, payload))

    def test_pair_comparison_requires_both_correct(self):
        a = {"oracle_pass": True, "usage": {"input_tokens": 800, "total_tokens": 1000}}
        b = {"oracle_pass": True, "usage": {"input_tokens": 400, "total_tokens": 500}}
        self.assertEqual(compare_pair(a, b)["total_token_savings_percent"], 50.0)
        b["oracle_pass"] = False
        self.assertEqual(compare_pair(a, b)["state"], "ORACLE_FAILED")

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
