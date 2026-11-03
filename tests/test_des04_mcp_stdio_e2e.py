"""Black-box MCP stdio integration, without a model or Codex credentials.

Starts the actual installed PIE MCP process with a temporary indexed
workspace and validates JSON-RPC initialization, tool discovery, tool calls,
and stale-source refusal over real stdin/stdout pipes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from pie.indexing.indexer import index_project
from pie.interfaces.cli import command_init


class MCPStdioE2ETests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "logic.py").write_text(
            "def compute(value):\n    return value * 2\n", encoding="utf-8"
        )
        (self.root / "consumer.py").write_text(
            "from logic import compute\n"
            "def run():\n"
            "    return compute(21)\n", encoding="utf-8"
        )
        command_init(self.root)
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")

    def tearDown(self):
        self.temp.cleanup()

    def _invoke(self, messages):
        lines = "\n".join(json.dumps(message) for message in messages) + "\n"
        child_env = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[1] / "src")
        child_env["PYTHONPATH"] = os.pathsep.join(filter(None, (
            source_root, child_env.get("PYTHONPATH", ""),
        )))
        proc = subprocess.run(
            [sys.executable, "-u", "-m", "pie.interfaces.mcp_server",
             "--root", str(self.root)],
            input=lines, text=True, encoding="utf-8",
            capture_output=True, timeout=30, check=False,
            env=child_env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        output = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(output), sum("id" in m for m in messages),
                         f"Unexpected MCP stdout: {proc.stdout!r}; stderr: {proc.stderr!r}")
        self.assertTrue(all(row.get("jsonrpc") == "2.0" for row in output))
        return {row["id"]: row for row in output}

    @staticmethod
    def _call(id, name, arguments):
        return {"jsonrpc": "2.0", "id": id, "method": "tools/call",
                "params": {"name": name, "arguments": arguments}}

    def test_stdio_handshake_discovery_and_context_pack(self):
        replies = self._invoke([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                        "clientInfo": {"name": "des04-stdio-smoke", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            self._call(3, "pie_build_context_pack",
                       {"symbol": "compute", "max_chars": 4000}),
            {"jsonrpc": "2.0", "id": 4, "method": "ping", "params": {}},
        ])
        self.assertEqual(replies[1]["result"]["protocolVersion"], "2025-03-26")
        names = {item["name"] for item in replies[2]["result"]["tools"]}
        self.assertIn("pie_build_context_pack", names)
        reply = replies[3]["result"]
        self.assertFalse(reply.get("isError", False))
        pack = json.loads(reply["content"][0]["text"])
        self.assertEqual(pack["definition"]["path"], "logic.py")
        self.assertEqual(pack["callers"][0]["path"], "consumer.py")
        self.assertEqual(pack["callers"][0]["line"], 3)
        self.assertEqual(pack["coverage"]["verified_direct_call_count"], 1)
        self.assertEqual(pack["impact"]["status"], "UNDETERMINED")
        self.assertEqual(replies[4]["result"], {})

    def test_stdio_abstains_on_stale_index(self):
        (self.root / "unindexed.py").write_text(
            "from logic import compute\ncompute(5)\n", encoding="utf-8"
        )
        replies = self._invoke([
            self._call(9, "pie_build_context_pack", {"symbol": "compute"})
        ])
        payload = replies[9]["result"]
        self.assertTrue(payload["isError"])
        self.assertIn("STALE_PROJECT", payload["content"][0]["text"])

    def test_stdio_local_import_and_qualified_method_contracts(self):
        (self.root / 'consumer.py').write_text(
            'class Runner:\n    def run(self):\n        from logic import compute\n'
            '        return [compute(x) for x in range(3)]\n', encoding='utf-8')
        (self.root / 'cache.py').write_text(
            'class MeasurementCache:\n    def get(self, key):\n        return key\n', encoding='utf-8')
        self.assertEqual(index_project(self.root)['index_state'], 'CURRENT')
        replies = self._invoke([
            self._call(1, 'pie_build_context_pack', {'symbol': 'compute'}),
            self._call(2, 'pie_build_context_pack', {'symbol': 'MeasurementCache.get'}),
            self._call(3, 'pie_verified_evidence', {'symbol': 'MeasurementCache.get'}),
            self._call(4, 'pie_build_context_pack', {'symbol': 'MeasurementCache.get()'}),
        ])
        for number in (1, 2, 3):
            self.assertFalse(replies[number]['result'].get('isError', False))
        compute = json.loads(replies[1]['result']['content'][0]['text'])
        self.assertEqual([(c['path'], c['line']) for c in compute['callers']], [('consumer.py', 4)])
        pack = json.loads(replies[2]['result']['content'][0]['text'])
        self.assertEqual(pack['schema_version'], 'pie-context-pack-v2')
        self.assertEqual(pack['definition']['binding'], 'cache.py::class:MeasurementCache::get')
        self.assertTrue(pack['coverage']['returned_verified_call_list_complete'])
        self.assertFalse(pack['coverage']['exhaustive'])
        self.assertEqual(pack['coverage']['static_analysis_coverage'], 'PARTIAL')
        self.assertTrue(replies[4]['result']['isError'])

    def test_stdio_rejects_workspace_override(self):
        replies = self._invoke([
            self._call(7, "pie_build_context_pack",
                       {"symbol": "compute", "root": "/untrusted"})
        ])
        self.assertTrue(replies[7]["result"]["isError"])
        self.assertIn("Unknown arguments", replies[7]["result"]["content"][0]["text"])

    def test_stdio_refuses_ambiguous_qualified_methods(self):
        for name in ('one.py', 'two.py'):
            (self.root / name).write_text('class Cache:\n    def get(self):\n        return 1\n',
                                          encoding='utf-8')
        self.assertEqual(index_project(self.root)['index_state'], 'CURRENT')
        replies = self._invoke([self._call(1, 'pie_build_context_pack', {'symbol': 'Cache.get'})])
        self.assertTrue(replies[1]['result']['isError'])
        self.assertIn('AMBIGUOUS', replies[1]['result']['content'][0]['text'])


if __name__ == "__main__":
    unittest.main()
