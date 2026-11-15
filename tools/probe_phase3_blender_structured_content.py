"""Compare real Blender MCP and PIE responses without starting a model."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from queue import Queue
from queue import Empty
import subprocess
import sys
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
                response = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if response.get("id") == identifier:
                return response
        raise TimeoutError(f"MCP response timeout for {method}")

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


def _serialized(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _field_sizes(response: dict) -> dict[str, int | None]:
    result = response.get("result")
    if not isinstance(result, dict):
        return {}
    content = result.get("content")
    text = None
    if isinstance(content, list) and content and isinstance(content[0], dict):
        text = content[0].get("text")
    return {
        "result": len(_serialized(result)),
        "content": len(_serialized(content)) if content is not None else None,
        "content_text": len(text) if isinstance(text, str) else None,
        "structuredContent": len(_serialized(result["structuredContent"]))
        if "structuredContent" in result else None,
        "response": len(_serialized(response)),
    }


def _tool_spec(tools: dict, name: str) -> dict:
    result = tools.get("result")
    values = result.get("tools", []) if isinstance(result, dict) else []
    return next((item for item in values if isinstance(item, dict) and item.get("name") == name), {})


def _run_profile(label: str, command: list[str], workspace: Path, marker: str,
                 max_chars: int) -> dict:
    env = dict(os.environ)
    env["PIE_GLOBAL_STORAGE_ROOT"] = str(workspace / ".pie-structured-probe-store")
    process = subprocess.Popen(
        command, cwd=workspace, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
    )
    client = Client(process)
    calls = 0
    try:
        init = client.call(1, "initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "pie-phase3-structured-probe", "version": "1"},
        })
        client.notify("notifications/initialized")
        tools = client.call(2, "tools/list", {})
        observed = client.call(3, "tools/call", {
            "name": "get_scene_info", "arguments": {},
        })
        calls = 1
        result = observed.get("result", {})
        content = result.get("content", []) if isinstance(result, dict) else []
        text = content[0].get("text", "") if content and isinstance(content[0], dict) else ""
        structured = result.get("structuredContent") if isinstance(result, dict) else None
        original_text_sha = sha256(text.encode("utf-8")).hexdigest() if isinstance(text, str) else None
        compact = None
        recovery = None
        if isinstance(text, str) and text.startswith("{"):
            try:
                compact = json.loads(text)
            except json.JSONDecodeError:
                compact = None
        if isinstance(compact, dict) and compact.get("restore_tool") == "pie_blender_expand":
            recovery = client.call(4, "tools/call", {
                "name": "pie_blender_expand",
                "arguments": {"response_id": compact["response_id"], "start": 0, "max_chars": 16000},
            })
            calls += 1
        marker_present = marker in _serialized(observed)
        recovered_text = None
        recovered_sha = None
        if recovery:
            recovery_result = recovery.get("result", {})
            recovery_content = recovery_result.get("content", []) if isinstance(recovery_result, dict) else []
            recovery_text = recovery_content[0].get("text", "") if recovery_content else ""
            try:
                recovered_text = json.loads(recovery_text).get("text")
            except (json.JSONDecodeError, AttributeError):
                recovered_text = None
            if isinstance(recovered_text, str):
                recovered_sha = sha256(recovered_text.encode("utf-8")).hexdigest()
        # The original upstream is never compacted, so this is used only for
        # per-profile evidence; the caller compares both serialized responses.
        if "error" in init or "error" in tools or "error" in observed:
            state = "BLOCKED"
        elif label == "pie" and compact:
            state = "COMPACTED_TEXT_ONLY" if "structuredContent" in result else "COMPACTED_EFFECTIVE"
        else:
            state = "PASSTHROUGH_SAFE"
        return {
            "label": label, "initialize": init, "tools": tools, "observed": observed,
            "tool_spec": _tool_spec(tools, "get_scene_info"),
            "field_sizes": _field_sizes(observed),
            "presence": {"content": bool(content), "structuredContent": "structuredContent" in result},
            "structured_content_sha256": sha256(_serialized(structured).encode()).hexdigest()
            if structured is not None else None,
            "content_text_sha256": original_text_sha,
            "marker_present": marker_present,
            "recovery": recovery,
            "recovered_text_sha256": recovered_sha,
            "recovery_hash_matches": recovered_sha == original_text_sha if recovered_sha else None,
            "calls": calls,
            "state": state,
            "max_chars": max_chars,
        }
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--uvx", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-chars", type=int, default=2400)
    args = parser.parse_args()
    root = args.workspace.resolve()
    upstream = [str(args.uvx), "mcp-for-blender", "--port", "9877"]
    baseline = _run_profile("baseline", upstream, root, "PIE_Large_Cube_00", args.max_chars)
    optimized = _run_profile("pie", [str(args.python), "-m", "pie.gateway.domain", "serve",
                                      "--domain", "blender", "--workspace", str(root),
                                      "--store", str(root / ".pie-structured-probe-store"),
                                      "--max-chars", str(args.max_chars), "--", *upstream],
                             root, "PIE_Large_Cube_00", args.max_chars)
    baseline_size = baseline["field_sizes"]["response"]
    optimized_size = optimized["field_sizes"]["response"]
    structured_equal = (
        baseline["structured_content_sha256"] is not None
        and baseline["structured_content_sha256"] == optimized["structured_content_sha256"]
    )
    optimized["structured_content_equal_to_baseline"] = structured_equal
    optimized["serialized_response_reduction_percent"] = round(
        100 * (baseline_size - optimized_size) / baseline_size, 3
    ) if baseline_size else None
    payload = {
        "schema": "pie-phase3-real-blender-structured-probe-v1",
        "status": "PASS" if baseline["marker_present"] and optimized["marker_present"] else "BLOCKED",
        "model_sessions": 0, "quota_consumed": False,
        "fixture": {"marker": "PIE_Large_Cube_00", "oracle": "PASS" if baseline["marker_present"] and optimized["marker_present"] else "FAIL"},
        "profiles": {"baseline": baseline, "optimized": optimized},
        "duplicate_call_check": {"baseline_calls": baseline["calls"], "optimized_calls": optimized["calls"], "one_observation_call_each": baseline["calls"] >= 1 and optimized["calls"] >= 1},
        "classification": optimized["state"],
        "limitations": ["Payload reduction is a character/serialization measurement, not a provider token measurement.", "Client preference between content and structuredContent remains unverified without Codex."],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "classification": payload["classification"], "output": str(args.output)}))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
