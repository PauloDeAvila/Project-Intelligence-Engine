"""MCP v1 contract and persistent warm retrieval tests."""
import io
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pie.indexing.indexer import index_project
from pie.interfaces.mcp_server import TOOLS, dispatch, main
from pie.interfaces.mcp_context import MCPContextEngine


class MCPQueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "models.py").write_text(
            'class Model:\n    """Store validated model state."""\n    def validate(self):\n        """Validate model state."""\n        return True\n', encoding="utf8")
        index_project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, name, args, engine):
        return dispatch({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                         "params": {"name": name, "arguments": args}}, self.root, engine)

    def test_tool_discovery_and_modes(self):
        names = {tool["name"] for tool in TOOLS}
        self.assertIn("pie_query", names)
        with MCPContextEngine(self.root) as engine:
            for mode in ("navigation", "responsibility", "impact"):
                response = self.request("pie_query", {"query": "Model", "mode": mode}, engine)
                self.assertNotIn("error", response)
                self.assertFalse(response["result"].get("isError", False), response)
                payload = json.loads(response["result"]["content"][0]["text"])
                self.assertEqual(payload["mode"], mode)
                self.assertEqual(payload["query"], "Model")

    def test_invalid_arguments_are_rejected(self):
        with MCPContextEngine(self.root) as engine:
            for args in ({"query": "Model", "limit": 21},
                         {"query": "Model", "mode": "nonsense"},
                         {"query": "Model", "max_chars": 1},
                         {"query": ""}):
                response = self.request("pie_query", args, engine)
                self.assertTrue(response["result"]["isError"], args)

    def test_navigation_cache_persists_across_calls(self):
        with MCPContextEngine(self.root) as engine:
            a = json.loads(self.request("pie_query", {"query": "Model", "mode": "navigation"}, engine)["result"]["content"][0]["text"])
            b = json.loads(self.request("pie_query", {"query": "Model", "mode": "navigation"}, engine)["result"]["content"][0]["text"])
            self.assertFalse(a["cache_hit"])
            self.assertTrue(b["cache_hit"])

    def test_real_process_stdio_client(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {
                    "name": "pie-smoke-client", "version": "1.0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "pie_query", "arguments": {"query": "Model", "mode": "navigation"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
                "name": "pie_query", "arguments": {"query": "Model", "mode": "navigation"}}},
        ]
        result = subprocess.run(
            [sys.executable, "-m", "pie.interfaces.mcp_server", "--root", str(self.root)],
            input="\\n".join(json.dumps(r) for r in requests) + "\\n",
            text=True, capture_output=True, timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([r["id"] for r in responses], [1, 2, 3, 4])
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-03-26")
        self.assertIn("pie_query", {t["name"] for t in responses[1]["result"]["tools"]})
        first = json.loads(responses[2]["result"]["content"][0]["text"])
        second = json.loads(responses[3]["result"]["content"][0]["text"])
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])

    def test_mcp_stdio_integration(self):
        requests = "\n".join(json.dumps(item) for item in [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "pie_query", "arguments": {"query": "Model", "mode": "impact"}}}
        ]) + "\n"
        source, target = io.StringIO(requests), io.StringIO()
        with patch("sys.stdin", source), patch("sys.stdout", target):
            self.assertEqual(main(["--root", str(self.root)]), 0)
        replies = [json.loads(line) for line in target.getvalue().splitlines()]
        self.assertEqual([x["id"] for x in replies], [1, 2, 3])
        self.assertIn("pie_query", {x["name"] for x in replies[1]["result"]["tools"]})
        self.assertFalse(replies[2]["result"].get("isError", False))


if __name__ == "__main__":
    unittest.main()
