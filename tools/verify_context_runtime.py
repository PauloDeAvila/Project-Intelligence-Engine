"""Run a network-free six-pillar Context Runtime homologation check.

The verifier uses synthetic provider evidence only to exercise the evaluator's
contract. It never turns that fixture into external token certification.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import tempfile
from typing import Any

from pie.certification.regression import RunEvidence
from pie.interfaces.mcp_server import dispatch
from pie.runtime import ContextRuntime, MeasuredCandidate, OperationSpec
from pie.storage.database import connect


def _evidence(condition: str) -> RunEvidence:
    return RunEvidence(
        pair_id="synthetic-runtime-pair",
        scenario_id="synthetic-runtime-scenario",
        application="web",
        condition=condition,
        model="synthetic-provider-fixture",
        prompt_sha256="synthetic-prompt-sha",
        configuration_sha256="synthetic-config-sha",
        provider_usage_status="available",
        input_tokens=100 if condition == "baseline" else 80,
        cached_input_tokens=20,
        output_tokens=10,
        latency_ms=5.0,
        mcp_calls=1,
        oracle_pass=True,
        route_verified=True,
    )


def _valid_count(value: Any) -> bool:
    """Non-negative integers only; booleans are never token counts."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _host_allowed(host: Any) -> bool:
    """Allow loopback hosts (localhost/127.0.0.1/::1) or anything HTTPS-only.

    The evidence records the gateway hostname; HTTPS is accepted without
    resolution so evidence from a real provider is never rejected for being
    a name this machine cannot resolve.
    """
    if not isinstance(host, str) or not host:
        return False
    name = host.strip("[]").lower()
    if name in ("localhost", "127.0.0.1", "::1", "[::1]"):
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def _validate_external_evidence(payload: Any) -> dict[str, Any]:
    """Fail-closed validation of a pie_real_repo_lab summary.json.

    Returns the accepted evidence block, or raises ValueError with a reason.
    No prompt text, credential, or other document field is ever read.
    """
    if not isinstance(payload, dict):
        raise ValueError("external evidence must be a JSON object")
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("external evidence 'results' must be a non-empty array")
    models = {entry.get("model") for entry in results}
    if len(models) != 1 or None in models:
        raise ValueError("external evidence must contain exactly one model")
    model = models.pop()
    hosts = {entry.get("host") for entry in results}
    if len(hosts) != 1:
        raise ValueError("external evidence must contain exactly one host")
    host = hosts.pop()
    schemes = {entry.get("scheme") for entry in results}
    if len(schemes) != 1:
        raise ValueError("external evidence must contain exactly one scheme")
    scheme = schemes.pop()

    def entry_for(mode: str) -> dict[str, Any]:
        matching = [e for e in results if e.get("mode") == mode]
        if len(matching) != 1:
            raise ValueError(
                f"external evidence must contain exactly one '{mode}' entry"
            )
        entry = matching[0]
        if not isinstance(entry, dict):
            raise ValueError(f"external evidence '{mode}' entry must be an object")
        return entry

    baseline = entry_for("baseline")
    pie = entry_for("pie")
    for entry in (baseline, pie):
        if entry.get("provider_usage_status") != "ok":
            raise ValueError(
                "external evidence requires provider_usage_status='ok' for both"
                " baseline and pie entries"
            )
        for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if not _valid_count(entry.get(field)):
                raise ValueError(
                    f"external evidence field '{field}' must be a non-negative integer"
                )
        for field in ("cached_input_tokens", "uncached_input_tokens"):
            if field in entry and not _valid_count(entry.get(field)):
                raise ValueError(
                    f"external evidence field '{field}' must be a non-negative integer"
                )
        if "cached_input_tokens" in entry and \
                entry["cached_input_tokens"] > entry["prompt_tokens"]:
            raise ValueError(
                "external evidence cached_input_tokens cannot exceed prompt_tokens"
            )
        if "uncached_input_tokens" in entry and \
                entry["uncached_input_tokens"] > entry["prompt_tokens"]:
            raise ValueError(
                "external evidence uncached_input_tokens cannot exceed prompt_tokens"
            )
        if "cached_input_tokens" in entry and "uncached_input_tokens" in entry and \
                entry["cached_input_tokens"] + entry["uncached_input_tokens"] != \
                entry["prompt_tokens"]:
            raise ValueError(
                "external evidence cached_input_tokens plus uncached_input_tokens"
                " must equal prompt_tokens"
            )
        if not _valid_count(entry.get("exact_correct")):
            raise ValueError(
                "external evidence field 'exact_correct' must be a non-negative integer"
            )
        if not _valid_count(entry.get("successful")):
            raise ValueError(
                "external evidence field 'successful' must be a non-negative integer"
            )
        if entry.get("successful") <= 0:
            raise ValueError("external evidence entries must have successful calls")
        if entry.get("exact_correct") > entry.get("successful"):
            raise ValueError("external evidence exact_correct cannot exceed successful")
    if scheme == "https":
        pass
    elif scheme == "http":
        if not _host_allowed(host):
            raise ValueError(
                "external evidence collected over HTTP must come from a loopback"
                " host (localhost/127.0.0.1/::1)"
            )
    else:
        raise ValueError(
            "external evidence must record a scheme of 'https' or 'http'"
        )
    return {"model": model, "host": host, "scheme": scheme,
            "baseline": baseline, "pie": pie}


