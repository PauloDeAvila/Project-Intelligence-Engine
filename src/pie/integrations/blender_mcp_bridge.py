"""Opt-in, stdio-transparent MCP for Blender proxy with bounded observation replies.

All upstream JSON-RPC methods and Blender tools are forwarded, including unknown
future tools. Only large, successful *text-only* scene observation responses are
compacted. Original responses remain available via the local pie_blender_expand
tool until this proxy process exits. Neither Blender nor upstream sources change.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
from hashlib import sha256
import json
import subprocess
import sys
import threading
from typing import Any

OBSERVATION_TOOLS = frozenset({"get_scene_info", "get_object_info"})
MAX_SNAPSHOTS = 32
MAX_SNAPSHOT_CHARS = 2_000_000
MIN_BUDGET = 800
MAX_BUDGET = 64000

EXPAND_TOOL: dict[str, Any] = {
    "name": "pie_blender_expand",
    "description": (
        "Recover an exact chunk of a Blender observation compacted by PIE. "
        "Call if an omitted field is relevant. This never modifies the Blender scene."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "response_id": {"type": "string"},
            "start": {"type": "integer", "minimum": 0},
            "max_chars": {"type": "integer", "minimum": 500, "maximum": 16000},
        },
        "required": ["response_id"],
        "additionalProperties": False,
    },
}


def _json(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _key(identifier: Any) -> str:
    return _json(identifier)


class SnapshotStore:
    """Bounded process-local store for responses, not durable task memory."""

    def __init__(self, capacity: int = MAX_SNAPSHOTS) -> None:
        self.capacity = capacity
        self._records: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.RLock()

    def remember(self, source: str) -> tuple[str, bool]:
        identifier = sha256(source.encode("utf-8")).hexdigest()
        with self._lock:
            seen = identifier in self._records
            self._records[identifier] = source
            self._records.move_to_end(identifier)
            while len(self._records) > self.capacity:
                self._records.popitem(last=False)
        return identifier, seen

    def expand(self, arguments: Any) -> dict[str, Any]:
        if not isinstance(arguments, dict) or set(arguments) - {"response_id", "start", "max_chars"}:
            return _error("Invalid expand arguments")
        identifier = arguments.get("response_id")
        start = arguments.get("start", 0)
        max_chars = arguments.get("max_chars", 4000)
        if not isinstance(identifier, str) or len(identifier) != 64 or any(
            c not in "0123456789abcdef" for c in identifier
        ):
            return _error("Invalid response_id")
        if type(start) is not int or start < 0:
            return _error("start must be a nonnegative integer")
        if type(max_chars) is not int or not 500 <= max_chars <= 16000:
            return _error("max_chars must be in 500..16000")
        with self._lock:
            source = self._records.get(identifier)
            if source is not None:
                self._records.move_to_end(identifier)
        if source is None:
            return _error("Response expired or unavailable; query Blender again")
        if start > len(source):
            return _error("start exceeds source length")
        end = min(len(source), start + max_chars)
        payload = {
            "schema": "pie-blender-observation-v1",
            "status": "EXACT_CHUNK",
            "response_id": identifier,
            "start": start,
            "end": end,
            "total_chars": len(source),
            "remaining_chars": len(source) - end,
            "text": source[start:end],
        }
        return {"content": [{"type": "text", "text": _json(payload)}]}


def _error(reason: str) -> dict[str, Any]:
    return {"isError": True, "content": [{"type": "text", "text": reason}]}


def extend_tools(message: dict[str, Any]) -> dict[str, Any]:
    result = message.get("result")
    if isinstance(result, dict) and isinstance(result.get("tools"), list):
        tools = result["tools"]
        if not any(isinstance(t, dict) and t.get("name") == EXPAND_TOOL["name"] for t in tools):
            result["tools"] = [*tools, EXPAND_TOOL]
    return message


def compact_observation(
    message: dict[str, Any], tool_name: str, snapshots: SnapshotStore, max_chars: int
) -> dict[str, Any]:
    """Compaction is explicitly lossy, labeled, and reversible within this process."""
    if tool_name not in OBSERVATION_TOOLS:
        return message
    result = message.get("result")
    if not isinstance(result, dict) or result.get("isError") or "structuredContent" in result:
        return message
    parts = result.get("content")
    if not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict):
        return message
    part = parts[0]
    if part.get("type") != "text" or not isinstance(part.get("text"), str):
        return message
    source = part["text"]
    if len(source) <= max_chars or len(source) > MAX_SNAPSHOT_CHARS or source.lstrip().startswith(("Error:", "Rejected", "Failed:")):
        return message
    identifier, seen = snapshots.remember(source)
    common = {
        "schema": "pie-blender-observation-v1",
        "status": "UNCHANGED" if seen else "PARTIAL",
        "source_tool": tool_name,
        "response_id": identifier,
        "source_chars": len(source),
        "restore_tool": "pie_blender_expand",
        "unit": "characters_not_tokens",
    }
    if seen:
        replacement = _json(common)
    else:
        common["omitted_chars"] = 0
        common["preview"] = ""
        # Keep metadata and preview inside max_chars without truncating raw
        # source storage. Every omitted character is recoverable via expand.
        available = max(0, max_chars - len(_json(common)) - 20)
        common["preview"] = source[:available]
        common["omitted_chars"] = len(source) - available
        replacement = _json(common)
        while len(replacement) > max_chars and available:
            available -= max(1, len(replacement) - max_chars)
            common["preview"] = source[:available]
            common["omitted_chars"] = len(source) - available
            replacement = _json(common)
        if len(replacement) > max_chars:
            # Never emit misleading content if the budget is too small.
            return message
    result["content"] = [dict(part, text=replacement)]
    return message


class BlenderMcpBridge:
    """Forward MCP JSON-RPC frames; intercept only tool discovery and read results."""

    def __init__(self, upstream: list[str], max_chars: int = 2400) -> None:
        if not upstream:
            raise ValueError("upstream command is required")
        if type(max_chars) is not int or not MIN_BUDGET <= max_chars <= MAX_BUDGET:
            raise ValueError("max_chars out of range")
        self.upstream = upstream
        self.max_chars = max_chars
        self.snapshots = SnapshotStore()
        self.pending: dict[str, str] = {}
        self.pending_lock = threading.Lock()
        self.output_lock = threading.Lock()
        self.stats = {"compacted": 0, "raw_chars": 0, "forwarded_chars": 0}

    def _write(self, message: dict[str, Any] | str) -> None:
        data = _json(message) + "\n" if isinstance(message, dict) else message
        with self.output_lock:
            sys.stdout.write(data)
            sys.stdout.flush()

    def _receive_client(self, process: subprocess.Popen[str]) -> None:
        try:
            for raw in sys.stdin:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    # Forward errors to the upstream MCP implementation as-is.
                    message = None
                if isinstance(message, dict) and "id" in message:
                    method = message.get("method")
                    params = message.get("params") or {}
                    if method == "tools/call" and isinstance(params, dict) and params.get("name") == "pie_blender_expand":
                        self._write({
                            "jsonrpc": "2.0",
                            "id": message["id"],
                            "result": self.snapshots.expand(params.get("arguments", {})),
                        })
                        continue
                    if method == "tools/list":
                        marker = "__tools_list__" if not (isinstance(params, dict) and params.get("cursor")) else ""
                    elif method == "tools/call" and isinstance(params, dict):
                        marker = str(params.get("name", ""))
                    else:
                        marker = ""
                    if marker:
                        with self.pending_lock:
                            self.pending[_key(message["id"])] = marker
                try:
                    if process.stdin is None:
                        break
                    process.stdin.write(raw)
                    process.stdin.flush()
                except (BrokenPipeError, OSError):
                    break
        finally:
            try:
                if process.stdin:
                    process.stdin.close()
            except OSError:
                pass

    def run(self) -> int:
        try:
            process = subprocess.Popen(
                self.upstream, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=None, text=True, encoding="utf-8", bufsize=1,
            )
        except OSError as exc:
            print(f"PIE Blender MCP upstream cannot start: {exc}", file=sys.stderr)
            return 2
        thread = threading.Thread(target=self._receive_client, args=(process,), daemon=True)
        thread.start()
        try:
            assert process.stdout is not None
            for raw in process.stdout:
                try:
                    message = json.loads(raw)
                    if not isinstance(message, dict) or "id" not in message:
                        self._write(raw)
                        continue
                    with self.pending_lock:
                        tool_name = self.pending.pop(_key(message["id"]), "")
                    if tool_name == "__tools_list__":
                        self._write(extend_tools(message))
                    elif tool_name in OBSERVATION_TOOLS:
                        before = _json(message)
                        result = compact_observation(message, tool_name, self.snapshots, self.max_chars)
                        after = _json(result)
                        if len(after) < len(before):
                            self.stats["compacted"] += 1
                            self.stats["raw_chars"] += len(before)
                            self.stats["forwarded_chars"] += len(after)
                        self._write(result)
                    else:
                        # Preserve error responses, notifications, images, writes,
                        # prompts, resources and unknown future tools byte-for-byte.
                        self._write(raw)
                except (ValueError, TypeError):
                    self._write(raw)
        except KeyboardInterrupt:
            process.terminate()
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            print(_json({"pie_blender_bridge_stats": self.stats, "unit": "characters_not_tokens"}), file=sys.stderr)
        return process.returncode or 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Transparent PIE Blender MCP bridge")
    parser.add_argument("--max-chars", type=int, default=2400)
    parser.add_argument(
        "upstream", nargs=argparse.REMAINDER,
        help="Command after --; default: uvx mcp-for-blender",
    )
    args = parser.parse_args(argv)
    upstream = args.upstream
    if upstream and upstream[0] == "--":
        upstream = upstream[1:]
    return BlenderMcpBridge(upstream or ["uvx", "mcp-for-blender"], args.max_chars).run()


if __name__ == "__main__":
    raise SystemExit(main())
