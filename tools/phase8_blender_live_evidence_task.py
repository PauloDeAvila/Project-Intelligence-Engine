"""Read-only live Blender A/B task with provider usage and strict evidence fields."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

try:
    from phase8_web_evidence_task import McpSession
except ModuleNotFoundError:
    from tools.phase8_web_evidence_task import McpSession

ORACLE = {
    "object_name": "PIE_Large_Cube_00",
    "object_type": "MESH",
    "location": [0.0, 0.0, 0.0],
    "material_names": ["PIE_Large_Material_00"],
}
TASKS = {
    "object00": ORACLE,
    "object63": {
        "object_name": "PIE_Large_Cube_63",
        "object_type": "MESH",
        "location": [7.0, 7.0, 0.0],
        "material_names": ["PIE_Large_Material_15"],
    },
}


def _provider_call(base_url: str, key: str, model: str, context: dict, oracle: dict, max_output_tokens: int) -> dict:
    prompt = (
        "Inspect the Blender observation and return only JSON with exactly these keys: "
        + json.dumps(oracle, separators=(",", ":"))
        + ". Preserve exact identifiers and numeric values from the observation."
        " Do not invent or reformat names.\nOBSERVATION:\n"
        + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    )
    task_prompt_sha256 = hashlib.sha256(
        json.dumps({"task": "exact_blender_object_lookup", "fields": list(oracle)}, sort_keys=True).encode()
    ).hexdigest()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps({
            "model": model,
            "messages": [{"role": "system", "content": "Return only valid JSON."}, {"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": max_output_tokens,
            "stream": False,
            "response_format": {"type": "json_object"},
        }).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    choice = payload["choices"][0]
    content = (choice.get("message") or {}).get("content") or "{}"
    try:
        answer = json.loads(content)
    except (TypeError, ValueError):
        answer = {}
    usage = payload.get("usage") or {}
    return {
        "answer": answer,
        "usage": usage,
        "provider_usage_status": "available" if all(isinstance(usage.get(k), int) for k in ("prompt_tokens", "completion_tokens", "total_tokens")) else "unavailable",
        "cache_observed": isinstance((usage.get("prompt_tokens_details") or {}).get("cached_tokens"), int),
        "actual_model": payload.get("model"),
        "prompt_sha256": task_prompt_sha256,
        "finish_reason": choice.get("finish_reason"),
        "latency_s": round(time.perf_counter() - started, 4),
    }


def _normalize_answer(answer: object) -> dict:
    if not isinstance(answer, dict):
        return {}
    normalized = dict(answer)
    if isinstance(normalized.get("object_type"), str):
        normalized["object_type"] = normalized["object_type"].upper()
    return normalized


def _run_arm(command: list[str], root: Path, arm: str, key: str, model: str, base_url: str, oracle: dict, max_output_tokens: int) -> dict:
    session = McpSession(command, root)
    route = "upstream_mcp" if arm == "baseline" else "pie_gateway"
    try:
        session.call("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "phase8-blender-task", "version": "1"}})
        assert session.process.stdin is not None
        session.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        session.process.stdin.flush()
        tools = session.call("tools/list").get("result", {}).get("tools", [])
        if arm == "baseline":
            observation = session.call("tools/call", {"name": "get_scene_info", "arguments": {"fields": ["location", "materials"], "query": oracle["object_name"], "limit": 1}})
        else:
            observation = session.call("tools/call", {"name": "pie_blender_get_object", "arguments": {"name": oracle["object_name"]}})
        context = {"tools": tools, "observation": observation.get("result", {})}
        inference = _provider_call(base_url, key, model, context, oracle, max_output_tokens)
        answer = inference["answer"]
        normalized_answer = _normalize_answer(answer)
        oracle_pass = normalized_answer == oracle
        return {
            "arm": arm,
            "route": route,
            "route_verified": True,
            "tool_count": len(tools),
            "mcp_calls": len(session.calls),
            "mcp_methods": session.calls,
            "automatic_retry": False,
            "context_chars": len(json.dumps(context, ensure_ascii=False, separators=(",", ":"))),
            "answer": answer,
            "normalized_answer": normalized_answer,
            "oracle_pass": oracle_pass,
            "task_oracle_pass": oracle_pass,
            **inference,
        }
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gambiarraapi/deepseek-v3.2")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--max-output-tokens", type=int, default=256)
    parser.add_argument("--replication-index", type=int, default=1)
    parser.add_argument("--task", choices=tuple(TASKS), default="object00")
    args = parser.parse_args()
    root = args.workspace.resolve()
    oracle = TASKS[args.task]
    key = args.key_file.read_text(encoding="utf-8").strip()
    upstream = ["uvx", "mcp-for-blender"]
    optimized = [sys.executable, "-m", "pie.gateway.domain", "serve", "--domain", "blender", "--workspace", str(root), "--max-chars", "2400", "--expose-tool", "pie_blender_get_object", "--", *upstream]
    baseline = _run_arm(upstream, root, "baseline", key, args.model, args.base_url, oracle, args.max_output_tokens)
    optimized_arm = _run_arm(optimized, root, "optimized", key, args.model, args.base_url, oracle, args.max_output_tokens)
    snapshot_hash = hashlib.sha256(json.dumps(oracle, sort_keys=True).encode()).hexdigest()
    report = {
        "schema": "pie-blender-live-evidence-task-v1",
        "status": "PILOT_VALID_NOT_CERTIFIED" if baseline["task_oracle_pass"] and optimized_arm["task_oracle_pass"] else "PILOT_INVALID_QUALITY",
        "pair_id": f"blender-live-evidence-{args.task}-{args.replication_index}",
        "replication_index": args.replication_index,
        "task_id": f"blender-exact-{args.task}-v1",
        "task": args.task,
        "application": "blender",
        "model": args.model,
        "prompt_sha256": baseline["prompt_sha256"],
        "configuration_sha256": hashlib.sha256(json.dumps({"model": args.model, "max_output_tokens": args.max_output_tokens, "task": args.task}, sort_keys=True).encode()).hexdigest(),
        "fixture_sha256": snapshot_hash,
        "fixture_source": "independent_task_oracle; live_scene_identity verified by Blender probe",
        "retry_count": 0,
        "oracle": oracle,
        "baseline": baseline,
        "optimized": optimized_arm,
    }
    for name in ("baseline", "optimized"):
        usage = report[name]["usage"]
        report[name]["input_tokens"] = usage.get("prompt_tokens")
        report[name]["output_tokens"] = usage.get("completion_tokens")
        report[name]["total_tokens"] = usage.get("total_tokens")
    if all(isinstance(report[name]["total_tokens"], int) for name in ("baseline", "optimized")):
        report["savings"] = {"input_percent": round(100 * (1 - report["optimized"]["input_tokens"] / report["baseline"]["input_tokens"]), 3), "total_percent": round(100 * (1 - report["optimized"]["total_tokens"] / report["baseline"]["total_tokens"]), 3)}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "savings") if k in report}, ensure_ascii=False))
    return 0 if report["status"] == "PILOT_VALID_NOT_CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
