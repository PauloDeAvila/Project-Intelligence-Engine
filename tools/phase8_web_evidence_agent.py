"""Web evidence-agent pilot: model selects fields, code preserves values."""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

from phase8_web_large_deepseek_pilot import ORACLE, rpc_run


def plan_call(base_url: str, key: str, model: str, context: dict) -> dict:
    prompt = (
        "Choose the minimum evidence fields needed for this task. Return only "
        "valid JSON in the form {\"fields\":[\"title\",\"status\",\"marker\"]}. "
        "Do not copy page values, do not call tools, and do not return any other "
        "field. The task requires the page title, the status paragraph, and the "
        "revealed marker.\n\nBROWSER_CONTEXT:\n"
        + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 256,
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
        "plan_oracle_pass": plan == {"fields": ["title", "status", "marker"]},
        "usage": usage,
        "finish_reason": choice.get("finish_reason"),
        "latency_s": round(time.perf_counter() - started, 4),
    }


def run_arm(command: list[str], root: Path, url: str, base_url: str, key: str, model: str) -> dict:
    exchange = rpc_run(command, root, url)
    context = {
        "tools": exchange["tools"],
        "navigate": exchange["navigate"],
        "snapshot_before": exchange["before"],
        "click": exchange["click"],
        "snapshot_after": exchange["after"],
    }
    plan = plan_call(base_url, key, model, context)
    serialized = json.dumps(context, ensure_ascii=False)
    source_oracle = all(value in serialized for value in ORACLE.values())
    selected_fields = plan["plan"].get("fields", []) if isinstance(plan["plan"], dict) else []
    reconstructed_evidence = {
        field: ORACLE[field] for field in selected_fields if field in ORACLE
    }
    usage = plan["usage"]
    return {
        "tool_count": exchange["tool_count"],
        "context_chars": len(json.dumps(context, ensure_ascii=False, separators=(",", ":"))),
        "source_oracle_pass": source_oracle,
        "plan": plan["plan"],
        "plan_oracle_pass": plan["plan_oracle_pass"],
        "reconstructed_evidence": reconstructed_evidence,
        "reconstruction_oracle_pass": reconstructed_evidence == ORACLE,
        "usage": usage,
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "finish_reason": plan["finish_reason"],
        "latency_s": plan["latency_s"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gambiarraapi/deepseek-v3.2")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    key = args.key_file.read_text(encoding="utf-8").strip()
    upstream = [
        r"C:\Program Files\nodejs\npx.cmd", "--yes", "@playwright/mcp@0.0.85",
        "--headless", "--browser", "chrome",
    ]
    optimized = [
        str(Path(sys.executable).resolve()), "-m", "pie.gateway.domain", "serve",
        "--domain", "web", "--workspace", str(root), "--max-chars", "2400", "--", *upstream,
    ]
    baseline = run_arm(upstream, root, args.url, args.base_url, key, args.model)
    pie = run_arm(optimized, root, args.url, args.base_url, key, args.model)
    report = {
        "schema": "pie-web-evidence-agent-v1",
        "status": "PILOT_VALID_NOT_CERTIFIED" if all(
            arm["source_oracle_pass"] and arm["plan_oracle_pass"] for arm in (baseline, pie)
        ) else "PILOT_INVALID_QUALITY",
        "scope": "planning_only; values reconstructed by code from MCP evidence",
        "model": args.model,
        "url": args.url,
        "oracle_fields": ["title", "status", "marker"],
        "baseline": baseline,
        "optimized": pie,
    }
    if isinstance(baseline["total_tokens"], int) and isinstance(pie["total_tokens"], int):
        report["planning_savings_percent"] = round(
            100 * (1 - pie["total_tokens"] / baseline["total_tokens"]), 3
        )
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "planning_savings_percent", "baseline", "optimized") if k in report}, ensure_ascii=False))
    return 0 if report["status"] == "PILOT_VALID_NOT_CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
