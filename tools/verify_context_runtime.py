"""Run a network-free six-pillar Context Runtime homologation check.

The verifier uses synthetic provider evidence only to exercise the evaluator's
contract. It never turns that fixture into external token certification.
"""
from __future__ import annotations

import argparse
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


def verify() -> dict[str, Any]:
    pillars: dict[str, dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="pie-context-runtime-") as directory:
        root = Path(directory)
        storage = root / ".pie"
        storage.mkdir()
        connect(storage / "index.sqlite3").close()
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

    return {
        "schema": "pie-context-runtime-verifier-v1",
        "status": "PASS_LOCAL",
        "local_validation": True,
        "certification": "NOT_CERTIFIED",
        "external_provider_usage": "unavailable",
        "synthetic_provider_evidence": True,
        "pillars": pillars,
        "note": "Synthetic evaluator evidence is not external provider usage.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify()
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    print(encoded)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS_LOCAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
