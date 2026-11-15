"""Validate and emit a two-session, plan-only Blender selective-query A/B."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tomllib
import uuid


def _load_profile(path: Path, expected: str) -> dict:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    servers = data.get("mcp_servers")
    if not isinstance(servers, dict) or set(servers) != {expected}:
        raise ValueError(f"profile must contain only {expected}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    root = args.workspace.resolve()
    fixture = (root / scenario["fixture_spec"]).resolve()
    if not fixture.is_file():
        raise ValueError("fixture spec unavailable")
    baseline = _load_profile(args.profiles / "pie-phase3-baseline.config.toml", "blender")
    optimized = _load_profile(args.profiles / "pie-phase3-optimized.config.toml", "pie-blender-optimized")
    baseline_tools = baseline.get("enabled_tools", [])
    optimized_tools = optimized.get("enabled_tools", [])
    task_id = scenario["scenario_id"]
    expected_baseline_tools = scenario["expected_mcp_tools_by_condition"]["baseline"]
    expected_optimized_tools = scenario["expected_mcp_tools_by_condition"]["optimized"]
    if set(baseline_tools) != set(expected_baseline_tools):
        raise ValueError("baseline global tool allowlist differs from scenario")
    if set(optimized_tools) != set(expected_optimized_tools):
        raise ValueError("optimized global tool allowlist differs from scenario")
    if set((baseline["mcp_servers"]["blender"].get("tools") or {})) != set(expected_baseline_tools):
        raise ValueError("baseline server tool allowlist differs from scenario")
    if set((optimized["mcp_servers"]["pie-blender-optimized"].get("tools") or {})) != set(expected_optimized_tools):
        raise ValueError("optimized server tool allowlist differs from scenario")
    optimized_server = optimized["mcp_servers"]["pie-blender-optimized"]
    optimized_args = optimized_server.get("args", [])
    if "pie_blender_query_scene" in baseline_tools:
        raise ValueError("baseline exposes selective query")
    if "pie_blender_query_scene" not in optimized_tools or "pie_blender_query_scene" not in optimized_args:
        raise ValueError("optimized profile does not expose selective query")
    attempt_nonce = uuid.uuid4().hex[:24]
    pair_id = "pair-" + attempt_nonce
    entries = []
    for condition, profile, server, tools in (
        ("baseline", "pie-phase3-baseline.config.toml", "blender", expected_baseline_tools),
        ("optimized", "pie-phase3-optimized.config.toml", "pie-blender-optimized", expected_optimized_tools),
    ):
        entries.append({
            "task_id": task_id, "scenario_id": task_id, "pair_id": pair_id,
            "run_id": f"{condition}-" + uuid.uuid4().hex[:24],
            "condition": condition, "application": "blender", "model": scenario["model"],
            "reasoning_effort": scenario["reasoning_effort"], "profile": profile,
            "expected_mcp_server": server, "expected_mcp_tools": tools,
            "prompt_sha256": hashlib.sha256(scenario["prompt"].encode()).hexdigest(),
            "oracle": scenario["oracle"], "provider_usage_required": True,
        })
    plan = {
        "schema": "pie-phase3-selective-a-plan-v1", "state": "READY_FOR_MANUAL_PILOT",
        "execution": "PLAN_ONLY_NO_MODEL_EXECUTION", "model_sessions": 2,
        "automatic_retry": False, "experiment_type": scenario["experiment_type"],
        "workspace_root": str(root), "fixture_spec": str(fixture), "pair_id": pair_id,
        "scenario_id": task_id,
        "attempt_nonce": attempt_nonce,
        "entries": entries,
        "runtime_validation": {
            "status": "REQUIRED_BEFORE_PAID_EXECUTION",
            "tools_list": "pending",
            "tools_call": "pending",
            "forbidden_tool_rejection": "pending",
        },
        "limitations": [
            "This compares different product capabilities, not transparent compaction.",
            "Provider-reported usage and exact route evidence are required for validity.",
            "The profile allowlists are statically checked; real MCP tools/list and tools/call telemetry must still prove isolation.",
            "A paginated task must use a stable scene or a snapshot-bound contract; task A is single-page.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": plan["state"], "output": str(args.output), "pair_id": pair_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