def _external_block(evidence: dict[str, Any]) -> dict[str, Any]:
    """Compute the reported external usage block from real token counts."""
    baseline = evidence["baseline"]
    pie = evidence["pie"]
    pair_count = min(baseline["successful"], pie["successful"])
    baseline_tokens = baseline["prompt_tokens"] + baseline["completion_tokens"]
    pie_tokens = pie["prompt_tokens"] + pie["completion_tokens"]

    def savings_percent(base_value: Any, pie_value: Any, base_total: Any,
                        pie_total: Any) -> float | None:
        """Percent savings from real tokens only; None when not computable."""
        if not (_valid_count(base_value) and _valid_count(pie_value)):
            return None
        if base_total == 0:
            return None
        return round(100 * (base_value - pie_value) / base_total, 3)

    input_savings_percent = savings_percent(
        baseline.get("prompt_tokens"), pie.get("prompt_tokens"),
        baseline["prompt_tokens"], pie["prompt_tokens"],
    )
    total_savings_percent = savings_percent(
        baseline_tokens, pie_tokens, baseline_tokens, pie_tokens,
    )
    correct = min(baseline["exact_correct"], pie["exact_correct"])
    block: dict[str, Any] = {
        "available": True,
        "status": "available",
        "external_evidence_status": "PILOT_VALID",
        "model": evidence["model"],
        "host": evidence["host"],
        "scheme": evidence["scheme"],
        "pair_count": pair_count,
        "correct_pairs": correct,
        "baseline_tokens": baseline_tokens,
        "pie_tokens": pie_tokens,
        "input_savings_percent": input_savings_percent,
        "total_savings_percent": total_savings_percent,
        "note": "Token counts come from real provider usage reported by"
                " pie_real_repo_lab; no prompts or credentials were read.",
    }
    for side in ("baseline", "pie"):
        for field in ("cached_input_tokens", "uncached_input_tokens"):
            block[f"{side}_{field}"] = evidence[side].get(field)
    return block


