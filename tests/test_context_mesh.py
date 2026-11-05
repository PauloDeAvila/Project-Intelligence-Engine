import tempfile
import unittest
import json
import os
import subprocess
import sys
from pathlib import Path

from pie.graph.relationships import build_relationships
from pie.indexing.indexer import index_project
from pie.interfaces.mcp_server import dispatch
from pie.retrieval.context_mesh import ContextMesh


class ContextMeshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "app.py").write_text(
            "def greet(name):\n"
            "    if not name:\n"
            "        raise ValueError('name required')\n"
            "    return name.strip()\n",
            encoding="utf-8",
        )
        index_project(self.root)
        build_relationships(self.root)

    def test_coordinator_gets_isolated_packs_with_shared_deduplicated_facts(self):
        mesh = ContextMesh(self.root)
        result = mesh.build([
            {"id": "planner", "objective": "understand validation", "query": "greet", "requirements": ["raise"]},
            {"id": "implementer", "objective": "understand return path", "query": "greet", "requirements": ["return"]},
        ])
        self.assertEqual(result["schema"], "pie-context-mesh-v1")
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["deduplication"]["agent_count"], 2)
        self.assertEqual(result["deduplication"]["unique_source_count"], 1)
        self.assertEqual(len(result["assignments"]), 2)
        self.assertTrue(all(item["can_deliver"] for item in result["assignments"]))
        self.assertTrue(result["graph"]["edges"])

    def test_search_and_visualization_use_the_built_graph(self):
        mesh = ContextMesh(self.root)
        mesh.build([
            {"id": "reader", "objective": "find return behavior", "query": "greet", "requirements": ["return"]},
        ])
        found = mesh.search("return")
        self.assertGreaterEqual(found["count"], 1)
        graph = mesh.visualization()
        self.assertTrue(graph["nodes"])
        self.assertTrue(graph["edges"])

    def test_incomplete_proof_is_not_delivered_to_agent(self):
        mesh = ContextMesh(self.root)
        result = mesh.build([
            {"id": "unsafe", "objective": "need missing fact", "query": "greet", "requirements": ["not_present"]},
        ])
        self.assertEqual(result["status"], "PARTIAL")
        self.assertFalse(result["assignments"][0]["can_deliver"])
        self.assertEqual(result["assignments"][0]["status"], "FALLBACK_REQUIRED")

    def test_partial_index_is_blocked_from_agent_delivery(self):
        (self.root / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
        index_project(self.root)
        result = ContextMesh(self.root).build([
            {"id": "reader", "objective": "read current code", "query": "greet", "requirements": ["return"]},
        ])
        self.assertEqual(result["status"], "PARTIAL")
        self.assertFalse(result["assignments"][0]["can_deliver"])
        self.assertEqual(result["assignments"][0]["status"], "BLOCKED")

    def test_mcp_exposes_context_mesh_for_coordinators(self):
        listed = dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, self.root)
        names = {item["name"] for item in listed["result"]["tools"]}
        self.assertIn("pie_build_context_mesh", names)
        response = dispatch({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "pie_build_context_mesh",
                "arguments": {"agents": [{
                    "id": "planner",
                    "objective": "understand greet",
                    "query": "greet",
                    "requirements": ["return"],
                }]},
            },
        }, self.root)
        self.assertFalse(response["result"].get("isError", False))
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["schema"], "pie-context-mesh-v1")
        self.assertEqual(payload["status"], "READY")

    def test_mcp_stdio_serves_context_mesh_tool(self):
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "pie_build_context_mesh",
                "arguments": {"agents": [{
                    "id": "reader",
                    "objective": "understand greet",
                    "query": "greet",
                    "requirements": ["return"],
                }]},
            }},
        ]
        process = subprocess.run(
            [sys.executable, "-m", "pie.interfaces.mcp_server", "--root", str(self.root)],
            input="\n".join(json.dumps(message) for message in messages) + "\n",
            text=True,
            capture_output=True,
            check=True,
            timeout=30,
            env=dict(
                os.environ,
                PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src")
                + os.pathsep
                + os.environ.get("PYTHONPATH", ""),
            ),
        )
        responses = {
            item.get("id"): item
            for item in map(json.loads, process.stdout.splitlines())
            if "id" in item
        }
        self.assertFalse(responses[2]["result"].get("isError", False))
        payload = json.loads(responses[2]["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "READY")


if __name__ == "__main__":
    unittest.main()
