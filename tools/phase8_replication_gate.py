"""Fail-closed gate for provider-backed paired replication reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pie.certification.regression import RunEvidence, evaluate_replication_suite


def _cached_tokens(arm: dict) -> tuple[int | None, bool]:
    usage = arm.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens")
    return (cached if isinstance(cached, int) and cached >= 0 else None, arm.get("cache_observed") is True)


def _run(report: dict, name: str) -> RunEvidence:
    arm = report[name]
    cached, cache_observed = _cached_tokens(arm)
    return RunEvidence(
        pair_id=report["pair_id"],
        scenario_id=report["task_id"],
        application=report.get("application", "unknown"),
        condition=name,
        model=report["model"],
        prompt_sha256=report["prompt_sha256"],
        configuration_sha256=report["configuration_sha256"],
        provider_usage_status=arm.get("provider_usage_status", "unavailable"),
        input_tokens=arm.get("input_tokens"),
        cached_input_tokens=cached,
        output_tokens=arm.get("output_tokens"),
        latency_ms=arm.get("latency_s", 0) * 1000 if isinstance(arm.get("latency_s"), (int, float)) else None,
        mcp_calls=arm.get("mcp_calls"),
        oracle_pass=arm.get("task_oracle_pass") is True,
        route_verified=arm.get("route_verified") is True,
        duplicate_calls=0,
        fixture_sha256=report.get("fixture_sha256"),
        actual_model=arm.get("actual_model"),
        mcp_methods=tuple(arm.get("mcp_methods") or ()),
        cache_observed=cache_observed,
        automatic_retry=report.get("retry_count", 0) != 0 or arm.get("automatic_retry") is not False,
        replication_index=report.get("replication_index"),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    loaded = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
    pairs = [(_run(report, "baseline"), _run(report, "optimized")) for report in loaded]
    result = evaluate_replication_suite(pairs)
    result["reports"] = [str(path) for path in args.reports]
    result["model"] = sorted({report.get("model") for report in loaded})
    result["application"] = sorted({report.get("application", "unknown") for report in loaded})
    result["fixture_sha256"] = sorted({report.get("fixture_sha256") for report in loaded})
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
