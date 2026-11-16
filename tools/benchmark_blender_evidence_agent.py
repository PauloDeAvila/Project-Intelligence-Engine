"""Experimental Blender evidence agent: model chooses a tool index, PIE renders facts.

One Ollama planning request per arm and one MCP call at most. No model is
asked to copy exact Blender facts. Never invokes Codex, executes model-written
Python, or mutates Blender. These results are NOT Codex certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from benchmark_local_ollama import (
    BLENDER_CODE, _check_response, _provider_usage, _visible_tool_schemas,
    compact_json, correct_answer, ensure_local_model,
    grounded_blender_exact_answer, sha,
)
from verify_phase3_mcp_profiles import Probe, _profile

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OBJECT_NAME = "PIE_Large_Cube_00"
EXPECTED_SERVER = {"baseline": "blender", "optimized": "pie-blender-optimized"}
EXPECTED_TOOL = {"baseline": "execute_blender_code", "optimized": "pie_blender_get_object"}
SYSTEM = (
    "Choose ONE read-only MCP tool and ONE target from the indexed lists. "
    "Return exactly one JSON object with keys tool_index and target_index, both integers. "
    "Do not output object names, data, Python code, or a final answer."
)


class AgentPlanError(ValueError):
    """Fail closed: no tool is called when the model selection is invalid."""


def _parse_plan(response: dict, *, allowed_tool_count: int, target_count: int) -> tuple[int, int]:
    message = response.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise AgentPlanError("Ollama did not return planning JSON")
    try:
        plan = json.loads(message["content"])
    except json.JSONDecodeError as exc:
        raise AgentPlanError("Planning response is not JSON") from exc
    if not isinstance(plan, dict) or set(plan) != {"tool_index", "target_index"}:
        raise AgentPlanError("Planning response must contain only tool_index and target_index")
    ti, oi = plan["tool_index"], plan["target_index"]
    if type(ti) is not int or not 0 <= ti < allowed_tool_count:
        raise AgentPlanError("Invalid tool index")
    if type(oi) is not int or not 0 <= oi < target_count:
        raise AgentPlanError("Invalid target index")
    return ti, oi


def plan_ollama(model: str, visible_tools: list[dict], *,
                object_name: str = OBJECT_NAME, num_ctx: int = 8192,
                timeout: int = 240) -> dict:
    """Ask local model for an INDEX, not a text transcription or executable code."""
    if len(visible_tools) != 1:
        raise AgentPlanError("This controlled experiment requires exactly one enabled tool")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Task: read exact Blender object by name. "
             "Targets: " + compact_json([{"index": 0, "name": object_name}]) +
             "\nTools: " + compact_json([{"index": 0, "schema": visible_tools[0]}])},
        ],
        "stream": False, "format": "json", "think": False,
        "options": {"temperature": 0, "seed": 42, "num_ctx": num_ctx, "num_predict": 64},
    }
    payload = compact_json(body).encode("utf-8")
    if len(payload) > 100_000:
        raise AgentPlanError("Planning payload exceeds limit")
    request = Request(OLLAMA_URL, payload, {"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            reply = json.loads(response.read(500_000))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise AgentPlanError("Local model unavailable or invalid response") from exc
    usage = _provider_usage(reply)
    if usage["input_tokens"] >= num_ctx - 64:
        raise AgentPlanError("Planning context may be truncated")
    tool_index, target_index = _parse_plan(reply, allowed_tool_count=1, target_count=1)
    return {
        "tool_index": tool_index, "target_index": target_index,
        "usage": usage, "planning_wall_ms": round((time.perf_counter() - started) * 1000, 3),
        "plan_sha256": sha(reply["message"]["content"]),
    }


def render_baseline_source(result: dict, *, object_name: str = OBJECT_NAME) -> str:
    """Extract the baseline marker and render only canonical source values."""
    parts = result.get("content")
    if not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict):
        raise ValueError("Invalid baseline MCP content")
    content = parts[0].get("text")
    if not isinstance(content, str):
        raise ValueError("Invalid baseline MCP text")
    marker = "PIE_LOCAL_OBJECT_V1="
    where = content.find(marker)
    if where == -1:
        raise ValueError("Baseline MCP marker missing")
    try:
        value, _ = json.JSONDecoder().raw_decode(content[where + len(marker):])
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid baseline object JSON") from exc
    # Reuse source validation for both arms; it never reads the benchmark gold.
    normalized = {"observations_json": compact_json([{
        "content": [{"type": "text", "text": compact_json(value)}]}])}
    return grounded_blender_exact_answer(normalized, object_name)


def run_arm(profile: Path, workspace: Path, scenario: dict, condition: str,
            model: str, num_ctx: int = 8192, timeout: int = 240) -> dict:
    if condition not in EXPECTED_TOOL or scenario.get("application") != "blender":
        raise ValueError("Only the Blender exact fixture is supported")
    config, server, args, configured_env = _profile(profile, workspace)
    if server != EXPECTED_SERVER[condition]:
        raise ValueError("Wrong MCP server for condition")
    environment = dict(os.environ, **configured_env)
    process = subprocess.Popen(
        [config["command"], *args], cwd=workspace, env=environment,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", bufsize=1,
    )
    probe = Probe(process)
    started = time.perf_counter()
    try:
        init = probe.call(1, "initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "pie-blender-evidence-agent", "version": "1"},
        })
        if "error" in init or not isinstance(init.get("result"), dict):
            raise ValueError("MCP initialize failed")
        probe.notify("notifications/initialized")
        tools = _check_response(probe.call(2, "tools/list", {}), "tools/list").get("tools")
        if not isinstance(tools, list):
            raise ValueError("Missing MCP tool catalog")
        visible = _visible_tool_schemas(tools, config, "profile")
        expected_tool = EXPECTED_TOOL[condition]
        if len(visible) != 1 or visible[0].get("name") != expected_tool:
            raise ValueError("Unexpected enabled tool in exact-object benchmark")
        # The model makes a bounded tool-selection decision BEFORE the MCP call.
        planning = plan_ollama(model, visible, num_ctx=num_ctx, timeout=timeout)
        if planning["tool_index"] != 0 or planning["target_index"] != 0:
            raise AgentPlanError("Incorrect tool or target selected")
        arguments = ({"code": BLENDER_CODE} if condition == "baseline"
                     else {"name": OBJECT_NAME})
        call = {"name": expected_tool, "arguments": arguments}
        result = _check_response(probe.call(3, "tools/call", call), "tools/call")
        if condition == "baseline":
            answer = render_baseline_source(result)
        else:
            answer = grounded_blender_exact_answer(
                {"observations_json": compact_json([result])}, OBJECT_NAME)
        oracle, _ = correct_answer(scenario, answer)
        return {
            "condition": condition, "server": server, "selected_tool": expected_tool,
            "plan_valid": True, "oracle_pass": oracle,
            "rendering": "DETERMINISTIC_TOOL_DATA_NOT_MODEL_OUTPUT",
            "answer_sha256": sha(answer),
            "schema_chars": len(compact_json(visible)),
            "model": model, "usage": planning["usage"],
            "plan_sha256": planning["plan_sha256"],
            "planning_wall_ms": planning["planning_wall_ms"],
            "total_wall_ms": round((time.perf_counter() - started) * 1000, 3),
            "mcp_calls": 1,
        }
    finally:
        probe.close()


def compare_pair(baseline: dict, optimized: dict) -> dict:
    if not baseline.get("oracle_pass") or not optimized.get("oracle_pass"):
        return {"state": "ORACLE_FAILED", "savings_percent": None}
    left, right = baseline["usage"]["total_tokens"], optimized["usage"]["total_tokens"]
    if left <= 0:
        raise ValueError("Missing positive provider usage")
    return {
        "state": "LOCAL_AGENT_PLANNING_TOKENS_COMPARED",
        "savings_percent": round(100 * (left - right) / left, 3),
        "baseline_tokens": left, "optimized_tokens": right,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--baseline-profile", type=Path, required=True)
    parser.add_argument("--optimized-profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=240)
    options = parser.parse_args(argv)
    if not 1 <= options.repetitions <= 3 or not 2048 <= options.num_ctx <= 8192:
        parser.error("repetitions must be 1..3 and num_ctx 2048..8192")
    output = options.output.resolve()
    if output.exists():
        parser.error("Refusing to overwrite existing evidence file")
    workspace = options.workspace.resolve(strict=True)
    scenario = json.loads(options.scenario.read_text(encoding="utf-8"))
    if scenario.get("scenario_id") != "blender-selective-location-v3":
        parser.error("Only frozen Blender v3 fixture may be used in this experiment")
    ensure_local_model(options.model)
    profiles = {"baseline": options.baseline_profile.resolve(strict=True),
                "optimized": options.optimized_profile.resolve(strict=True)}
    report = {
        "schema": "pie-blender-evidence-agent-v1",
        "scenario": scenario["scenario_id"],
        "method": "model_selects_index_then_mcp_executes_then_code_renders",
        "model": options.model, "num_ctx": options.num_ctx,
        "codex_sessions_started": 0, "codex_certification": "NOT_CERTIFIED",
        "output_values_logged": False, "runs": [],
    }
    status = 0
    for repetition in range(1, options.repetitions + 1):
        order = ("baseline", "optimized") if repetition % 2 else ("optimized", "baseline")
        pair = {"repetition": repetition, "order": list(order), "arms": {}}
        for condition in order:
            try:
                arm = run_arm(profiles[condition], workspace, scenario, condition,
                              options.model, options.num_ctx, options.timeout)
                pair["arms"][condition] = arm
                if not arm["oracle_pass"]:
                    pair["error"] = "SOURCE_ORACLE_FAILED"
                    status = 2
                    break
            except (AgentPlanError, ValueError, RuntimeError, OSError) as exc:
                pair["error"] = type(exc).__name__
                status = 2
                break
        if not status:
            pair["comparison"] = compare_pair(pair["arms"]["baseline"],
                                              pair["arms"]["optimized"])
        report["runs"].append(pair)
        if status:
            break
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
