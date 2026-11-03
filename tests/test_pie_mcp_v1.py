"""MCP v1 contract and persistent warm retrieval tests."""
import io
import json
import os
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

    def test_query_phases_and_total_character_budget(self):
        with MCPContextEngine(self.root) as engine:
            for mode in ("navigation", "responsibility", "impact"):
                result = engine.query("Model", mode=mode, max_chars=1000, limit=5)
                encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
                self.assertLessEqual(len(encoded), 1000)
                metrics = result["metrics"]
                for key in ("cache_hit", "reindexed", "refresh_ms", "search_ms",
                            "graph_ms", "serialization_ms", "total_ms"):
                    self.assertIn(key, metrics)
                self.assertGreaterEqual(metrics["total_ms"], 0)

    def test_unchanged_query_never_calls_indexer(self):
        with MCPContextEngine(self.root) as engine:
            with patch("pie.retrieval.warm.index_project",
                       side_effect=AssertionError("Unexpected full reindex")):
                first = engine.query("Model", mode="navigation")
                second = engine.query("Model", mode="navigation")
                self.assertFalse(first["metrics"]["reindexed"])
                self.assertFalse(second["metrics"]["reindexed"])
                self.assertTrue(second["metrics"]["cache_hit"])

    def test_source_change_reindexes_once_and_invalidates_cache(self):
        with MCPContextEngine(self.root) as engine:
            engine.query("Model", mode="navigation")
            (self.root / "models.py").write_text(
                'class RenamedModel:\n    """New model behavior."""\n    pass\n',
                encoding="utf8")
            import pie.retrieval.warm as warm
            original_index = warm.index_project
            with patch("pie.retrieval.warm.index_project", wraps=original_index) as indexer:
                changed = engine.query("RenamedModel", mode="navigation")
                unchanged = engine.query("RenamedModel", mode="navigation")
                self.assertEqual(indexer.call_count, 1)
                self.assertTrue(changed["metrics"]["reindexed"])
                self.assertFalse(unchanged["metrics"]["reindexed"])
                self.assertTrue(unchanged["metrics"]["cache_hit"])

    def test_budget_omission_is_explicit_and_deduplicated(self):
        with MCPContextEngine(self.root) as engine:
            result = engine.query("Model", mode="responsibility", max_chars=700)
            pack = result["pack"]
            identities = [(item["path"], item["symbol"], item["start_line"])
                          for item in pack["responsibilities"]]
            self.assertEqual(len(identities), len(set(identities)))
            self.assertIn("omitted", pack)
            self.assertLessEqual(len(json.dumps(result, ensure_ascii=False,
                                               separators=(",", ":"))), 700)

    def test_ambiguous_and_missing_symbols(self):
        (self.root / "other.py").write_text(
            'class Model:\n    """Alternate domain model."""\n    pass\n',
            encoding="utf8")
        index_project(self.root)
        with MCPContextEngine(self.root) as engine:
            ambiguous = engine.query("Model", mode="navigation")
            self.assertEqual(ambiguous["lookup_status"], "AMBIGUOUS")
            self.assertEqual(ambiguous["exact_match_count"], 2)
            self.assertEqual(engine.query("model", mode="navigation")["lookup_status"],
                             "AMBIGUOUS")
            missing = engine.query("UnfindableUniqueClass999", mode="navigation")
            self.assertEqual(missing["lookup_status"], "NOT_FOUND")
            self.assertEqual(missing["relation_classes"]["inferred"], 0)

    def test_mcp_bad_payloads_fail_closed(self):
        with MCPContextEngine(self.root) as engine:
            bad = [
                [],
                {"jsonrpc": "1.0", "id": 1, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": []},
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "pie_query", "arguments": {"query": "Model", "root": ".."}}},
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "pie_query", "arguments": {"query": "Model", "limit": True}}},
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "pie_query", "arguments": {"query": "X" * 4097}}},
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "pie_query", "arguments": {"query": "Model" + chr(0)}}},
            ]
            for request in bad:
                result = dispatch(request, self.root, engine)
                self.assertTrue("error" in result or
                                result.get("result", {}).get("isError"), request)

    def test_source_symlink_outside_root_not_disclosed(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "external.py"
            external.write_text(
                'class Model:\n    """Secret outside root."""\n    pass\n', encoding="utf8")
            original = self.root / "models.py"
            original.unlink()
            try:
                original.symlink_to(external)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unavailable on this runner")
            with MCPContextEngine(self.root) as engine:
                with self.assertRaises(ValueError):
                    engine.query("Model", mode="navigation")

    def test_changed_source_same_size_rejected_from_cache(self):
        with MCPContextEngine(self.root) as engine:
            engine.query("Model", mode="navigation")
            source = self.root / "models.py"
            content = source.read_text(encoding="utf8")
            new = content.replace("Store validated model state.", "Store validated model STATE.")
            self.assertEqual(len(content), len(new))
            source.write_text(new, encoding="utf8")
            result = engine.query("Model", mode="navigation")
            self.assertFalse(result["metrics"]["cache_hit"])
            self.assertTrue(result["metrics"]["reindexed"])

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
            input="\n".join(json.dumps(r) for r in requests) + "\n",
            text=True, capture_output=True, timeout=45,
            env={**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [
                str(Path(__file__).resolve().parents[1] / "src"), os.environ.get("PYTHONPATH")
            ]))},
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
