"""Offline controller for auditable PIE certification preparation.

This module deliberately has no model execution path. It creates immutable
plans, validates evidence, and refuses incomplete correlation before any paid
runner is allowed to be invoked by a future integration.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pie.certification.live_codex import CONDITIONS, _record, _sha, validate_scenario, _expected_mcp_tools
from pie.certification.live_codex import CodexCaptureError, capture_codex, preflight_codex
from pie.certification.task_telemetry import import_provider_record

SCHEMA = "pie-phase3-certification-controller-v1"
DECISIONS = frozenset(("VALID", "INVALID", "INSUFFICIENT_EVIDENCE"))
MAX_SESSIONS = 12


class ControllerError(ValueError):
    """Fail-closed controller validation error."""


def _safe_id(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 80:
        raise ControllerError(f"Invalid {label}")
    if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for c in value):
        raise ControllerError(f"Invalid {label}")
    return value


def _pair_id(scenario_id: str) -> str:
    return "pair-" + hashlib.sha256(scenario_id.encode("utf-8")).hexdigest()[:24]


def _application(scenario: dict[str, Any]) -> str:
    value = " ".join(str(scenario.get(k, "")) for k in ("scenario_id", "required_mcp_server")).lower()
    if "blender" in value:
        return "blender"
    if "web" in value or "playwright" in value:
        return "web"
    raise ControllerError("Scenario must identify Blender or Web")


def _expected_server(scenario: dict[str, Any], condition: str) -> str:
    required = str(scenario.get("required_mcp_server", "")).lower()
    if "blender" in required:
        return "blender" if condition == "baseline" else "pie-blender-optimized"
    if "web" in required or "playwright" in required:
        return "playwright-baseline" if condition == "baseline" else "pie-web-optimized"
    raise ControllerError("Unsupported scenario domain")


def _oracle_spec(scenario: dict[str, Any]) -> dict[str, Any]:
    oracle = scenario.get("oracle")
    if not isinstance(oracle, dict) or not isinstance(oracle.get("kind"), str):
        raise ControllerError("Scenario needs an independent oracle specification")
    kind = oracle["kind"]
    if kind == "blender_material_properties":
        required = ("object_name", "material_name", "roughness", "metallic")
    elif kind == "blender_scene_json":
        required = ("expected",)
    elif kind == "web_local_page":
        required = ("fixture_id", "required_refs", "required_text")
    elif kind == "exact_text":
        required = ("fixture_id", "required_text")
    else:
        raise ControllerError("Unsupported oracle kind")
    if any(key not in oracle for key in required):
        raise ControllerError("Incomplete oracle specification")
    return {key: oracle[key] for key in ("kind", *required)}


def load_scenario(path: Path) -> dict[str, Any]:
    try:
        scenario = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControllerError("Scenario file unavailable or invalid") from exc
    validate_scenario(scenario)
    _safe_id(scenario["scenario_id"], "scenario_id")
    _application(scenario)
    _oracle_spec(scenario)
    return scenario


def build_manifest(*, scenarios: Iterable[dict[str, Any]], workspace: Path,
                   baseline_profile: str, optimized_profile: str,
                   repetitions: int = 3, max_sessions: int = 12,
                   pilot_sessions: int = 4) -> dict[str, Any]:
    if repetitions != 3 or max_sessions != 12 or pilot_sessions != 4:
        raise ControllerError("Phase 3 plan is fixed at 3 pairs per domain and a 4-session pilot")
    root = workspace.expanduser().resolve()
    if not root.is_dir():
        raise ControllerError("Workspace is missing")
    scenarios = list(scenarios)
    if { _application(s) for s in scenarios } != {"blender", "web"}:
        raise ControllerError("Manifest requires exactly Blender and Web scenarios")
    entries: list[dict[str, Any]] = []
    for scenario in sorted(scenarios, key=lambda item: item["scenario_id"]):
        validate_scenario(scenario)
        application = _application(scenario)
        pair = _pair_id(scenario["scenario_id"])
        oracle = _oracle_spec(scenario)
        for repetition in range(1, repetitions + 1):
            for condition, profile in (("baseline", baseline_profile), ("optimized", optimized_profile)):
                run_id = f"{condition}-" + hashlib.sha256(
                    f"{scenario['scenario_id']}|{condition}|{repetition}".encode("utf-8")
                ).hexdigest()[:24]
                entries.append({
                    "application": application,
                    "scenario_id": scenario["scenario_id"],
                    "pair_id": pair,
                    "run_id": run_id,
                    "repetition": repetition,
                    "condition": condition,
                    "model": scenario["model"],
                    "prompt_sha256": _sha(scenario["prompt"]),
                    "expected_sha256": _sha(scenario["expected_exact"].strip()),
                    "workspace_root": str(root),
                    "profile": profile,
                    "expected_mcp_server": _expected_server(scenario, condition),
                    "expected_mcp_tools": _expected_mcp_tools(scenario, condition),
                    "oracle": oracle,
                })
    if max_sessions != MAX_SESSIONS or len(entries) != MAX_SESSIONS:
        raise ControllerError("Manifest session count does not equal the fixed budget")
    return {
        "schema": SCHEMA,
        "state": "READY_FOR_AB_PILOT",
        "model_sessions": len(entries),
        "max_authorized_sessions": MAX_SESSIONS,
        "pilot_sessions": pilot_sessions,
        "pilot_repetitions": [1],
        "no_automatic_retry": True,
        "workspace_root": str(root),
        "scenarios": entries,
        "execution": "PLAN_ONLY_NO_MODEL_EXECUTION",
    }


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise ControllerError("Invalid controller manifest")
    entries = manifest.get("scenarios")
    if not isinstance(entries, list) or len(entries) != MAX_SESSIONS:
        raise ControllerError("Manifest must contain exactly 12 planned sessions")
    seen: set[str] = set()
    pairs: dict[str, set[str]] = {}
    for item in entries:
        for key in ("run_id", "pair_id", "scenario_id", "workspace_root", "profile", "expected_mcp_server"):
            _safe_id(item[key], key) if key != "workspace_root" else None
        if item["run_id"] in seen:
            raise ControllerError("Duplicate run_id")
        seen.add(item["run_id"])
        pairs.setdefault(item["pair_id"], set()).add(item["condition"])
        if item["condition"] not in ("baseline", "optimized"):
            raise ControllerError("Invalid condition")
    if len(pairs) != 2 or any(arms != {"baseline", "optimized"} for arms in pairs.values()):
        raise ControllerError("Manifest does not contain complete pairs")
    return {"state": "READY_FOR_AB_PILOT", "sessions": len(entries), "pairs": len(pairs)}


def validate_batch_budget(manifest: dict[str, Any], batch: str, authorized_sessions: int) -> dict[str, Any]:
    """Validate an explicit batch authorization without starting a process."""
    batches = plan_batches(manifest)
    if batch not in ("pilot", "complement"):
        raise ControllerError("Unknown batch")
    requested = batches[batch]["sessions"]
    if type(authorized_sessions) is not int or authorized_sessions != requested:
        raise ControllerError("Batch authorization must exactly equal requested sessions")
    return {"state": "AUTHORIZED_FOR_PLANNING_ONLY", "batch": batch, "sessions": requested,
            "model_execution": "DISABLED"}


def _load_lifecycle(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value=json.loads(line)
            if isinstance(value, dict):
                events.append(value)
    return events


def _fixture_oracle(scenario: dict[str, Any], workspace: Path) -> dict[str, Any]:
    """Check deterministic fixture invariants without model or external writes."""
    oracle=_oracle_spec(scenario)
    if oracle["kind"] in ("web_local_page", "exact_text"):
        fixture=workspace/"fixtures"/"phase3"/"web"/"index.html"
        text=fixture.read_text(encoding="utf-8")
        required_refs=oracle.get("required_refs", [])
        missing=[value for value in (*required_refs, *oracle["required_text"]) if value not in text]
        return {"passed": not missing, "kind": oracle["kind"], "missing": missing}
    # The Blender oracle is a read-only contract for the disposable scene. The
    # live Blender probe remains an independent external evidence source.
    if oracle["kind"] == "blender_scene_json":
        expected = oracle["expected"]
        required = {"object_name", "object_type", "location", "material_names"}
        passed = isinstance(expected, dict) and set(expected) == required
    else:
        passed = bool(oracle["object_name"] and oracle["material_name"])
    return {"passed": passed, "kind": oracle["kind"], "independent_live_probe_required": True}


def _capture_failure_reason(evidence: Any) -> str:
    """Map capture evidence to a fixed internal failure reason code."""
    if _capture_certification_status(evidence) == "TIMEOUT":
        return "timeout"
    return "capture_failed"


def run_pilot(*, manifest: dict[str, Any], scenarios: Iterable[dict[str, Any]],
              workspace: Path, baseline_home: Path, optimized_home: Path,
              baseline_profile: str, optimized_profile: str,
              output: Path, authorized_sessions: int, codex_bin: str = "codex",
              timeout: int = 240) -> dict[str, Any]:
    """Execute exactly the authorized four-session pilot, fail closed."""
    validate_manifest(manifest)
    validate_batch_budget(manifest, "pilot", authorized_sessions)
    if authorized_sessions != 4:
        raise ControllerError("Pilot requires exactly four authorized sessions")
    scenario_map={item["scenario_id"]: item for item in scenarios}
    pilot_entries=[item for item in manifest["scenarios"] if item["repetition"] == 1]
    if len(pilot_entries) != 4:
        _write_budget_ledger(_budget_ledger_path(output), state="failed",
                             run_id="pilot", pair_id="pilot",
                             consumed_sessions=0, authorized_sessions=authorized_sessions,
                             error="Manifest pilot does not contain four sessions",
                             certification_status="BYPASS")
        raise ControllerError("Manifest pilot does not contain four sessions")
    root=workspace.expanduser().resolve(strict=True)
    manifest_root=Path(manifest.get("workspace_root", "")).expanduser().resolve()
    if manifest_root != root:
        raise ControllerError("Frozen manifest workspace differs from pilot workspace")
    output=output.expanduser().resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    records_dir=output.parent/(output.stem+"-records")
    records_dir.mkdir(parents=True,exist_ok=True)
    records=[]
    for entry in pilot_entries:
        scenario=scenario_map.get(entry["scenario_id"])
        if scenario is None:
            _write_budget_ledger(_budget_ledger_path(output), state="failed",
                                 run_id=entry.get("run_id", "pilot"),
                                 pair_id=entry.get("pair_id", "pilot"),
                                 consumed_sessions=len(records), authorized_sessions=authorized_sessions,
                                 error="Manifest scenario is not available",
                                 task_id=entry.get("scenario_id"),
                                 certification_status="BYPASS")
            raise ControllerError("Manifest scenario is not available")
        if (entry.get("model") != scenario["model"] or
            entry.get("prompt_sha256") != _sha(scenario["prompt"]) or
            entry.get("expected_sha256") != _sha(scenario["expected_exact"].strip()) or
            entry.get("expected_mcp_server") != _expected_server(scenario, entry["condition"])):
            _write_budget_ledger(_budget_ledger_path(output), state="failed",
                                 run_id=entry["run_id"], pair_id=entry["pair_id"],
                                 consumed_sessions=len(records), authorized_sessions=authorized_sessions,
                                 error="Manifest identity does not match the loaded scenario",
                                 task_id=entry["scenario_id"],
                                 certification_status="BYPASS")
            raise ControllerError("Manifest identity does not match the loaded scenario")
        if entry.get("expected_mcp_tools") != _expected_mcp_tools(scenario, entry["condition"]):
            _write_budget_ledger(_budget_ledger_path(output), state="failed",
                                 run_id=entry["run_id"], pair_id=entry["pair_id"],
                                 consumed_sessions=len(records), authorized_sessions=authorized_sessions,
                                 error="Manifest tool allowlist does not match the loaded scenario",
                                 task_id=entry["scenario_id"],
                                 certification_status="BYPASS")
            raise ControllerError("Manifest tool allowlist does not match the loaded scenario")
        home=baseline_home if entry["condition"]=="baseline" else optimized_home
        profile=baseline_profile if entry["condition"]=="baseline" else optimized_profile
        preflight=preflight_codex(scenario,condition=entry["condition"],workspace=root,
                                  codex_home=home,codex_bin=codex_bin,profile=profile)
        if preflight["state"]!="READY_FOR_BENCHMARK":
            _write_budget_ledger(_budget_ledger_path(output), state="failed",
                                 run_id=entry["run_id"], pair_id=entry["pair_id"],
                                 consumed_sessions=len(records), authorized_sessions=authorized_sessions,
                                 error="preflight_failed",
                                 task_id=entry["scenario_id"],
                                 certification_status="BYPASS")
            _write_terminal_record(_terminal_record_path(output, entry["run_id"], entry["pair_id"]),
                                   task_id=entry["scenario_id"],
                                   run_id=entry["run_id"], pair_id=entry["pair_id"],
                                   condition=entry["condition"], status="BYPASS",
                                   reason="preflight_failed")
            raise ControllerError("Preflight failed: "+";".join(preflight["errors"]))
        try:
            record=capture_codex(scenario,condition=entry["condition"],repetition=1,
                                 workspace=root,codex_home=home,codex_bin=codex_bin,
                                 profile=profile,timeout=timeout,
                                 run_id_override=entry["run_id"], pair_id_override=entry["pair_id"])
        except CodexCaptureError as exc:
            capture_status=_capture_certification_status(exc.evidence)
            capture_reason=_capture_failure_reason(exc.evidence)
            _write_budget_ledger(_budget_ledger_path(output), state="failed",
                                 run_id=entry["run_id"], pair_id=entry["pair_id"],
                                 consumed_sessions=len(records)+1, authorized_sessions=authorized_sessions,
                                 error=capture_reason,
                                 task_id=entry["scenario_id"],
                                 certification_status=capture_status)
            _write_terminal_record(_terminal_record_path(output, entry["run_id"], entry["pair_id"]),
                                   task_id=entry["scenario_id"],
                                   run_id=entry["run_id"], pair_id=entry["pair_id"],
                                   condition=entry["condition"],
                                   status=capture_status,
                                   reason=capture_reason)
            return {"schema":"pie-phase3-pilot-result-v1","state":"AB_PILOT_FAILED",
                    "authorization":{"maximum_sessions":authorized_sessions,
                                     "consumed_sessions":len(records)+1,
                                     "remaining_sessions_not_run":4-(len(records)+1),
                                     "complement_executed":False,"automatic_retry":False},
                    "manifest_state":manifest.get("state"),
                    "certification_status":_capture_certification_status(exc.evidence),
                    "task_id":entry["scenario_id"],
                    "ledger":str(_budget_ledger_path(output)),
                    "failed_execution":{"application":entry["application"],
                                        "condition":entry["condition"],
                                        "repetition":entry["repetition"],
                                        "run_id":entry["run_id"],"pair_id":entry["pair_id"],
                                        "task_id":entry["scenario_id"],
                                        "certification_status":_capture_certification_status(exc.evidence),
                                        "failure_code":_capture_failure_reason(exc.evidence),
                                        "evidence_available":bool(exc.evidence),
                                        "oracle":"not_evaluated",
                                        "lifecycle_correlation":"not_evaluated"},
                    "records":records}
        if record["run_id"]!=entry["run_id"] or record["pair_id"]!=entry["pair_id"]:
            _write_budget_ledger(_budget_ledger_path(output), state="failed",
                                 run_id=entry["run_id"], pair_id=entry["pair_id"],
                                 consumed_sessions=len(records)+1, authorized_sessions=authorized_sessions,
                                 error="identity_mismatch",
                                 task_id=entry["scenario_id"],
                                 certification_status="FAILED")
            _write_terminal_record(_terminal_record_path(output, entry["run_id"], entry["pair_id"]),
                                   task_id=entry["scenario_id"],
                                   run_id=entry["run_id"], pair_id=entry["pair_id"],
                                   condition=entry["condition"], status="FAILED",
                                   reason="identity_mismatch")
            raise ControllerError("Capture identity differs from frozen manifest")
        oracle=_fixture_oracle(scenario,root)
        if not oracle["passed"]:
            _write_budget_ledger(_budget_ledger_path(output), state="failed",
                                 run_id=entry["run_id"], pair_id=entry["pair_id"],
                                 consumed_sessions=len(records)+1, authorized_sessions=authorized_sessions,
                                 error="oracle_failed",
                                 task_id=entry["scenario_id"],
                                 certification_status="FAILED")
            _write_terminal_record(_terminal_record_path(output, entry["run_id"], entry["pair_id"]),
                                   task_id=entry["scenario_id"],
                                   run_id=entry["run_id"], pair_id=entry["pair_id"],
                                   condition=entry["condition"], status="FAILED",
                                   reason="oracle_failed")
            raise ControllerError("Independent fixture oracle failed")
        lifecycle=_load_lifecycle(root.parent/("."+root.name+"-pie-live-store")/"mcp-lifecycle.jsonl")
        route=audit_record_route(record,lifecycle)
        if route["decision"]!="VALID":
            _write_budget_ledger(_budget_ledger_path(output), state="failed",
                                 run_id=entry["run_id"], pair_id=entry["pair_id"],
                                 consumed_sessions=len(records)+1, authorized_sessions=authorized_sessions,
                                 error="route_evidence_failed",
                                 task_id=entry["scenario_id"],
                                 certification_status="FAILED")
            _write_terminal_record(_terminal_record_path(output, entry["run_id"], entry["pair_id"]),
                                   task_id=entry["scenario_id"],
                                   run_id=entry["run_id"], pair_id=entry["pair_id"],
                                   condition=entry["condition"], status="FAILED",
                                   reason="route_evidence_failed")
            raise ControllerError("Route evidence failed: "+route["reason"])
        destination=records_dir/(entry["condition"]+"-"+entry["application"]+"-r1.json")
        destination.write_text(json.dumps(record,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        import_provider_record(root,record,app=entry["application"],task_id=entry["scenario_id"])
        records.append({"manifest":entry,"record":str(destination),"oracle":oracle,"route":route})
    return {"schema":"pie-phase3-pilot-result-v1","state":"AB_PILOT_PASSED",
            "sessions_consumed":len(records),"pairs_accepted":2,"records":records,
            "automatic_retry":False,"complement_executed":False}


def plan_batches(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest)
    entries = manifest["scenarios"]
    pilot = [item for item in entries if item["repetition"] == 1]
    remainder = [item for item in entries if item["repetition"] != 1]
    if len(pilot) != 4 or len(remainder) != 8:
        raise ControllerError("Invalid 4+8 batch split")
    return {
        "state": "READY_FOR_AB_PILOT",
        "pilot": {"sessions": 4, "authorization_required": True, "entries": pilot},
        "complement": {"sessions": 8, "authorization_required": True, "entries": remainder},
        "automatic_execution": False,
        "automatic_retry": False,
    }


def build_frozen_resume_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    """Expand the quota-blocked manifest 106 into an offline execution plan."""
    if not isinstance(manifest, dict) or manifest.get("schema") != "pie-phase3-frozen-ab-manifest-v1":
        raise ControllerError("Invalid frozen A/B manifest")
    applications=manifest.get("applications")
    if not isinstance(applications, dict) or set(applications) != {"blender", "web"}:
        raise ControllerError("Frozen manifest must contain Blender and Web")
    entries=[]
    seen=set()
    sequence=0
    for application in ("blender", "web"):
        item=applications[application]
        scenario=item.get("scenario")
        pair_id=item.get("pair_id")
        orders=item.get("orders")
        if not isinstance(scenario,str) or not isinstance(pair_id,str) or not isinstance(orders,list):
            raise ControllerError("Incomplete frozen manifest application")
        _safe_id(pair_id,"pair_id")
        for order in orders:
            repetition=order.get("repetition") if isinstance(order,dict) else None
            conditions=order.get("conditions") if isinstance(order,dict) else None
            if type(repetition) is not int or repetition not in (1,2,3) or conditions not in (["baseline","optimized"],["optimized","baseline"]):
                raise ControllerError("Invalid frozen manifest order")
            for condition in conditions:
                sequence+=1
                run_id=f"{condition}-{application}-r{repetition}-{uuid.uuid4().hex[:12]}"
                if run_id in seen:
                    raise ControllerError("Duplicate resume run_id")
                seen.add(run_id)
                entries.append({"sequence":sequence,"application":application,"scenario":scenario,
                                "pair_id":pair_id,"run_id":run_id,"repetition":repetition,
                                "condition":condition})
    if len(entries) != 10:
        raise ControllerError("Frozen resume plan must contain exactly 10 sessions")
    return {"schema":"pie-phase3-frozen-ab-resume-plan-v1","state":"READY_FOR_PAID_AB",
            "model_execution":"DISABLED","automatic_retry":False,"sessions":entries}


def audit_record_route(record: dict[str, Any], lifecycle: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Audit one provider record against exact lifecycle IDs, never timestamps."""
    try:
        _record(record)
    except (ValueError, KeyError) as exc:
        return {"decision": "INSUFFICIENT_EVIDENCE", "reason": str(exc)}
    matching = [event for event in lifecycle if event.get("run_id") == record["run_id"]
                and event.get("pair_id") == record["pair_id"]]
    expected = record["expected_mcp_server"]
    calls = [event for event in matching if event.get("event") == "MCP_TOOL_CALL_RECEIVED"]
    if record["condition"] == "optimized":
        if not calls or any(event.get("gateway_server") != expected for event in calls):
            return {"decision": "INSUFFICIENT_EVIDENCE", "reason": "No exact optimized gateway correlation"}
    if not record["oracle_pass"]:
        return {"decision": "INVALID", "reason": "Oracle failed"}
    return {"decision": "VALID", "reason": "Provider, oracle and exact route evidence matched"}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sanitize_id_component(value: str) -> str:
    """Defensively sanitize an identifier for use in a filename."""
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", str(value))
    return sanitized[:128] or "unknown"


