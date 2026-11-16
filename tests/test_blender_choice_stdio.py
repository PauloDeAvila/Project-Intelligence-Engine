"""Full JSON-RPC stdio tests: actual Blender PIE proxy with a fake upstream.

No Blender app, Ollama model, internet or Codex needed. This confirms routing,
source parsing and proxy forwarding through subprocess pipes, not GPU behavior.
"""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

from benchmark_blender_choice_agent import TASKS, run_arm


FAKE_BLENDER_UPSTREAM = r"""
import json, re, sys
for line in sys.stdin:
    try:
        message = json.loads(line)
    except json.JSONDecodeError:
        continue
    method = message.get("method")
    if "id" not in message:
        continue
    if method == "initialize":
        result = {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "controlled-fixture", "version": "1"},
        }
    elif method == "tools/list":
        result = {"tools": [
            {"name": "get_scene_info", "description": "Broad scene summary",
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "execute_blender_code", "description": "Execute Blender Python code",
             "inputSchema": {"type": "object",
                             "properties": {"code": {"type": "string"}},
                             "required": ["code"]}},
        ]}
    elif method == "tools/call":
        params = message.get("params") or {}
        if params.get("name") != "execute_blender_code":
            result = {"isError": True, "content": [
                {"type": "text", "text": "Unsupported mock tool"}]}
        else:
            code = params.get("arguments", {}).get("code", "")
            exact = "PIE_GET_OBJECT_V1=" in code
            pattern = (r'pie_object_name = "(PIE_Large_Cube_[0-9]{2})"'
                       if exact else
                       r'objects\.get\("(PIE_Large_Cube_[0-9]{2})"\)')
            match = re.search(pattern, code)
            if not match:
                result = {"isError": True, "content": [
                    {"type": "text", "text": "Unexpected code pattern"}]}
            else:
                target = match.group(1)
                index = int(target[-2:])
                if not 0 <= index <= 63:
                    result = {"isError": True, "content": [
                        {"type": "text", "text": "Object outside fixture"}]}
                else:
                    data = {
                        "object_name": target, "object_type": "MESH",
                        "location": [index % 8, index // 8, 0],
                        "material_names": [f"PIE_Large_Material_{index // 4:02d}"],
                    }
                    marker = ("PIE_GET_OBJECT_V1=" if exact
                              else "PIE_LOCAL_OBJECT_V1=")
                    result = {"content": [{"type": "text",
                        "text": "Code executed successfully: " + marker +
                                json.dumps(data, separators=(",", ":"))}]}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"],
                      "result": result}), flush=True)
"""


class MultiChoiceStdioTests(unittest.TestCase):
    def test_three_tasks_both_arms_around_real_pie_proxy(self):
        py = sys.executable
        env = {"PYTHONPATH": str(ROOT / "src")}
        for condition, names, server in (
            ("baseline", ["get_scene_info", "execute_blender_code"], "blender"),
            ("optimized", ["pie_blender_query_scene", "pie_blender_get_object"],
             "pie-blender-optimized"),
        ):
            args = ["-u", "-c", FAKE_BLENDER_UPSTREAM]
            if condition == "optimized":
                args = [
                    "-u", "-m", "pie.integrations.blender_mcp_bridge",
                    "--expose-tool", "pie_blender_query_scene",
                    "--expose-tool", "pie_blender_get_object",
                    "--", py, "-u", "-c", FAKE_BLENDER_UPSTREAM,
                ]
            for task in TASKS:
                with (
                    self.subTest(condition=condition, task_id=task["task_id"]),
                    patch("benchmark_blender_choice_agent._profile", return_value=(
                        {"command": py, "enabled_tools": names},
                        server, args, env)),
                    patch("benchmark_blender_choice_agent.plan_choice") as model,
                ):
                    result = run_arm(
                        Path("mock-profile.toml"), ROOT, condition, task, "unused",
                        route_mode="deterministic")
                    model.assert_not_called()
                    self.assertTrue(result["oracle_pass"])
                    self.assertEqual(result["routing_strategy"],
                                     "DETERMINISTIC_EXACT_MATCH_NO_MODEL")
                    self.assertEqual(result["mcp_calls"], 1)
                    self.assertEqual(result["provider_requests"], 0)
                    self.assertIsNone(result["usage"])
                    self.assertEqual(
                        result["selected_tool"],
                        "execute_blender_code" if condition == "baseline"
                        else "pie_blender_get_object")


if __name__ == "__main__":
    unittest.main()
