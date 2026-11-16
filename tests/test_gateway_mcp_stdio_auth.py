"""Black-box auth tests for the MCP stdio gateway (opt-in token auth).

Starts the real gateway process (with the plain MCP server as upstream)
and validates that, when authentication is enabled, requests without a
valid token are rejected with a JSON-RPC error on stdout, and that a
valid token completes the handshake. No network, Blender, Codex, or
real credentials are involved.
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

GATEWAY_MODULE = "pie.gateway.mcp_stdio"
UPSTREAM_MODULE = "pie.interfaces.mcp_server"
AUTH_ERROR_CODE = -32001


class MCPStdioAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "logic.py").write_text(
            "def compute(value):\n    return value * 2\n", encoding="utf-8"
        )
        # The gateway routes the upstream through a global storage root (so the
        # child process it spawns resolves the same index). Mirror that layout
        # locally: index into "<global root>/projects/<id>" and export it to
        # the gateway process via PIE_GLOBAL_STORAGE_ROOT (see _env).
        self.storage_root = self.root / "global_storage"
        self._storage_override = os.environ.get("PIE_GLOBAL_STORAGE_ROOT")
        os.environ["PIE_GLOBAL_STORAGE_ROOT"] = str(self.storage_root)
        try:
            command_init(self.root)
            index_project(self.root)
        finally:
            if self._storage_override is None:
                os.environ.pop("PIE_GLOBAL_STORAGE_ROOT", None)
            else:
                os.environ["PIE_GLOBAL_STORAGE_ROOT"] = self._storage_override
        self.token = "test-token-abc123"
        self.token_file = self.root / "auth_token.txt"
        self.token_file.write_text(self.token + "\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _env(self, extra: dict | None = None) -> dict:
        child_env = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[1] / "src")
        child_env["PYTHONPATH"] = os.pathsep.join(filter(None, (
            source_root, child_env.get("PYTHONPATH", ""),
        )))
        child_env.pop("PIE_MCP_AUTH_TOKEN", None)
        child_env["PIE_GLOBAL_STORAGE_ROOT"] = str(self.storage_root)
        if extra:
            child_env.update(extra)
        return child_env

    def _run_gateway(self, messages, env_extra: dict | None = None):
        lines = "\n".join(json.dumps(message) for message in messages) + "\n"
        proc = subprocess.run(
            [sys.executable, "-u", "-m", GATEWAY_MODULE,
             "--workspace", str(self.root),
             "--auth-token-file", str(self.token_file),
             "--", sys.executable, "-u", "-m", UPSTREAM_MODULE,
             "--root", str(self.root)],
            input=lines, text=True, encoding="utf-8",
            capture_output=True, timeout=60, check=False,
            env=self._env(env_extra),
        )
        return proc

    @staticmethod
    def _initialize(id, token: str | None = None, in_meta: bool = True):
        params: dict = {"protocolVersion": "2025-03-26", "capabilities": {},
                        "clientInfo": {"name": "auth-test", "version": "1"}}
        if token is not None:
            if in_meta:
                params["_meta"] = {"pie_auth_token": token}
            else:
                params["pie_auth_token"] = token
        return {"jsonrpc": "2.0", "id": id, "method": "initialize",
                "params": params}

    @staticmethod
    def _call(id, name, arguments):
        return {"jsonrpc": "2.0", "id": id, "method": "tools/call",
                "params": {"name": name, "arguments": arguments}}

    def _output(self, proc):
        rows = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    def test_valid_token_handshake_and_tools_call(self):
        proc = self._run_gateway([
            self._initialize(1, self.token, in_meta=True),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            self._call(3, "pie_build_context_pack",
                       {"symbol": "compute", "max_chars": 4000}),
        ])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = self._output(proc)
        replies = {row["id"]: row for row in rows if "id" in row}
        self.assertNotIn("error", replies[1])
        self.assertEqual(replies[1]["result"]["protocolVersion"], "2025-03-26")
        self.assertNotIn("error", replies[2])
        self.assertIn("pie_build_context_pack",
                      {t["name"] for t in replies[2]["result"]["tools"]})
        self.assertNotIn("error", replies[3])

    def test_missing_token_rejected_on_initialize_and_tools(self):
        proc = self._run_gateway([
            self._initialize(1),
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            self._call(3, "pie_build_context_pack", {"symbol": "compute"}),
        ])
        rows = self._output(proc)
        replies = {row["id"]: row for row in rows if "id" in row}
        for id_ in (1, 2, 3):
            self.assertIn("error", replies[id_], f"id {id_}: {replies[id_]}")
            self.assertEqual(replies[id_]["error"]["code"], AUTH_ERROR_CODE)
            self.assertEqual(replies[id_]["error"]["message"],
                             "PIE_GATEWAY_AUTH_REQUIRED")

    def test_invalid_token_rejected_on_initialize(self):
        proc = self._run_gateway([
            self._initialize(1, "wrong-token"),
        ])
        rows = self._output(proc)
        replies = {row["id"]: row for row in rows if "id" in row}
        self.assertIn("error", replies[1])
        self.assertEqual(replies[1]["error"]["code"], AUTH_ERROR_CODE)
        self.assertEqual(replies[1]["error"]["message"],
                         "PIE_GATEWAY_AUTH_REQUIRED")

    def test_token_sent_top_level_is_accepted_and_not_forwarded(self):
        proc = self._run_gateway([
            self._initialize(1, self.token, in_meta=False),
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = self._output(proc)
        replies = {row["id"]: row for row in rows if "id" in row}
        self.assertNotIn("error", replies[1])
        self.assertNotIn("error", replies[2])

    def test_auth_disabled_by_default_allows_unauthenticated_handshake(self):
        lines = "\n".join(json.dumps(message) for message in [
            self._initialize(1),
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]) + "\n"
        proc = subprocess.run(
            [sys.executable, "-u", "-m", GATEWAY_MODULE,
             "--workspace", str(self.root),
             "--", sys.executable, "-u", "-m", UPSTREAM_MODULE,
             "--root", str(self.root)],
            input=lines, text=True, encoding="utf-8",
            capture_output=True, timeout=60, check=False,
            env=self._env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = self._output(proc)
        replies = {row["id"]: row for row in rows if "id" in row}
        self.assertNotIn("error", replies[1])
        self.assertNotIn("error", replies[2])

    def test_env_var_token_source(self):
        lines = "\n".join(json.dumps(message) for message in [
            self._initialize(1, self.token),
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]) + "\n"
        proc = subprocess.run(
            [sys.executable, "-u", "-m", GATEWAY_MODULE,
             "--workspace", str(self.root),
             "--", sys.executable, "-u", "-m", UPSTREAM_MODULE,
             "--root", str(self.root)],
            input=lines, text=True, encoding="utf-8",
            capture_output=True, timeout=60, check=False,
            env=self._env({"PIE_MCP_AUTH_TOKEN": self.token}),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = self._output(proc)
        replies = {row["id"]: row for row in rows if "id" in row}
        self.assertNotIn("error", replies[1])
        self.assertNotIn("error", replies[2])

    def test_token_never_appears_in_stdout_or_stderr(self):
        proc = self._run_gateway([
            self._initialize(1, self.token),
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ])
        self.assertNotIn(self.token, proc.stdout)
        self.assertNotIn(self.token, proc.stderr)


if __name__ == "__main__":
    unittest.main()
