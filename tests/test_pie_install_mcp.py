"""Install, project isolation, config idempotency and MCP startup tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

from pie.interfaces.setup import provision, _identifier


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.one = self.root / "workspace-one"
        self.two = self.root / "workspace-two"
        self.one.mkdir()
        self.two.mkdir()
        (self.one / "model.py").write_text(
            'class Model:\n    """Workspace one."""\n    pass\n', encoding="utf8")
        (self.two / "service.py").write_text(
            'def process():\n    """Workspace two."""\n    return 42\n', encoding="utf8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_three_clients_and_idempotency(self):
        first = provision(self.one)
        self.assertEqual(first["index_state"], "CURRENT")
        self.assertTrue((self.one / ".pie" / "index.sqlite3").is_file())
        name = _identifier(self.one)
        vscode = json.loads((self.one / ".vscode" / "mcp.json").read_text())
        portable = json.loads((self.one / ".mcp.json").read_text())
        codex = tomllib.loads((self.one / ".codex" / "config.toml").read_text())
        self.assertEqual(vscode["servers"][name]["type"], "stdio")
        self.assertIn("--root", vscode["servers"][name]["args"])
        self.assertEqual(portable["mcpServers"][name]["command"], str(Path(sys.executable).resolve()))
        self.assertEqual(codex["mcp_servers"][name]["command"], str(Path(sys.executable).resolve()))
        second = provision(self.one)
        self.assertTrue(all(item["status"] == "unchanged"
                            for item in second["clients"].values()))

    def test_multi_workspace_separate_databases_and_server_names(self):
        first = provision(self.one)
        second = provision(self.two)
        self.assertNotEqual(first["server_id"], second["server_id"])
        self.assertNotEqual(first["database"], second["database"])
        self.assertTrue(Path(first["database"]).is_file())
        self.assertTrue(Path(second["database"]).is_file())

    def test_existing_unrelated_config_is_preserved(self):
        vscode = self.one / ".vscode" / "mcp.json"
        vscode.parent.mkdir()
        vscode.write_text(json.dumps({"settings": {"name": "keep"},
                                      "servers": {"other": {"command": "do-not-touch"}}}))
        codex = self.one / ".codex" / "config.toml"
        codex.parent.mkdir()
        codex.write_text('model = "meu"\n[mcp_servers.other]\ncommand = "other"\n')
        portable = self.one / ".mcp.json"
        portable.write_text(json.dumps({"mcpServers": {"existing": {"command": "other"}}}))
        provision(self.one)
        self.assertEqual(json.loads(vscode.read_text())["servers"]["other"]["command"],
                         "do-not-touch")
        self.assertEqual(tomllib.loads(codex.read_text())["model"], "meu")
        self.assertIn("existing", json.loads(portable.read_text())["mcpServers"])

    def test_conflicting_config_does_not_overwrite(self):
        name = _identifier(self.one)
        path = self.one / ".vscode" / "mcp.json"
        path.parent.mkdir()
        before = json.dumps({"servers": {name: {"command": "existing"}}})
        path.write_text(before)
        with self.assertRaises(ValueError):
            provision(self.one)
        self.assertEqual(path.read_text(), before)

    def test_choose_client_only(self):
        provision(self.one, clients=("codex",))
        self.assertTrue((self.one / ".codex" / "config.toml").is_file())
        self.assertFalse((self.one / ".vscode" / "mcp.json").exists())
        self.assertFalse((self.one / ".mcp.json").exists())

    def test_real_stdio_server_for_two_workspaces(self):
        for root, symbol in ((self.one, "Model"), (self.two, "process")):
            provision(root, clients=())
            messages = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "pie_query",
                            "arguments": {"query": symbol, "mode": "navigation"}}},
            ]
            proc = subprocess.run(
                [sys.executable, "-m", "pie.interfaces.mcp_server", "--root", str(root)],
                input="\n".join(json.dumps(m) for m in messages) + "\n",
                text=True, capture_output=True, timeout=45,
                env={**os.environ,
                     "PYTHONPATH": os.pathsep.join(filter(None, [
                         str(Path(__file__).resolve().parents[1] / "src"),
                         os.environ.get("PYTHONPATH")]))},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            replies = [json.loads(line) for line in proc.stdout.splitlines()]
            self.assertEqual([r["id"] for r in replies], [1, 2, 3])
            self.assertIn("pie_query", [t["name"] for t in replies[1]["result"]["tools"]])
            payload = json.loads(replies[2]["result"]["content"][0]["text"])
            self.assertEqual(payload["lookup_status"], "FOUND")

    def test_cli_one_command(self):
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [
            str(Path(__file__).resolve().parents[1] / "src"),
            os.environ.get("PYTHONPATH")]))}
        result = subprocess.run(
            [sys.executable, "-m", "pie.interfaces.setup",
             "--project", str(self.one), "--clients", "vscode", "claude"],
            capture_output=True, text=True, timeout=45, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(set(data["clients"]), {"vscode", "claude"})


if __name__ == "__main__":
    unittest.main()
