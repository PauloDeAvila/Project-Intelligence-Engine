"""Multi-choice Blender MCP evidence-agent benchmark (local Ollama only).

Two advertised read-only tools per arm; three distractor target names.
The model chooses tool/target indices BEFORE the real MCP call. Code, not the
model, binds the chosen target to safe allowlisted arguments and renders facts.
No Codex calls. No automatic retries. This does not certify the Codex agent.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from benchmark_local_ollama import (
    BLENDER_CODE, _check_response, _provider_usage, _visible_tool_schemas,
    compact_json, correct_answer, ensure_local_model,
    grounded_blender_exact_answer, sha,
)
from benchmark_blender_evidence_agent import (
    AgentPlanError, _parse_plan, render_baseline_source,
)
from verify_phase3_mcp_profiles import Probe, _profile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pie.integrations.blender_routing import route_exact_object, ExactRouteError

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
EXPECTED_SERVER = {"baseline": "blender", "optimized": "pie-blender-optimized"}
TARGET_PATTERN = re.compile(r"PIE_Large_Cube_(?:0[0-9]|[1-5][0-9]|6[0-3])\Z")
TOOL_NAMES = {
    "baseline": frozenset(("execute_blender_code", "get_scene_info")),
    "optimized": frozenset(("pie_blender_get_object", "pie_blender_query_scene")),
}
SELECTED_TOOL = {"baseline": "execute_blender_code", "optimized": "pie_blender_get_object"}
TASKS = (
    {"task_id": "cube-13-middle", "target": "PIE_Large_Cube_13",
     "candidates": ("PIE_Large_Cube_00", "PIE_Large_Cube_13", "PIE_Large_Cube_63"),
     "tool_order": ("broad", "exact")},
    {"task_id": "cube-63-last", "target": "PIE_Large_Cube_63",
     "candidates": ("PIE_Large_Cube_13", "PIE_Large_Cube_00", "PIE_Large_Cube_63"),
     "tool_order": ("exact", "broad")},
    {"task_id": "cube-00-first", "target": "PIE_Large_Cube_00",
     "candidates": ("PIE_Large_Cube_00", "PIE_Large_Cube_63", "PIE_Large_Cube_13"),
     "tool_order": ("broad", "exact")},
)
SYSTEM = (
    "You are a tool routing planner. A target name is given in the TASK. "
    "Select the target_index of that exact name in CANDIDATES. "
    "Select the tool_index of the direct read-only exact-object lookup, "
    "not the broad scene summary or paginated search. "
    "Reply with exactly one JSON object containing integer tool_index "
    "and target_index. No tool call, explanation, object data, or code."
)


PLAN_ERROR_CODES = {
    "Ollama did not return planning JSON": "MISSING_MODEL_CONTENT",
    "Planning response is not JSON": "INVALID_MODEL_JSON",
    "Planning response must contain only tool_index and target_index": "INVALID_PLAN_SHAPE",
    "Invalid tool index": "INVALID_TOOL_INDEX",
    "Invalid target index": "INVALID_TARGET_INDEX",
}


class ChoicePlanError(AgentPlanError):
    """Known failure code plus safe diagnostics; never store model response text."""

    def __init__(self, code: str, *, usage: dict | None = None,
                 plan_sha256: str | None = None, indices: tuple[int, int] | None = None,
                 model_request_attempted: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.usage = usage
        self.plan_sha256 = plan_sha256
        self.indices = indices
        self.model_request_attempted = model_request_attempted


def safe_plan_failure(exc: AgentPlanError, condition: str) -> dict:
    """Persist classification, without fabricating success or leaking model text."""
    diagnostic = {
        "failed_condition": condition, "failure_stage": "MODEL_PLAN",
        "failure_code": exc.code if isinstance(exc, ChoicePlanError)
        else "UNCLASSIFIED_AGENT_PLAN_ERROR",
        "mcp_tool_calls_executed": 0,
    }
    if isinstance(exc, ChoicePlanError):
        diagnostic["model_request_attempted"] = exc.model_request_attempted
        if exc.usage is not None:
            diagnostic["failed_plan_usage"] = exc.usage
        if exc.plan_sha256 is not None:
            diagnostic["failed_plan_sha256"] = exc.plan_sha256
        if exc.indices is not None:
            diagnostic["selected_tool_index"] = exc.indices[0]
            diagnostic["selected_target_index"] = exc.indices[1]
    return diagnostic


def validate_task(task: dict) -> tuple[str, tuple[str, ...]]:
    target, names = task.get("target"), task.get("candidates")
    if not isinstance(target, str) or not TARGET_PATTERN.fullmatch(target):
        raise ValueError("Invalid fixture task target")
    if (not isinstance(names, (list, tuple)) or len(names) != 3
            or len(set(names)) != 3
            or target not in names
            or any(not isinstance(name, str) or not TARGET_PATTERN.fullmatch(name) for name in names)):
        raise ValueError("Invalid fixture candidate set")
    return target, tuple(names)


def ordered_catalog(visible: list[dict], condition: str, task: dict) -> list[dict]:
    """Order *real server tool schemas* to avoid rewarding a constant index."""
    if condition not in TOOL_NAMES:
        raise ValueError("Unknown arm")
    names = {tool.get("name") for tool in visible if isinstance(tool, dict)}
    if names != TOOL_NAMES[condition] or len(visible) != 2:
        raise ValueError("Each arm must expose exactly two expected tools")
    tool_by_name = {tool["name"]: tool for tool in visible}
    primary = SELECTED_TOOL[condition]
    alternate = next(iter(TOOL_NAMES[condition] - {primary}))
    order = task.get("tool_order")
    if order not in (("exact", "broad"), ("broad", "exact")):
        raise ValueError("Invalid predetermined tool ordering")
    return [tool_by_name[primary if kind == "exact" else alternate] for kind in order]


def independent_fixture_oracle(target: str) -> dict:
    """Independent specification from Blender 8x8 generator, not the MCP value."""
    if not isinstance(target, str) or not TARGET_PATTERN.fullmatch(target):
        raise ValueError("Invalid fixed fixture name")
    index = int(target.rsplit("_", 1)[1])
    return {
        "object_name": target, "object_type": "MESH",
        "location": [index % 8, index // 8, 0],
        "material_names": [f"PIE_Large_Material_{index // 4:02d}"],
    }


def plan_choice(model: str, catalog: list[dict], task: dict, *,
                num_ctx: int = 8192, timeout: int = 240) -> dict:
    target, candidates = validate_task(task)
    if len(catalog) != 2:
        raise ChoicePlanError("INVALID_CATALOG_SIZE")
    choices = [{"index": index, "name": name} for index, name in enumerate(candidates)]
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content":
         "TASK: Look up object named " + json.dumps(target) +
         " in the active Blender scene. Return its exact type, location and material names. "
         "CANDIDATES=" + compact_json(choices) +
         " TOOLS=" + compact_json([
             {"index": index, "schema": spec} for index, spec in enumerate(catalog)])},
    ]
    payload = {"model": model, "messages": messages, "stream": False,
               "format": "json", "think": False,
               "options": {"temperature": 0, "seed": 42, "num_ctx": num_ctx,
                           "num_predict": 64}}
    wire = compact_json(payload).encode("utf-8")
    if len(wire) > 100_000:
        raise ChoicePlanError("PLANNING_PAYLOAD_OVERSIZED")
    started = time.perf_counter()
    try:
        with urlopen(Request(OLLAMA_URL, wire,
                             {"Content-Type": "application/json"}, method="POST"),
                     timeout=timeout) as response:
            body = json.loads(response.read(500_000))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ChoicePlanError(
            "OLLAMA_TRANSPORT_FAILURE", model_request_attempted=True) from exc
    usage = _provider_usage(body)
    message = body.get("message") if isinstance(body, dict) else None
    response_text = message.get("content") if isinstance(message, dict) else None
    fingerprint = sha(response_text) if isinstance(response_text, str) else None
    if usage["input_tokens"] >= num_ctx - 64:
        raise ChoicePlanError(
            "POSSIBLE_CONTEXT_TRUNCATION", usage=usage,
            plan_sha256=fingerprint, model_request_attempted=True)
    try:
        tool_index, target_index = _parse_plan(
            body, allowed_tool_count=len(catalog), target_count=len(candidates))
    except AgentPlanError as exc:
        raise ChoicePlanError(
            PLAN_ERROR_CODES.get(str(exc), "INVALID_MODEL_PLAN"),
            usage=usage, plan_sha256=fingerprint,
            model_request_attempted=True) from exc
    chosen = (tool_index, target_index)
    selected_name = catalog[tool_index]["name"]
    if selected_name not in TOOL_NAMES["baseline"] | TOOL_NAMES["optimized"]:
        raise ChoicePlanError(
            "UNRECOGNIZED_TOOL", usage=usage, plan_sha256=fingerprint,
            indices=chosen, model_request_attempted=True)
    if selected_name not in ("execute_blender_code", "pie_blender_get_object"):
        raise ChoicePlanError(
            "NON_EXACT_TOOL_SELECTED", usage=usage, plan_sha256=fingerprint,
            indices=chosen, model_request_attempted=True)
    if candidates[target_index] != target:
        raise ChoicePlanError(
            "WRONG_TARGET_SELECTED", usage=usage, plan_sha256=fingerprint,
            indices=chosen, model_request_attempted=True)
    return {
        "tool_index": tool_index, "target_index": target_index,
        "usage": usage, "planning_ms": round((time.perf_counter() - started) * 1000, 3),
        "plan_sha256": sha(body["message"]["content"]),
    }


def deterministic_choice(catalog: list[dict], task: dict, condition: str) -> dict:
    """Use the reusable PIE exact router before any model call.

    An explicit exact object name is already a complete routing instruction.
    Routing it with Qwen is unnecessary expense and a source of errors.
    """
    target, candidates = validate_task(task)
    route = route_exact_object(catalog, candidates, target)
    if route.tool_name != SELECTED_TOOL[condition]:
        raise ExactRouteError("Exact router selected a tool unavailable for this arm")
    return {
        "tool_index": route.tool_index,
        "target_index": route.target_index,
        "usage": None,
        "planning_ms": 0.0,
        "plan_sha256": None,
        "routing_strategy": route.strategy,
        "provider_requests": 0,
    }


def _read_only_blender_code(target: str) -> str:
    """Reuse audited read-only extraction, changing only a validated name literal."""
    if not TARGET_PATTERN.fullmatch(target):
        raise ValueError("Invalid Blender object name")
    original = 'bpy.data.objects.get("PIE_Large_Cube_00")'
    if BLENDER_CODE.count(original) != 1:
        raise RuntimeError("Audited baseline extraction template has changed")
    return BLENDER_CODE.replace(
        original, "bpy.context.scene.objects.get(" + json.dumps(target) + ")"
    )


def run_arm(profile: Path, workspace: Path, condition: str, task: dict,
            model: str, *, num_ctx: int = 8192, timeout: int = 240,
            route_mode: str = "model") -> dict:
    target, candidates = validate_task(task)
    config, server, args, configured_env = _profile(profile, workspace)
    if server != EXPECTED_SERVER[condition]:
        raise ValueError("Incorrect MCP server for arm")
    environment = dict(os.environ, **configured_env)
    process = subprocess.Popen(
        [config["command"], *args], cwd=workspace, env=environment,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", bufsize=1)
    probe = Probe(process)
    started = time.perf_counter()
    try:
        init = probe.call(1, "initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "pie-blender-choice-agent", "version": "1"},
        })
        if "error" in init or not isinstance(init.get("result"), dict):
            raise ValueError("MCP initialize failed")
        probe.notify("notifications/initialized")
        tools = _check_response(probe.call(2, "tools/list", {}), "tools/list").get("tools")
        if not isinstance(tools, list):
            raise ValueError("Missing MCP tool list")
        catalog = ordered_catalog(_visible_tool_schemas(tools, config, "profile"),
                                  condition, task)
        if route_mode == "deterministic":
            plan = deterministic_choice(catalog, task, condition)
        elif route_mode == "model":
            plan = plan_choice(model, catalog, task, num_ctx=num_ctx, timeout=timeout)
        else:
            raise ValueError("Unknown routing mode")
        selected_tool = catalog[plan["tool_index"]]["name"]
        selected_target = candidates[plan["target_index"]]
        if selected_tool != SELECTED_TOOL[condition] or selected_target != target:
            raise ChoicePlanError(
                "ARM_SELECTION_MISMATCH", usage=plan["usage"],
                plan_sha256=plan["plan_sha256"],
                indices=(plan["tool_index"], plan["target_index"]),
                model_request_attempted=True)
        arguments = ({"code": _read_only_blender_code(selected_target)}
                     if condition == "baseline" else {"name": selected_target})
        observation = _check_response(probe.call(3, "tools/call", {
            "name": selected_tool, "arguments": arguments}), "tools/call")
        answer = (render_baseline_source(observation, object_name=target)
                  if condition == "baseline" else
                  grounded_blender_exact_answer({
                      "observations_json": compact_json([observation])}, target))
        parsed = json.loads(answer)
        oracle = parsed == independent_fixture_oracle(target)
        return {
            "condition": condition, "task_id": task["task_id"],
            "model": model, "plan_valid": True, "oracle_pass": oracle,
            "tool_index": plan["tool_index"], "target_index": plan["target_index"],
            "selected_tool": selected_tool, "mcp_calls": 1,
            "rendering": "DETERMINISTIC_TOOL_DATA_NOT_MODEL_OUTPUT",
            "schema_chars": len(compact_json(catalog)),
            "answer_sha256": sha(answer),
            "plan_sha256": plan["plan_sha256"],
            "usage": plan["usage"], "planning_ms": plan["planning_ms"],
            "routing_strategy": ("DETERMINISTIC_EXACT_MATCH_NO_MODEL"
                                  if route_mode == "deterministic"
                                  else "OLLAMA_MODEL_INDEX_SELECTION"),
            "provider_requests": 0 if route_mode == "deterministic" else 1,
            "total_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    finally:
        probe.close()


def compare_pair(baseline: dict, optimized: dict) -> dict:
    if not baseline.get("oracle_pass") or not optimized.get("oracle_pass"):
        return {"state": "ORACLE_FAILED", "planning_token_savings_percent": None}
    if baseline.get("usage") is None and optimized.get("usage") is None:
        return {"state": "DETERMINISTIC_ROUTING_NO_MODEL",
                "planning_token_savings_percent": None,
                "provider_requests": 0,
                "note": "Both arms performed real MCP calls with zero LLM requests"}
    if not isinstance(baseline.get("usage"), dict) or not isinstance(optimized.get("usage"), dict):
        return {"state": "INCOMPARABLE_ROUTING_MODES",
                "planning_token_savings_percent": None}
    a, b = baseline["usage"]["total_tokens"], optimized["usage"]["total_tokens"]
    if type(a) is not int or type(b) is not int or a <= 0:
        raise ValueError("Missing provider token usage")
    return {"state": "LOCAL_MULTI_CHOICE_PLANNING_COMPARE",
            "planning_token_savings_percent": round(100 * (a - b) / a, 3),
            "baseline_tokens": a, "pie_tokens": b}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--baseline-profile", type=Path, required=True)
    parser.add_argument("--optimized-profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--route-mode", choices=("deterministic", "model"),
                        default="deterministic",
                        help="deterministic: exact-name fast path, zero model requests; model: strict legacy Qwen planning")
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--max-tasks", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=240)
    options = parser.parse_args(argv)
    if not 1 <= options.max_tasks <= len(TASKS) or not 2048 <= options.num_ctx <= 8192:
        parser.error("max-tasks=1..3, num-ctx=2048..8192")
    output = options.output.resolve()
    if output.exists():
        parser.error("Report already exists; write-once evidence only")
    workspace = options.workspace.resolve(strict=True)
    profiles = {"baseline": options.baseline_profile.resolve(strict=True),
                "optimized": options.optimized_profile.resolve(strict=True)}
    if options.route_mode == "model":
        ensure_local_model(options.model)
    report = {
        "schema": "pie-blender-multi-choice-v1",
        "method": "one_model_index_decision_per_arm_then_exact_mcp_then_source_renderer",
        "fixture": "64 deterministic Blender cubes, 3 tasks, 2 tools per arm",
        "model": options.model if options.route_mode == "model" else None,
        "route_mode": options.route_mode,
        "num_ctx": options.num_ctx,
        "codex_sessions_started": 0, "codex_certification": "NOT_CERTIFIED",
        "rows": [],
    }
    status = 0
    for index, task in enumerate(TASKS[:options.max_tasks]):
        order = ("baseline", "optimized") if index % 2 == 0 else ("optimized", "baseline")
        pair = {"task_id": task["task_id"], "order": list(order), "arms": {}}
        for condition in order:
            try:
                arm = run_arm(profiles[condition], workspace, condition, task,
                              options.model, num_ctx=options.num_ctx, timeout=options.timeout,
                              route_mode=options.route_mode)
                pair["arms"][condition] = arm
                if not arm["oracle_pass"]:
                    raise ValueError("Independent fixture oracle failed")
            except AgentPlanError as exc:
                pair["status"] = "FAILED_CLOSED"
                pair["reason_type"] = "AgentPlanError"
                pair.update(safe_plan_failure(exc, condition))
                status = 2
                break
            except (ValueError, RuntimeError, OSError) as exc:
                pair["status"] = "FAILED_CLOSED"
                pair["reason_type"] = type(exc).__name__
                pair["failed_condition"] = condition
                pair["failure_code"] = "NON_PLAN_FAILURE"
                status = 2
                break
        if not status:
            pair["status"] = "VALID_PAIR"
            pair["comparison"] = compare_pair(pair["arms"]["baseline"],
                                               pair["arms"]["optimized"])
        report["rows"].append(pair)
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
