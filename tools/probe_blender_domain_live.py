"""Persistent real Blender MCP call through the PIE domain gateway."""
from __future__ import annotations

import json
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import Thread


class Client:
    def __init__(self, process):
        self.process = process
        self.queue = Queue()
        Thread(target=self._read, args=(process.stdout,), daemon=True).start()

    def _read(self, stream):
        for line in stream:
            self.queue.put(line)
        self.queue.put(None)

    def call(self, identifier, method, params=None):
        request = {"jsonrpc": "2.0", "id": identifier, "method": method}
        if params is not None:
            request["params"] = params
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        while True:
            raw = self.queue.get(timeout=30)
            if raw is None:
                raise RuntimeError("Blender gateway exited before response")
            try:
                response = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if response.get("id") == identifier:
                return response

    def notify(self, method):
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.process.stdin.flush()

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=15)


def main() -> int:
    workspace = Path(os.environ.get("PIE_PROBE_WORKSPACE", Path.cwd())).resolve()
    store = Path(os.environ.get("PIE_PROBE_STORE", workspace / ".pie-live-store")).resolve()
    command = [
        sys.executable, "-m", "pie.gateway.domain", "serve", "--domain", "blender",
        "--workspace", str(workspace), "--store", str(store), "--max-chars", "1200", "--",
        os.environ.get("PIE_BLENDER_UPSTREAM", str(Path.home() / ".local" / "bin" / "uvx.exe")),
        "mcp-for-blender",
    ]
    env = dict(os.environ, PIE_GLOBAL_STORAGE_ROOT=str(store))
    process = subprocess.Popen(command, cwd=workspace, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", bufsize=1)
    # The upstream Blender server is intentionally verbose on stderr. Drain it
    # so diagnostics cannot fill the pipe and block an otherwise healthy MCP
    # response. Do not persist the diagnostic stream: it may contain prompts.
    if process.stderr is not None:
        Thread(target=lambda: [line for line in process.stderr], daemon=True).start()
    client = Client(process)
    try:
        init = client.call(1, "initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "pie-blender-live-probe", "version": "1"},
        })
        if "error" in init:
            raise RuntimeError("MCP initialization rejected")
        client.notify("notifications/initialized")
        client.call(2, "tools/list", {})
        tool = os.environ.get("PIE_BLENDER_PROBE_TOOL", "get_scene_info")
        scene = client.call(3, "tools/call", {"name": tool, "arguments": {}})
        if scene.get("result", {}).get("isError"):
            raise RuntimeError("get_scene_info returned an MCP error")
        print(json.dumps({"schema": "pie-blender-mcp-real-v1", "state": "PASS",
                          "handshake": True, "tools_list": True,
                          "tool": tool, "tool_call": True, "provider_tokens_measured": False}))
        return 0
    except Exception as exc:
        print(json.dumps({"schema": "pie-blender-mcp-real-v1", "state": "FAIL",
                          "error": type(exc).__name__}), file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
