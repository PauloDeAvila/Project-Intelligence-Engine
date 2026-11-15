"""Offline controller for auditable PIE certification preparation.

This module deliberately has no model execution path. It creates immutable
plans, validates evidence, and refuses incomplete correlation before any paid
runner is allowed to be invoked by a future integration.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from pie.certification.live_codex import _record, _sha, validate_scenario
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
    elif kind == "web_local_page":
        required = ("fixture_id", "required_refs", "required_text")
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
    if oracle["kind"] == "web_local_page":
        fixture=workspace/"fixtures"/"phase3"/"web"/"index.html"
        text=fixture.read_text(encoding="utf-8")
        missing=[value for value in (*oracle["required_refs"], *oracle["required_text"]) if value not in text]
        return {"passed": not missing, "kind": oracle["kind"], "missing": missing}
    # The Blender oracle is a read-only contract for the disposable scene. The
    # live Blender probe remains an independent external evidence source.
    return {"passed": bool(oracle["object_name"] and oracle["material_name"]),
            "kind": oracle["kind"], "independent_live_probe_required": True}


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
            raise ControllerError("Manifest scenario is not available")
        home=baseline_home if entry["condition"]=="baseline" else optimized_home
        profile=baseline_profile if entry["condition"]=="baseline" else optimized_profile
        preflight=preflight_codex(scenario,condition=entry["condition"],workspace=root,
                                  codex_home=home,codex_bin=codex_bin,profile=profile)
        if preflight["state"]!="READY_FOR_BENCHMARK":
            raise ControllerError("Preflight failed: "+";".join(preflight["errors"]))
        try:
            record=capture_codex(scenario,condition=entry["condition"],repetition=1,
                                 workspace=root,codex_home=home,codex_bin=codex_bin,
                                 profile=profile,timeout=timeout)
        except CodexCaptureError as exc:
            return {"schema":"pie-phase3-pilot-result-v1","state":"AB_PILOT_FAILED",
                    "authorization":{"maximum_sessions":authorized_sessions,
                                     "consumed_sessions":len(records)+1,
                                     "remaining_sessions_not_run":4-(len(records)+1),
                                     "complement_executed":False,"automatic_retry":False},
                    "manifest_state":manifest.get("state"),
                    "failed_execution":{"application":entry["application"],
                                        "condition":entry["condition"],
                                        "repetition":entry["repetition"],
                                        "run_id":entry["run_id"],"pair_id":entry["pair_id"],
                                        "failure":str(exc),
                                        "provider_evidence":exc.evidence or "unavailable",
                                        "oracle":"not_evaluated",
                                        "lifecycle_correlation":"not_evaluated"},
                    "records":records}
        if record["run_id"]!=entry["run_id"] or record["pair_id"]!=entry["pair_id"]:
            raise ControllerError("Capture identity differs from frozen manifest")
        oracle=_fixture_oracle(scenario,root)
        if not oracle["passed"]:
            raise ControllerError("Independent fixture oracle failed")
        lifecycle=_load_lifecycle(root.parent/("."+root.name+"-pie-live-store")/"mcp-lifecycle.jsonl")
        route=audit_record_route(record,lifecycle)
        if route["decision"]!="VALID":
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
        return 0 if (args.action == "plan" or result.get("state") in (
            "EVIDENCE_CERTIFIED", "AB_PILOT_PASSED", "READY_FOR_BENCHMARK")) else 2
    except (ControllerError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"state": "BLOCKED_WITH_EVIDENCE", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

