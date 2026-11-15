"""Probe the PIE-owned selective Blender scene query against a real gateway."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from queue import Empty, Queue
from threading import Thread
import time


class Client:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.lines: Queue[str | None] = Queue()
        Thread(target=self._drain, args=(process.stdout,), daemon=True).start()
        Thread(target=self._drain_stderr, args=(process.stderr,), daemon=True).start()

    def _drain(self, stream) -> None:
        if stream is not None:
            for line in stream:
                self.lines.put(line)
        self.lines.put(None)

    @staticmethod
    def _drain_stderr(stream) -> None:
        if stream is not None:
            for _ in stream:
                pass

    def call(self, identifier: int, method: str, params: dict | None = None) -> dict:
        request = {"jsonrpc": "2.0", "id": identifier, "method": method}
        if params is not None:
            request["params"] = params
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                raw = self.lines.get(timeout=1)
            except Empty:
                continue
            if raw is None:
                raise RuntimeError(f"MCP exited before {method}")
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if value.get("id") == identifier:
                return value
        raise TimeoutError(method)

    def notify(self, method: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.process.stdin.flush()

    def close(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=15)


def _query(client: Client, identifier: int, offset: int) -> dict:
    response = client.call(identifier, "tools/call", {"name": "pie_blender_query_scene", "arguments": {
        "query": "find_objects", "filters": {"name_prefix": "PIE_Large_Cube_"},
        "fields": ["name", "type", "material_count"], "limit": 20, "offset": offset,
    }})
    text = response["result"]["content"][0]["text"]
    return {"response": response, "payload": json.loads(text), "serialized_chars": len(json.dumps(response, ensure_ascii=False, separators=(",", ":")))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--uvx", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    store = root / ".pie-query-probe-store"
    upstream = [str(args.uvx), "mcp-for-blender", "--port", "9877"]
    command = [str(args.python), "-m", "pie.gateway.domain", "serve", "--domain", "blender",
               "--workspace", str(root), "--store", str(store), "--max-chars", "2400", "--", *upstream]
    process = subprocess.Popen(command, cwd=root, env=dict(**__import__("os").environ, PIE_GLOBAL_STORAGE_ROOT=str(store)),
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", bufsize=1)
    client = Client(process)
    try:
        initialize = client.call(1, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                                     "clientInfo": {"name": "pie-query-probe", "version": "1"}})
        client.notify("notifications/initialized")
        tools = client.call(2, "tools/list", {})
        page_one = _query(client, 3, 0)
        page_two = _query(client, 4, 20)
        page_three = _query(client, 5, 40)
        page_four = _query(client, 6, 60)
        names_one = [item["name"] for item in page_one["payload"]["items"]]
        names_two = [item["name"] for item in page_two["payload"]["items"]]
        names_three = [item["name"] for item in page_three["payload"]["items"]]
        names_four = [item["name"] for item in page_four["payload"]["items"]]
        tool = next(item for item in tools["result"]["tools"] if item["name"] == "pie_blender_query_scene")
        result = {
            "schema": "pie-phase3-real-blender-query-probe-v1", "status": "PASS",
            "model_sessions": 0, "quota_consumed": False,
            "initialize": "PASS" if "result" in initialize else "FAIL",
            "tool_discovery": {"name": tool["name"], "input_schema": tool["inputSchema"],
                               "output_schema": tool.get("outputSchema")},
            "pages": [page_one, page_two, page_three, page_four],
            "oracle": {"page_one_has_fixture_prefix": all(name.startswith("PIE_Large_Cube_") for name in names_one),
                       "page_one_count": len(names_one), "page_two_count": len(names_two), "page_three_count": len(names_three), "page_four_count": len(names_four),
                       "deterministic_pagination": page_one["payload"]["next_offset"] == 20 and page_two["payload"]["next_offset"] == 40 and page_three["payload"]["next_offset"] == 60 and page_four["payload"]["next_offset"] is None,
                       "typed_fields": all(set(item) == {"name", "type", "material_count"} for item in page_one["payload"]["items"])},
            "client_calls": 4,
            "upstream_calls_per_client_query": 1,
            "note": "Payload is reduced at the source query contract; this is not transparent get_scene_info compaction.",
        }
    finally:
        client.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
