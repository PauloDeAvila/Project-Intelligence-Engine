"""Controlled Web task: DeepSeek chooses an action, PIE preserves the result."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from phase8_web_large_deepseek_pilot import ORACLE


class McpSession:
    def __init__(self, command: list[str], root: Path) -> None:
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            cwd=root,
        )
        self.request_id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self.request_id += 1
        request = {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params or {}}
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("MCP process exited before response")
            response = json.loads(line)
            if response.get("id") == self.request_id:
                return response
        raise TimeoutError(method)

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=20)


def _result_text(value: object) -> str:
    parts: list[str] = []

    def walk(item: object) -> None:
        if isinstance(item, dict):
            if isinstance(item.get("text"), str):
                parts.append(item["text"])
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return "\n".join(parts)


def _visible_snapshot(result: dict) -> str:
    text = _result_text(result)
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return text
    if isinstance(payload, dict):
        return str(payload.get("preview") or text)
    return text


def _extract_source_evidence(result: dict) -> dict[str, str]:
    source = _result_text(result)
    return {field: value for field, value in ORACLE.items() if value in source}


def _provider_call(base_url: str, key: str, model: str, context: dict, max_output_tokens: int) -> dict:
    prompt = (
        "Perform the local web task. Return only JSON with exactly these keys: "
        '{"action":"reveal","target_ref":"...","fields":["title","status","marker"]}. '
        "Choose target_ref from the visible button reference in the browser snapshot. "
        "Do not copy page values and do not invent references."
        "\n\nBROWSER_CONTEXT:\n"
        + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max_output_tokens,
        "stream": False,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.load(response)
    choice = result["choices"][0]
    content = (choice.get("message") or {}).get("content") or ""
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        plan = json.loads(content)
    except (TypeError, ValueError):
        plan = {"raw_excerpt": content[:300]}
    usage = result.get("usage") or {}
    return {
        "plan": plan,
        "usage": usage,
        "finish_reason": choice.get("finish_reason"),
        "latency_s": round(time.perf_counter() - started, 4),
    }


def _run_arm(command: list[str], root: Path, url: str, base_url: str, key: str, model: str, max_output_tokens: int) -> dict:
    session = McpSession(command, root)
    try:
        session.call(
            "initialize",
            {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "phase8-web-task", "version": "1"}},
        )
        assert session.process.stdin is not None
        session.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        session.process.stdin.flush()
        tools = session.call("tools/list").get("result", {}).get("tools", [])
        navigate = session.call("tools/call", {"name": "browser_navigate", "arguments": {"url": url}})
        before = session.call("tools/call", {"name": "browser_snapshot", "arguments": {}})
        visible = _visible_snapshot(before.get("result", {}))
        match = re.search(r"button .*\[ref=([a-z][0-9]+)\]", visible)
        if not match:
            raise RuntimeError("button reference absent from visible snapshot")
        target_ref = match.group(1)
        context = {"tools": tools, "navigate": navigate.get("result", {}), "snapshot_before": before.get("result", {})}
        inference = _provider_call(base_url, key, model, context, max_output_tokens)
        expected_plan = {"action": "reveal", "target_ref": target_ref, "fields": ["title", "status", "marker"]}
        plan_oracle = inference["plan"] == expected_plan
        if not plan_oracle:
            return {
                "tool_count": len(tools),
                "context_chars": len(json.dumps(context, ensure_ascii=False, separators=(",", ":"))),
                "plan": inference["plan"],
                "plan_oracle_pass": False,
                "source_oracle_pass": False,
                "task_oracle_pass": False,
                "usage": inference["usage"],
                "finish_reason": inference["finish_reason"],
                "latency_s": inference["latency_s"],
            }
        click = session.call("tools/call", {"name": "browser_click", "arguments": {"target": target_ref}})
        after = session.call("tools/call", {"name": "browser_snapshot", "arguments": {}})
        source_results = {
            "navigate": navigate.get("result", {}),
            "snapshot_before": before.get("result", {}),
            "snapshot_after": after.get("result", {}),
        }
        reconstructed = _extract_source_evidence(source_results)
        return {
            "tool_count": len(tools),
            "context_chars": len(json.dumps(context, ensure_ascii=False, separators=(",", ":"))),
            "navigate_ok": not navigate.get("result", {}).get("isError", False),
            "click_ok": not click.get("result", {}).get("isError", False),
            "plan": inference["plan"],
            "plan_oracle_pass": True,
            "reconstructed_evidence": reconstructed,
            "source_oracle_pass": reconstructed == ORACLE,
            "task_oracle_pass": reconstructed == ORACLE,
            "usage": inference["usage"],
            "finish_reason": inference["finish_reason"],
            "latency_s": inference["latency_s"],
        }
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gambiarraapi/deepseek-v3.2")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--max-chars", type=int, default=2400)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    key = args.key_file.read_text(encoding="utf-8").strip()
    upstream = [r"C:\Program Files\nodejs\npx.cmd", "--yes", "@playwright/mcp@0.0.85", "--headless", "--browser", "chrome"]
    optimized = [sys.executable, "-m", "pie.gateway.domain", "serve", "--domain", "web", "--workspace", str(root), "--max-chars", str(args.max_chars), "--", *upstream]
    baseline = _run_arm(upstream, root, args.url, args.base_url, key, args.model, args.max_output_tokens)
    optimized_arm = _run_arm(optimized, root, args.url, args.base_url, key, args.model, args.max_output_tokens)
    report = {
        "schema": "pie-web-evidence-task-v1",
        "status": "PILOT_VALID_NOT_CERTIFIED" if baseline["task_oracle_pass"] and optimized_arm["task_oracle_pass"] else "PILOT_INVALID_QUALITY",
        "scope": "end_to_end_controlled_task; model selects action, code executes MCP and preserves values",
        "model": args.model,
        "url": args.url,
        "oracle": ORACLE,
        "max_output_tokens": args.max_output_tokens,
        "baseline": baseline,
        "optimized": optimized_arm,
    }
    for arm_name in ("baseline", "optimized"):
        usage = report[arm_name].get("usage") or {}
        report[arm_name]["input_tokens"] = usage.get("prompt_tokens")
        report[arm_name]["output_tokens"] = usage.get("completion_tokens")
        report[arm_name]["total_tokens"] = usage.get("total_tokens")
    if all(isinstance(report[name]["total_tokens"], int) for name in ("baseline", "optimized")):
        report["savings"] = {"input_percent": round(100 * (1 - report["optimized"]["input_tokens"] / report["baseline"]["input_tokens"]), 3), "total_percent": round(100 * (1 - report["optimized"]["total_tokens"] / report["baseline"]["total_tokens"]), 3)}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "baseline", "optimized", "savings") if k in report}, ensure_ascii=False))
    return 0 if report["status"] == "PILOT_VALID_NOT_CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
