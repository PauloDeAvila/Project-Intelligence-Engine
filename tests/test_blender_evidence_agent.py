"""Fail-closed offline tests for Blender model-selection/source-render agent."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from benchmark_blender_evidence_agent import (
    AgentPlanError, OBJECT_NAME, _parse_plan, compare_pair,
    plan_ollama, render_baseline_source, run_arm,
)


def fixture():
    return {
        "object_name": OBJECT_NAME, "object_type": "MESH",
        "location": [0.0, 0.0, 0.0], "material_names": ["PIE_Large_Material_00"],
    }


class EvidenceAgentTests(unittest.TestCase):
    def test_planning_validates_indices_not_model_copied_facts(self):
        valid = {"message": {"content": '{"tool_index":0,"target_index":0}'}}
        self.assertEqual(_parse_plan(valid, allowed_tool_count=1, target_count=1), (0, 0))
        for body in (
            '{"tool_index":1,"target_index":0}',
            '{"tool_index":0,"target_index":2}',
            '{"tool_index":false,"target_index":0}',
            '{"tool_index":0,"target_index":0,"object_name":"wrong"}',
            '{"tool_index":0,"object_name":"Cube"}',
            "bad json",
        ):
            with self.subTest(body=body), self.assertRaises(AgentPlanError):
                _parse_plan({"message": {"content": body}},
                            allowed_tool_count=1, target_count=1)

    def test_baseline_renders_source_directly_and_never_fabricates_name(self):
        reply = {"content": [{"type": "text",
                 "text": "Code executed successfully: PIE_LOCAL_OBJECT_V1="
                         + json.dumps(fixture())}]}
        rendered = render_baseline_source(reply)
        self.assertEqual(json.loads(rendered), fixture())
        bad = {"content": [{"type": "text", "text": "PIE_LOCAL_OBJECT_V1="
                           + json.dumps({**fixture(), "object_name": "PIE_Large_Cube_0:00"})}]}
        with self.assertRaises(ValueError):
            render_baseline_source(bad)
        with self.assertRaises(ValueError):
            render_baseline_source({"content": []})

    def test_plan_model_prompt_only_requests_indices(self):
        reply = {"done": True, "prompt_eval_count": 100, "eval_count": 12,
                 "message": {"content": '{"tool_index":0,"target_index":0}'}}

        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self, *_):return False
            def read(self, _):return json.dumps(reply).encode()

        def answer(req, timeout):
            self.assertEqual(req.full_url, "http://127.0.0.1:11434/api/chat")
            body = json.loads(req.data)
            self.assertNotIn("expected_exact", str(body))
            self.assertIn("target_index", body["messages"][0]["content"])
            return FakeResponse()

        with patch("benchmark_blender_evidence_agent.urlopen", side_effect=answer):
            result = plan_ollama("qwen3:4b", [{"name": "pie_blender_get_object"}])
        self.assertEqual((result["tool_index"], result["target_index"]), (0, 0))
        self.assertEqual(result["usage"]["total_tokens"], 112)

    def test_invalid_plan_is_not_corrected_or_retried(self):
        calls = 0
        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self, *_):return False
            def read(self, _):return json.dumps({
                "done": True, "prompt_eval_count": 100, "eval_count": 10,
                "message": {"content": '{"tool_index":1,"target_index":0}'},
            }).encode()

        def answer(req, timeout):
            nonlocal calls
            calls += 1
            return FakeResponse()

        with patch("benchmark_blender_evidence_agent.urlopen", side_effect=answer):
            with self.assertRaises(AgentPlanError):
                plan_ollama("qwen3:4b", [{"name": "pie_blender_get_object"}])
        self.assertEqual(calls, 1)

    def test_agent_executes_mcp_after_model_choice_and_preserves_source(self):
        scenario = {"application": "blender", "expected_exact": json.dumps(fixture())}
        for condition, tool, server in (
            ("baseline", "execute_blender_code", "blender"),
            ("optimized", "pie_blender_get_object", "pie-blender-optimized"),
        ):
            timeline = []
            class FakeProbe:
                def __init__(self, process):pass
                def call(self, identifier, method, params=None):
                    timeline.append(method)
                    if method == "initialize":
                        return {"result": {"protocolVersion": "2025-03-26"}}
                    if method == "tools/list":
                        return {"result": {"tools": [{"name": tool, "inputSchema": {"type": "object"}}]}}
                    self_name = params["name"]
                    self_outer.assertEqual(self_name, tool)
                    if condition == "baseline":
                        return {"result": {"content": [{"type": "text",
                            "text": "PIE_LOCAL_OBJECT_V1=" + json.dumps(fixture())}]}}
                    return {"result": {"content": [{"type": "text",
                        "text": json.dumps(fixture())}]}}
                def notify(self, method):pass
                def close(self):pass

            def fake_plan(*args, **kwargs):
                timeline.append("model-plan")
                return {"tool_index": 0, "target_index": 0,
                        "usage": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110},
                        "planning_wall_ms": 5, "plan_sha256": "hash"}

            self_outer = self
            with (
                self.subTest(condition=condition),
                patch("benchmark_blender_evidence_agent._profile", return_value=(
                    {"command": "python", "enabled_tools": [tool]}, server, [], {})),
                patch("benchmark_blender_evidence_agent.subprocess.Popen"),
                patch("benchmark_blender_evidence_agent.Probe", FakeProbe),
                patch("benchmark_blender_evidence_agent.plan_ollama", side_effect=fake_plan),
            ):
                result = run_arm(Path("profile.toml"), Path.cwd(), scenario,
                                 condition, "qwen3:4b")
                self.assertEqual(timeline,
                                 ["initialize", "tools/list", "model-plan", "tools/call"])
                self.assertTrue(result["oracle_pass"])
                self.assertEqual(result["mcp_calls"], 1)
                self.assertEqual(result["rendering"],
                                 "DETERMINISTIC_TOOL_DATA_NOT_MODEL_OUTPUT")

    def test_reject_bad_schema_before_model_and_no_tool_call(self):
        events = []
        class FakeProbe:
            def __init__(self, process):pass
            def call(self, identifier, method, params=None):
                events.append(method)
                if method == "initialize":
                    return {"result": {}}
                return {"result": {"tools": [{"name": "unexpected"}]}}
            def notify(self, method):pass
            def close(self):pass

        scenario = {"application": "blender", "expected_exact": json.dumps(fixture())}
        with (
            patch("benchmark_blender_evidence_agent._profile", return_value=(
                {"command": "python", "enabled_tools": ["unexpected"]},
                "pie-blender-optimized", [], {})),
            patch("benchmark_blender_evidence_agent.subprocess.Popen"),
            patch("benchmark_blender_evidence_agent.Probe", FakeProbe),
            patch("benchmark_blender_evidence_agent.plan_ollama") as planning,
        ):
            with self.assertRaises(ValueError):
                run_arm(Path("profile.toml"), Path.cwd(), scenario,
                        "optimized", "qwen3:4b")
            planning.assert_not_called()
            self.assertNotIn("tools/call", events)

    def test_comparison_counts_planning_tokens_only(self):
        baseline = {"oracle_pass": True, "usage": {"total_tokens": 400}}
        optimized = {"oracle_pass": True, "usage": {"total_tokens": 300}}
        self.assertEqual(compare_pair(baseline, optimized)["savings_percent"], 25.0)
        optimized["oracle_pass"] = False
        self.assertEqual(compare_pair(baseline, optimized)["state"], "ORACLE_FAILED")


if __name__ == "__main__":
    unittest.main()
