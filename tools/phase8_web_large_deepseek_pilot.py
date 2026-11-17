"""One-shot real-provider A/B for transparent Web snapshot compaction.

The runner uses the same local page and oracle in both arms. It records provider
usage and compact metadata only; prompts and complete page responses are not
persisted.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ORACLE = {
    "title": "PIE Large Web Fixture",
    "status": "The deterministic large fixture is ready.",
    "marker": "PIE_WEB_LARGE_FIXTURE_V1",
}


def rpc_run(command: list[str], root: Path, url: str) -> dict:
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        bufsize=1,
        cwd=root,
    )
    request_id = 0

    def call(method: str, params: dict | None = None) -> dict:
        nonlocal request_id
        request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("MCP process exited before response")
            response = json.loads(line)
            if response.get("id") == request_id:
                return response
        raise TimeoutError(method)

    try:
        call(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "phase8-large-ab", "version": "1"},
            },
        )
        assert process.stdin is not None
        process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
            + "\n"
        )
        process.stdin.flush()
        tools = call("tools/list").get("result", {}).get("tools", [])
        navigate = call(
            "tools/call",
            {"name": "browser_navigate", "arguments": {"url": url}},
        )
        before = call("tools/call", {"name": "browser_snapshot", "arguments": {}})
        before_text = before.get("result", {}).get("content", [{}])[0].get("text", "")
        try:
            before_payload = json.loads(before_text)
            visible = before_payload.get("preview") or before_text
        except (TypeError, ValueError):
            visible = before_text
        match = re.search(r"button .*\[ref=([a-z][0-9]+)\]", visible)
        if not match:
            raise RuntimeError("button reference absent from visible snapshot")
        click = call(
            "tools/call",
            {"name": "browser_click", "arguments": {"target": match.group(1)}},
        )
        after = call("tools/call", {"name": "browser_snapshot", "arguments": {}})
        return {
            "tool_count": len(tools),
            "navigate_ok": not navigate.get("result", {}).get("isError", False),
            "tools": tools,
            "navigate": navigate.get("result", {}),
            "before": before.get("result", {}),
            "click": click.get("result", {}),
            "after": after.get("result", {}),
        }
    finally:
        process.kill()
        process.wait(timeout=20)


def provider_call(
    base_url: str, key: str, model: str, context: dict, max_output_tokens: int
) -> dict:
    prompt = (
        "You are answering a deterministic local web task. Return ONLY a JSON "
        "object with exactly the string fields title, status, marker. Preserve "
        "values exactly from the browser evidence; do not invent or normalize. "
        "The status field comes from the page's status paragraph, while the "
        "marker field comes from the revealed output element; never copy the "
        "marker value into status. "
        "The task is to navigate the page, activate the reveal action, and "
        "report the page title, status text, and revealed marker.\n\n"
        "BROWSER_CONTEXT:\n"
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
    message = choice.get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        answer = json.loads(content)
    except (TypeError, ValueError):
        answer = {"raw_excerpt": content[:300]}
    return {
        "answer": answer,
        "oracle_pass": answer == ORACLE,
        "usage": result.get("usage") or {},
        "finish_reason": choice.get("finish_reason"),
        "latency_s": round(time.perf_counter() - started, 4),
    }


def arm(
    command: list[str], root: Path, url: str, base_url: str, key: str, model: str,
    max_output_tokens: int,
) -> dict:
    exchange = rpc_run(command, root, url)
    context = {
        "tools": exchange["tools"],
        "navigate": exchange["navigate"],
        "snapshot_before": exchange["before"],
        "click": exchange["click"],
        "snapshot_after": exchange["after"],
    }
    inference = provider_call(base_url, key, model, context, max_output_tokens)
    return {
        "tool_count": exchange["tool_count"],
        "context_chars": len(json.dumps(context, ensure_ascii=False, separators=(",", ":"))),
        "answer": inference["answer"],
        "oracle_pass": inference["oracle_pass"],
        "usage": inference["usage"],
        "finish_reason": inference["finish_reason"],
        "latency_s": inference["latency_s"],
    }


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
    upstream = [
        r"C:\Program Files\nodejs\npx.cmd",
        "--yes",
        "@playwright/mcp@0.0.85",
        "--headless",
        "--browser",
        "chrome",
    ]
    optimized = [
        sys.executable,
        "-m",
        "pie.gateway.domain",
        "serve",
        "--domain",
        "web",
        "--workspace",
        str(root),
        "--max-chars",
        str(args.max_chars),
        "--",
        *upstream,
    ]
    report = {
        "schema": "pie-web-large-deepseek-ab-v1",
        "status": "PILOT_PENDING",
        "model": args.model,
        "endpoint": args.base_url,
        "url": args.url,
        "oracle": ORACLE,
        "max_output_tokens": args.max_output_tokens,
        "baseline": arm(upstream, root, args.url, args.base_url, key, args.model, args.max_output_tokens),
        "optimized": arm(optimized, root, args.url, args.base_url, key, args.model, args.max_output_tokens),
    }
    report["status"] = (
        "PILOT_VALID_NOT_CERTIFIED"
        if report["baseline"]["oracle_pass"] and report["optimized"]["oracle_pass"]
        else "PILOT_INVALID_NOT_CERTIFIED"
    )
    base_usage = report["baseline"]["usage"]
    pie_usage = report["optimized"]["usage"]
    for name, usage in (("baseline", base_usage), ("optimized", pie_usage)):
        report[name]["input_tokens"] = usage.get("prompt_tokens")
        report[name]["output_tokens"] = usage.get("completion_tokens")
        report[name]["total_tokens"] = usage.get("total_tokens")
    if isinstance(report["baseline"]["total_tokens"], int) and isinstance(
        report["optimized"]["total_tokens"], int
    ):
        report["savings"] = {
            "input_percent": round(
                100
                * (1 - report["optimized"]["input_tokens"] / report["baseline"]["input_tokens"]),
                3,
            ),
            "total_percent": round(
                100
                * (1 - report["optimized"]["total_tokens"] / report["baseline"]["total_tokens"]),
                3,
            ),
        }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "baseline", "optimized", "savings") if k in report}, ensure_ascii=False))
    return 0 if report["baseline"]["oracle_pass"] and report["optimized"]["oracle_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