def _terminal_record_path(output: Path, run_id: str, pair_id: str) -> Path:
    """Per-attempt terminal record path so each attempt keeps its own file."""
    return output.parent / (output.stem + "-terminal-"
                            + _sanitize_id_component(run_id) + "-"
                            + _sanitize_id_component(pair_id) + ".json")


def _write_terminal_record(path: Path, *, task_id: str | None, run_id: str,
                           pair_id: str, condition: str, status: str,
                           reason: str) -> None:
    """Persist a sanitized terminal record for a failed session.

    The record intentionally contains only identifiers and a bounded reason
    string: no credentials, prompts, provider responses, or token usage.
    Tokens, latency and usage remain null because failures carry no usage.
    """
    _write_json(path, {
        "schema": "pie-phase3-terminal-record-v1",
        "task_id": task_id,
        "run_id": run_id,
        "pair_id": pair_id,
        "condition": condition,
        "status": status,
        "reason": str(reason)[:2000],
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tokens": None,
        "latency_ms": None,
        "usage": None,
    })


def _budget_ledger_path(output: Path) -> Path:
    return output.parent / (output.stem + "-budget-ledger.json")


def _write_budget_ledger(path: Path, *, state: str, run_id: str, pair_id: str,
                         consumed_sessions: int, authorized_sessions: int,
                         error: str | None = None,
                         task_id: str | None = None,
                         certification_status: str | None = None) -> None:
    value = {
        "schema": "pie-phase3-budget-ledger-v1",
        "state": state,
        "authorized_sessions": authorized_sessions,
        "consumed_sessions": consumed_sessions,
        "remaining_sessions": authorized_sessions - consumed_sessions,
        "run_id": run_id,
        "pair_id": pair_id,
        "automatic_retry": False,
    }
    if task_id:
        value["task_id"] = task_id
    if certification_status:
        value["certification_status"] = certification_status
    if error:
        value["error"] = str(error)[:2000]
    _write_json(path, value)