def verify(external_evidence: Path | None = None) -> dict[str, Any]:
    pillars: dict[str, dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="pie-context-runtime-") as directory:
        root = Path(directory)
        storage = root / ".pie"
        storage.mkdir()
        connect(storage / "index.sqlite3").close()
        external: dict[str, Any] | None = None
        if external_evidence is not None:
            try:
                payload = json.loads(
                    external_evidence.read_text(encoding="utf-8-sig")
                )
                external = _external_block(_validate_external_evidence(payload))
            except Exception as error:
                return {
                    "schema": "pie-context-runtime-verifier-v1",
                    "status": "FAIL_LOCAL",
                    "local_validation": False,
                    "certification": "NOT_CERTIFIED",
                    "external_evidence_path": str(external_evidence),
                    "external_evidence_status": "INVALID",
                    "failure_code": type(error).__name__,
                    "failure_reason": str(error),
                    "pillars": {},
                    "external_provider_usage": "unavailable",
                }
        try:
            with ContextRuntime(
                root,
                journal_path=Path(".pie") / "runtime.sqlite3",
                graph_path=Path(".pie") / "context-runtime-graph.sqlite3",
            ) as runtime:
                task = runtime.start("synthetic runtime verification")
                runtime.record(task["task_id"], "note", "fixture created")
                runtime.checkpoint_agent(
                    task["task_id"], "agent-a", {"fact": {"value": 7}}
                )
                compiled = runtime.compile_checkpoint(
                    task["task_id"], [["fact", "value"]]
                )
                if compiled.data != {"fact": {"value": 7}}:
                    raise AssertionError("context compiler returned unexpected data")
                pillars["state_engine"] = {"status": "PASS"}
                pillars["context_compiler"] = {"status": "PASS"}

                runtime.register_operation(
                    OperationSpec("read_value", lambda args: {"value": args["value"]})
                )
                first = runtime.execute_local("read_value", {"value": 7})
                second = runtime.execute_local("read_value", {"value": 7})
                if first["status"] != "SUCCESS" or second["status"] != "REPLAYED":
                    raise AssertionError("local execution replay contract failed")
                pillars["local_execution_engine"] = {"status": "PASS"}

                selected = runtime.choose([
                    MeasuredCandidate("wide", "available", cost_usd=0.02),
                    MeasuredCandidate("compact", "available", cost_usd=0.01),
                ], objective="cost")
                if selected["representation"] != "compact":
                    raise AssertionError("adaptive cost selection failed")
                pillars["adaptive_runtime"] = {"status": "PASS"}

                runtime.add_graph_node(task["task_id"], "observe", "step")
                runtime.add_graph_node(task["task_id"], "verify", "step")
                runtime.add_graph_edge(task["task_id"], "observe", "verify", "depends")
                if runtime.graph_order(task["task_id"])["order"] != ["observe", "verify"]:
                    raise AssertionError("task graph ordering failed")
                references = runtime.memory.references(task["task_id"], "agent-a")
                if references["state"] != "FOUND":
                    raise AssertionError("agent memory reference failed")
                pillars["multi_agent_memory"] = {"status": "PASS"}

                synthetic = runtime.evaluate_suite([
                    (_evidence("baseline"), _evidence("optimized"))
                ])
                if synthetic["status"] != "CERTIFIED":
                    raise AssertionError("synthetic certification evaluator failed")
                pillars["continuous_certification"] = {
                    "status": "PASS_SYNTHETIC_ONLY"
                }

            response = dispatch({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "pie_context_runtime",
                    "arguments": {
                        "operation": "graph_snapshot",
                        "task_id": task["task_id"],
                    },
                },
            }, root)
            if response.get("result", {}).get("isError"):
                raise AssertionError("MCP runtime projection returned an error")
            pillars["mcp_projection"] = {"status": "PASS"}
        except Exception as error:
            return {
                "schema": "pie-context-runtime-verifier-v1",
                "status": "FAIL_LOCAL",
                "local_validation": False,
                "certification": "NOT_CERTIFIED",
                "failure_code": type(error).__name__,
                "pillars": pillars,
                "external_provider_usage": "unavailable",
            }

    result: dict[str, Any] = {
        "schema": "pie-context-runtime-verifier-v1",
        "status": "PASS_LOCAL",
        "local_validation": True,
        "certification": "NOT_CERTIFIED",
        "external_provider_usage": "unavailable",
        "synthetic_provider_evidence": True,
        "pillars": pillars,
        "note": "Synthetic evaluator evidence is not external provider usage.",
    }
    if external is not None:
        result["external_provider_usage"] = external
        if external["pair_count"] < 3:
            result["certification"] = "NOT_CERTIFIED"
            result["certification_note"] = (
                "External evidence shows "
                f"{external['pair_count']} pair(s); at least 3 are required"
                " for pilot certification, so the result stays NOT_CERTIFIED."
            )
        else:
            result["certification"] = "NOT_CERTIFIED"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--external-evidence",
        type=Path,
        help="Path to a pie_real_repo_lab summary.json with real provider usage",
    )
    args = parser.parse_args()
    result = verify(args.external_evidence)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    print(encoded)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS_LOCAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
