"""Contract tests for PIE's opt-in, transparent Blender MCP proxy."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pie.integrations.blender_mcp_bridge import (
    BlenderMcpBridge, SnapshotStore, compact_observation, extend_tools,
)


def response(text, *, is_error=False):
    return {
        "jsonrpc": "2.0", "id": 7,
        "result": {
            "content": [{"type": "text", "text": text}],
            **({"isError": True} if is_error else {}),
        },
    }


class BlenderProxyUnitTests(unittest.TestCase):
    def setUp(self):
        self.store = SnapshotStore()

    def test_unchanged_small_observation_is_byte_equivalent(self):
        original = response("Small scene")
        self.assertEqual(compact_observation(original, "get_scene_info", self.store, 800), original)

    def test_large_read_compacted_reversible_with_exact_bytes(self):
        original = "Scene\n" + "Object Cube material RoughMetal\n" * 100
        compacted = compact_observation(response(original), "get_scene_info", self.store, 800)
        summary = json.loads(compacted["result"]["content"][0]["text"])
        self.assertEqual(summary["status"], "PARTIAL")
        self.assertLessEqual(len(compacted["result"]["content"][0]["text"]), 800)
        self.assertEqual(summary["source_chars"], len(original))
        self.assertGreater(summary["omitted_chars"], 0)
        identifier = summary["response_id"]
        result = []
        start = 0
        while start < len(original):
            expanded = self.store.expand({
                "response_id": identifier, "start": start, "max_chars": 500,
            })
            content = json.loads(expanded["content"][0]["text"])
            self.assertEqual(content["status"], "EXACT_CHUNK")
            result.append(content["text"])
            start = content["end"]
        self.assertEqual("".join(result), original)

    def test_repeated_observation_is_hash_reference(self):
        text = "Scene\n" + "Cube 1.000\n" * 300
        first = compact_observation(response(text), "get_scene_info", self.store, 800)
        second = compact_observation(response(text), "get_scene_info", self.store, 800)
        ref1 = json.loads(first["result"]["content"][0]["text"])
        ref2 = json.loads(second["result"]["content"][0]["text"])
        self.assertEqual(ref1["response_id"], ref2["response_id"])
        self.assertEqual(ref2["status"], "UNCHANGED")
        self.assertNotIn("preview", ref2)

    def test_mutation_tool_and_non_text_content_never_compressed(self):
        big = "MATERIAL_CREATED" * 500
        for tool in ("execute_blender_code", "import_asset", "generate_3d", "search_assets"):
            raw = response(big)
            self.assertEqual(compact_observation(raw, tool, self.store, 800)["result"]["content"][0]["text"], big)
        image = {"jsonrpc":"2.0","id":7,"result":{"content":[{"type":"image","data":"x"*4000,"mimeType":"image/png"}]}}
        self.assertEqual(compact_observation(image, "get_scene_info", self.store, 800), image)
        mixed = {"jsonrpc":"2.0","id":7,"result":{"content":[{"type":"text","text":big},{"type":"image","data":"x"*4000,"mimeType":"image/png"}]}}
        self.assertEqual(compact_observation(mixed, "get_scene_info", self.store, 800), mixed)

    def test_errors_and_structured_content_passthrough(self):
        for raw in (response("Error: permission denied" * 150), response("Oops"*1000, is_error=True)):
            before = json.dumps(raw)
            compact_observation(raw, "get_scene_info", self.store, 800)
            self.assertEqual(json.dumps(raw), before)
        structured = response("x"*4000)
        structured["result"]["structuredContent"] = {"objects": [1,2,3]}
        self.assertEqual(compact_observation(structured, "get_scene_info", self.store, 800)["result"]["content"][0]["text"], "x"*4000)

    def test_expand_validation_and_expiry(self):
        self.assertTrue(self.store.expand({"response_id": "../bad"})["isError"])
        self.assertTrue(self.store.expand({"response_id": "a" * 64})["isError"])
        identifier, _ = self.store.remember("hello")
        self.assertTrue(self.store.expand({"response_id": identifier, "start": True})["isError"])
        self.assertTrue(self.store.expand({"response_id": identifier, "max_chars": 2})["isError"])
        bounded = SnapshotStore(capacity=1)
        old, _ = bounded.remember("old")
        bounded.remember("new")
        self.assertTrue(bounded.expand({"response_id": old})["isError"])

    def test_discovery_preserves_upstream_tools(self):
        raw = {"jsonrpc":"2.0","id":2,"result":{"tools":[
            {"name":"execute_blender_code","inputSchema":{"type":"object"}},
            {"name":"get_scene_info","inputSchema":{"type":"object"}},
        ],"nextCursor":"next"}}
        tools = extend_tools(raw)["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], ["execute_blender_code", "get_scene_info", "pie_blender_expand", "pie_blender_scene_delta"])
        extend_tools(raw)
        self.assertEqual(len(raw["result"]["tools"]), 4)

    def test_invalid_budget(self):
        with self.assertRaises(ValueError):
            BlenderMcpBridge(["python"], 200)

    def test_synthetic_payload_benchmark_records_exact_restore(self):
        from tools.benchmark_blender_payload import measure
        report = measure(objects=200, max_chars=1200)
        self.assertGreater(report["response_character_reduction_percent"], 80)
        self.assertTrue(report["full_response_recovered_exactly"])
        self.assertIsNone(report["measured_model_tokens"])


class BlenderProxyProcessTests(unittest.TestCase):
    def test_real_stdio_roundtrip_with_mock_upstream(self):
        mock = r'''
import json,sys
for line in sys.stdin:
    q=json.loads(line)
    m=q.get("method")
    if "id" not in q:
        continue
    if m=="initialize":
        result={"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"mock-blender","version":"1"}}
    elif m=="tools/list":
        result={"tools":[{"name":"get_scene_info","inputSchema":{"type":"object"}},{"name":"execute_blender_code","inputSchema":{"type":"object"}}]}
    elif m=="tools/call":
        name=q["params"]["name"]
        result={"content":[{"type":"text","text":("Scene\n"+"Cube Material\n"*300) if name=="get_scene_info" else "MATERIAL_CREATED" * 150}]}
    else:
        result={}
    sys.stdout.write(json.dumps({"jsonrpc":"2.0","id":q["id"],"result":result})+"\n")
    sys.stdout.flush()
'''
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "get_scene_info", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "execute_blender_code", "arguments": {"code": "print(1)"}}},
        ]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        process = subprocess.run(
            [sys.executable, "-m", "pie.integrations.blender_mcp_bridge",
             "--max-chars", "1000", "--", sys.executable, "-c", mock],
            input="\n".join(json.dumps(q) for q in requests) + "\n",
            text=True, capture_output=True, env=env, timeout=20, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = {r["id"]:r for r in (json.loads(line) for line in process.stdout.splitlines())}
        self.assertEqual(responses[1]["result"]["serverInfo"]["name"], "mock-blender")
        names = [x["name"] for x in responses[2]["result"]["tools"]]
        self.assertEqual(names, ["get_scene_info","execute_blender_code","pie_blender_expand","pie_blender_scene_delta"])
        compact = json.loads(responses[3]["result"]["content"][0]["text"])
        self.assertEqual(compact["status"], "PARTIAL")
        self.assertEqual(responses[4]["result"]["content"][0]["text"], "MATERIAL_CREATED"*150)


if __name__ == "__main__":
    unittest.main()