def _capture_certification_status(evidence: Any) -> str:
    """Map capture evidence to an explicit certification status."""
    if isinstance(evidence, dict):
        if evidence.get("certification_status") == "TIMEOUT":
            return "TIMEOUT"
        if evidence.get("certification_status") == "EXECUTOR_UNAVAILABLE":
            return "BYPASS"
    return "FAILED"


def run_single(*, scenario: dict[str, Any], application: str, condition: str,
               workspace: Path, baseline_home: Path, optimized_home: Path,
               baseline_profile: str, optimized_profile: str, output: Path,
               authorized_sessions: int = 1, codex_bin: str = "codex",
               timeout: int = 240, pair_id_override: str | None = None,
               run_id_override: str | None = None, repetition: int = 1) -> dict[str, Any]:
    """Run one reusable certification arm with a persistent pre-spawn ledger."""
    validate_scenario(scenario)
    if application not in ("blender", "web") or condition not in CONDITIONS:
        raise ControllerError("Invalid single-run domain or condition")
    if _application(scenario) != application:
        raise ControllerError("Scenario domain does not match requested application")
    if authorized_sessions != 1:
        raise ControllerError("Single run requires exactly one authorized session")
    if type(repetition) is not int or not 1 <= repetition <= 3:
        raise ControllerError("Repetition must be 1, 2 or 3")
    root = workspace.expanduser().resolve(strict=True)
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    run_id = run_id_override or (f"{condition}-" + uuid.uuid4().hex[:24])
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", run_id):
        raise ControllerError("Invalid run_id override")
    pair_id = pair_id_override or ("pair-" + uuid.uuid4().hex[:24])
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", pair_id):
        raise ControllerError("Invalid pair_id override")
    valid_state = f"{condition.upper()}_{application.upper()}_VALID"
    failed_state = f"{condition.upper()}_{application.upper()}_FAILED"
    ledger = _budget_ledger_path(output)
    _write_budget_ledger(ledger, state="reserved", run_id=run_id, pair_id=pair_id,
                         consumed_sessions=0, authorized_sessions=authorized_sessions)
    home = baseline_home if condition == "baseline" else optimized_home
    profile = baseline_profile if condition == "baseline" else optimized_profile
    preflight = preflight_codex(scenario, condition=condition, workspace=root,
                                codex_home=home, codex_bin=codex_bin, profile=profile)
    if preflight["state"] != "READY_FOR_BENCHMARK":
        _write_budget_ledger(ledger, state="preflight_failed", run_id=run_id, pair_id=pair_id,
                             consumed_sessions=0, authorized_sessions=authorized_sessions,
                             error="preflight_failed",
                             task_id=scenario.get("scenario_id"),
                             certification_status="BYPASS")
        _write_terminal_record(_terminal_record_path(output, run_id, pair_id),
                               task_id=scenario.get("scenario_id"),
                               run_id=run_id, pair_id=pair_id,
                               condition=condition, status="BYPASS",
                               reason="preflight_failed")
        return {"schema": "pie-phase3-single-result-v1", "state": failed_state,
                "run_id": run_id, "pair_id": pair_id, "ledger": str(ledger),
                "preflight": preflight, "quota_consumed": False,
                "automatic_retry": False, "task_id": scenario.get("scenario_id"),
                "certification_status": "BYPASS"}
    # Reserve the one authorized session before the model process is spawned.
    _write_budget_ledger(ledger, state="started", run_id=run_id, pair_id=pair_id,
                         consumed_sessions=1, authorized_sessions=authorized_sessions)
    try:
        record = capture_codex(
            scenario, condition=condition, repetition=repetition, workspace=root,
            codex_home=home, codex_bin=codex_bin, profile=profile, timeout=timeout,
            run_id_override=run_id, pair_id_override=pair_id)
    except RuntimeError as exc:
        status = _capture_certification_status(getattr(exc, "evidence", None))
        _write_budget_ledger(ledger, state="failed", run_id=run_id, pair_id=pair_id,
                             consumed_sessions=1, authorized_sessions=authorized_sessions,
                             error=_capture_failure_reason(getattr(exc, "evidence", None)),
                             task_id=scenario.get("scenario_id"),
                             certification_status=status)
        _write_terminal_record(_terminal_record_path(output, run_id, pair_id),
                               task_id=scenario.get("scenario_id"),
                               run_id=run_id, pair_id=pair_id,
                               condition=condition, status=status,
                               reason=_capture_failure_reason(getattr(exc, "evidence", None)))
        return {"schema": "pie-phase3-single-result-v1", "state": failed_state,
                "run_id": run_id, "pair_id": pair_id, "ledger": str(ledger),
                "quota_consumed": True, "automatic_retry": False,
                "failure_code": _capture_failure_reason(getattr(exc, "evidence", None)),
                "evidence_available": bool(getattr(exc, "evidence", None)),
                "task_id": scenario.get("scenario_id"),
                "certification_status": status}
    if record["run_id"] != run_id or record["pair_id"] != pair_id:
        _write_budget_ledger(ledger, state="failed", run_id=run_id, pair_id=pair_id,
                             consumed_sessions=1, authorized_sessions=authorized_sessions,
                             error="identity_mismatch",
                             task_id=scenario.get("scenario_id"),
                             certification_status="FAILED")
        _write_terminal_record(_terminal_record_path(output, run_id, pair_id),
                               task_id=scenario.get("scenario_id"),
                               run_id=run_id, pair_id=pair_id,
                               condition=condition, status="FAILED",
                               reason="identity_mismatch")
        raise ControllerError("Capture identity differs from generated single-run identity")
    oracle = _fixture_oracle(scenario, root)
    if not oracle["passed"]:
        _write_budget_ledger(ledger, state="failed", run_id=run_id, pair_id=pair_id,
                             consumed_sessions=1, authorized_sessions=authorized_sessions,
                             error="oracle_failed",
                             task_id=scenario.get("scenario_id"),
                             certification_status="FAILED")
        _write_terminal_record(_terminal_record_path(output, run_id, pair_id),
                               task_id=scenario.get("scenario_id"),
                               run_id=run_id, pair_id=pair_id,
                               condition=condition, status="FAILED",
                               reason="oracle_failed")
        return {"schema": "pie-phase3-single-result-v1", "state": failed_state,
                "run_id": run_id, "pair_id": pair_id, "ledger": str(ledger),
                "quota_consumed": True, "automatic_retry": False, "oracle": oracle,
                "task_id": scenario.get("scenario_id"), "certification_status": "FAILED"}
    lifecycle = _load_lifecycle(root.parent / ("." + root.name + "-pie-live-store") / "mcp-lifecycle.jsonl")
    route = audit_record_route(record, lifecycle)
    if route["decision"] != "VALID":
        _write_budget_ledger(ledger, state="failed", run_id=run_id, pair_id=pair_id,
                             consumed_sessions=1, authorized_sessions=authorized_sessions,
                             error="route_evidence_failed",
                             task_id=scenario.get("scenario_id"),
                             certification_status="FAILED")
        _write_terminal_record(_terminal_record_path(output, run_id, pair_id),
                               task_id=scenario.get("scenario_id"),
                               run_id=run_id, pair_id=pair_id,
                               condition=condition, status="FAILED",
                               reason="route_evidence_failed")
        return {"schema": "pie-phase3-single-result-v1", "state": failed_state,
                "run_id": run_id, "pair_id": pair_id, "ledger": str(ledger),
                "quota_consumed": True, "automatic_retry": False,
                "record": record, "oracle": oracle, "route": route,
                "task_id": scenario.get("scenario_id"), "certification_status": "FAILED"}
    destination = output.parent / (output.stem + "-record.json")
    _write_json(destination, record)
    import_provider_record(root, record, app=application, task_id=scenario["scenario_id"])
    _write_budget_ledger(ledger, state="completed", run_id=run_id, pair_id=pair_id,
                         consumed_sessions=1, authorized_sessions=authorized_sessions)
    return {"schema": "pie-phase3-single-result-v1", "state": valid_state,
            "run_id": run_id, "pair_id": pair_id, "ledger": str(ledger),
            "record": str(destination), "oracle": oracle, "route": route,
            "quota_consumed": True, "automatic_retry": False}


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Offline PIE Phase 3 certification controller")
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--workspace", type=Path, required=True)
    plan.add_argument("--baseline-profile", required=True)
    plan.add_argument("--optimized-profile", required=True)
    plan.add_argument("--scenario", action="append", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--record", action="append", type=Path, required=True)
    audit.add_argument("--lifecycle", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    pre = sub.add_parser("preflight")
    pre.add_argument("--scenario", action="append", type=Path, required=True)
    pre.add_argument("--workspace", type=Path, required=True)
    pre.add_argument("--baseline-home", type=Path, required=True)
    pre.add_argument("--optimized-home", type=Path, required=True)
    pre.add_argument("--baseline-profile", required=True)
    pre.add_argument("--optimized-profile", required=True)
    pre.add_argument("--output", type=Path, required=True)
    pre.add_argument("--codex-bin", default="codex")
    pilot = sub.add_parser("pilot")
    pilot.add_argument("--manifest", type=Path, required=True)
    pilot.add_argument("--scenario", action="append", type=Path, required=True)
    pilot.add_argument("--workspace", type=Path, required=True)
    pilot.add_argument("--baseline-home", type=Path, required=True)
    pilot.add_argument("--optimized-home", type=Path, required=True)
    pilot.add_argument("--baseline-profile", required=True)
    pilot.add_argument("--optimized-profile", required=True)
    pilot.add_argument("--authorized-sessions", type=int, required=True)
    pilot.add_argument("--output", type=Path, required=True)
    pilot.add_argument("--codex-bin", default="codex")
    pilot.add_argument("--timeout", type=int, default=240)
    single = sub.add_parser("single")
    single.add_argument("--scenario", type=Path, required=True)
    single.add_argument("--application", choices=("blender", "web"), required=True)
    single.add_argument("--condition", choices=("baseline", "optimized"), required=True)
    single.add_argument("--workspace", type=Path, required=True)
    single.add_argument("--baseline-home", type=Path, required=True)
    single.add_argument("--optimized-home", type=Path, required=True)
    single.add_argument("--baseline-profile", required=True)
    single.add_argument("--optimized-profile", required=True)
    single.add_argument("--output", type=Path, required=True)
    single.add_argument("--repetition", type=int, default=1)
    single.add_argument("--pair-id", default=None)
    single.add_argument("--run-id", default=None)
    single.add_argument("--codex-bin", default="codex")
    single.add_argument("--timeout", type=int, default=240)
    resume = sub.add_parser("resume-plan")
    resume.add_argument("--manifest", type=Path, required=True)
    resume.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            scenarios = [load_scenario(path) for path in args.scenario]
            manifest = build_manifest(scenarios=scenarios, workspace=args.workspace,
                                      baseline_profile=args.baseline_profile,
                                      optimized_profile=args.optimized_profile)
            result = {"manifest": manifest, "batches": plan_batches(manifest)}
        elif args.action == "audit":
            lifecycle = [json.loads(line) for line in args.lifecycle.read_text(encoding="utf-8").splitlines() if line.strip()]
            result = {"schema": "pie-phase3-evidence-audit-v1", "decisions": []}
            for path in args.record:
                record = json.loads(path.read_text(encoding="utf-8"))
                result["decisions"].append({"record": path.name, **audit_record_route(record, lifecycle)})
            result["state"] = "EVIDENCE_CERTIFIED" if result["decisions"] and all(
                item["decision"] == "VALID" for item in result["decisions"]
            ) else "BLOCKED_WITH_EVIDENCE"
        elif args.action == "preflight":
            scenarios = [load_scenario(path) for path in args.scenario]
            rows=[]
            for scenario in scenarios:
                for condition, home, profile in (("baseline",args.baseline_home,args.baseline_profile),
                                                  ("optimized",args.optimized_home,args.optimized_profile)):
                    result=preflight_codex(scenario,condition=condition,workspace=args.workspace,
                                           codex_home=home,codex_bin=args.codex_bin,profile=profile)
                    rows.append({"scenario_id":scenario["scenario_id"],"condition":condition,**result})
            result={"schema":"pie-phase3-preflight-v1","state":"READY_FOR_BENCHMARK" if all(
                row["state"]=="READY_FOR_BENCHMARK" for row in rows) else "BLOCKED",
                    "model_started":False,"quota_consumed":False,"arms":rows}
        elif args.action == "single":
            scenario = load_scenario(args.scenario)
            result = run_single(
                scenario=scenario, application=args.application, condition=args.condition,
                workspace=args.workspace, baseline_home=args.baseline_home,
                optimized_home=args.optimized_home,
                baseline_profile=args.baseline_profile, optimized_profile=args.optimized_profile,
                output=args.output, codex_bin=args.codex_bin, timeout=args.timeout,
                pair_id_override=args.pair_id, run_id_override=args.run_id,
                repetition=args.repetition)
        elif args.action == "resume-plan":
            document=json.loads(args.manifest.read_text(encoding="utf-8"))
            result=build_frozen_resume_plan(document)
            _write_json(args.output,result)
        else:
            scenarios = [load_scenario(path) for path in args.scenario]
            manifest_document = json.loads(args.manifest.read_text(encoding="utf-8"))
            manifest = manifest_document.get("manifest", manifest_document)
            result = run_pilot(manifest=manifest,scenarios=scenarios,
                               workspace=args.workspace,baseline_home=args.baseline_home,
                               optimized_home=args.optimized_home,
                               baseline_profile=args.baseline_profile,
                               optimized_profile=args.optimized_profile,
                               output=args.output,codex_bin=args.codex_bin,
                               authorized_sessions=args.authorized_sessions,
                               timeout=args.timeout)
        _write_json(args.output, result)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if (args.action in ("plan", "resume-plan") or result.get("state") in (
            "EVIDENCE_CERTIFIED", "AB_PILOT_PASSED", "BASELINE_BLENDER_VALID",
            "OPTIMIZED_BLENDER_VALID", "BASELINE_WEB_VALID", "OPTIMIZED_WEB_VALID",
            "READY_FOR_BENCHMARK")) else 2
    except (ControllerError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"state": "BLOCKED_WITH_EVIDENCE", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

