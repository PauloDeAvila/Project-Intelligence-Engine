"""Pure evaluator for continuous paired certification and regressions."""

from __future__ import annotations

from dataclasses import dataclass
import math

_CONDITIONS = frozenset(("baseline", "optimized"))
_USAGE_STATUSES = frozenset(("available", "unavailable"))


@dataclass(frozen=True)
class RunEvidence:
    pair_id: str
    scenario_id: str
    application: str
    condition: str
    model: str
    prompt_sha256: str
    configuration_sha256: str
    provider_usage_status: str
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None
    mcp_calls: int | None = None
    oracle_pass: bool = False
    route_verified: bool = False
    duplicate_calls: int = 0
    fixture_sha256: str | None = None
    actual_model: str | None = None
    mcp_methods: tuple[str, ...] | None = None
    cache_observed: bool = False
    automatic_retry: bool = False
    replication_index: int | None = None

    def __post_init__(self) -> None:
        for name in (
            "pair_id",
            "scenario_id",
            "application",
            "model",
            "prompt_sha256",
            "configuration_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a nonempty string")
        if self.condition not in _CONDITIONS:
            raise ValueError("condition must be baseline or optimized")
        if self.provider_usage_status not in _USAGE_STATUSES:
            raise ValueError("unsupported provider usage status")
        if not isinstance(self.oracle_pass, bool) or not isinstance(self.route_verified, bool):
            raise ValueError("oracle_pass and route_verified must be bools")
        for name in ("input_tokens", "cached_input_tokens", "output_tokens", "mcp_calls", "duplicate_calls"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError(f"{name} must be a nonnegative int or None")
        if self.replication_index is not None and (
            isinstance(self.replication_index, bool)
            or not isinstance(self.replication_index, int)
            or self.replication_index < 1
        ):
            raise ValueError("replication_index must be a positive int or None")
        if self.cached_input_tokens is not None and self.input_tokens is None:
            raise ValueError("cached_input_tokens requires input_tokens")
        if (
            self.input_tokens is not None
            and self.cached_input_tokens is not None
            and self.cached_input_tokens > self.input_tokens
        ):
            raise ValueError("cached_input_tokens must be <= input_tokens")
        if self.latency_ms is not None and (
            isinstance(self.latency_ms, bool)
            or not isinstance(self.latency_ms, (int, float))
            or not math.isfinite(self.latency_ms)
            or self.latency_ms < 0
        ):
            raise ValueError("latency_ms must be a finite nonnegative number or None")


def _identity_reasons(baseline: RunEvidence, optimized: RunEvidence) -> list[str]:
    reasons: list[str] = []
    for name in ("pair_id", "scenario_id", "application", "model", "prompt_sha256", "configuration_sha256"):
        if getattr(baseline, name) != getattr(optimized, name):
            reasons.append(f"{name}_mismatch")
    if baseline.condition != "baseline":
        reasons.append("baseline_condition_invalid")
    if optimized.condition != "optimized":
        reasons.append("optimized_condition_invalid")
    return reasons


def _run_reasons(label: str, run: RunEvidence) -> list[str]:
    reasons: list[str] = []
    if run.provider_usage_status != "available":
        reasons.append(f"{label}_provider_usage_unavailable")
    for name in ("input_tokens", "cached_input_tokens", "output_tokens"):
        if getattr(run, name) is None:
            reasons.append(f"{label}_{name}_missing")
    if run.latency_ms is None:
        reasons.append(f"{label}_latency_missing")
    if run.mcp_calls is None:
        reasons.append(f"{label}_mcp_calls_missing")
    if not run.oracle_pass:
        reasons.append(f"{label}_oracle_failure")
    if not run.route_verified:
        reasons.append(f"{label}_route_unverified")
    if run.duplicate_calls != 0:
        reasons.append(f"{label}_duplicate_calls")
    return reasons


def evaluate_pair(baseline: RunEvidence, optimized: RunEvidence) -> dict[str, object]:
    """Evaluate one pair without estimating any missing metric."""
    reasons = _identity_reasons(baseline, optimized)
    reasons.extend(_run_reasons("baseline", baseline))
    reasons.extend(_run_reasons("optimized", optimized))
    baseline_total = (
        None
        if baseline.input_tokens is None or baseline.output_tokens is None
        else baseline.input_tokens + baseline.output_tokens
    )
    if baseline_total is not None and baseline_total <= 0:
        reasons.append("baseline_total_tokens_not_positive")
    if reasons:
        return {
            "schema": "pie-certification-regression-v1",
            "status": "NOT_CERTIFIED",
            "pair_id": baseline.pair_id,
            "reasons": sorted(set(reasons)),
            "savings": None,
        }

    assert baseline.input_tokens is not None
    assert baseline.cached_input_tokens is not None
    assert baseline.output_tokens is not None
    assert baseline.latency_ms is not None
    assert baseline.mcp_calls is not None
    assert optimized.input_tokens is not None
    assert optimized.cached_input_tokens is not None
    assert optimized.output_tokens is not None
    assert optimized.latency_ms is not None
    assert optimized.mcp_calls is not None
    optimized_total = optimized.input_tokens + optimized.output_tokens
    baseline_uncached = baseline.input_tokens - baseline.cached_input_tokens
    optimized_uncached = optimized.input_tokens - optimized.cached_input_tokens
    savings_input = (
        None
        if baseline_uncached == 0
        else round((baseline_uncached - optimized_uncached) / baseline_uncached * 100.0, 6)
    )
    return {
        "schema": "pie-certification-regression-v1",
        "status": "CERTIFIED_PAIR",
        "pair_id": baseline.pair_id,
        "reasons": [],
        "savings": {
            "baseline_input_tokens": baseline.input_tokens,
            "baseline_cached_input_tokens": baseline.cached_input_tokens,
            "baseline_uncached_input_tokens": baseline_uncached,
            "baseline_output_tokens": baseline.output_tokens,
            "baseline_total_tokens": baseline_total,
            "optimized_input_tokens": optimized.input_tokens,
            "optimized_cached_input_tokens": optimized.cached_input_tokens,
            "optimized_uncached_input_tokens": optimized_uncached,
            "optimized_output_tokens": optimized.output_tokens,
            "optimized_total_tokens": optimized_total,
            "savings_input_percent": savings_input,
            "savings_total_percent": round(
                (baseline_total - optimized_total) / baseline_total * 100.0, 6
            ),
            "cached_input_delta": optimized.cached_input_tokens - baseline.cached_input_tokens,
            "output_token_delta": optimized.output_tokens - baseline.output_tokens,
            "latency_delta_ms": optimized.latency_ms - baseline.latency_ms,
            "mcp_call_delta": optimized.mcp_calls - baseline.mcp_calls,
        },
    }


def evaluate_golden_suite(
    pairs: list[tuple[RunEvidence, RunEvidence]],
) -> dict[str, object]:
    """Certify a suite only when it is nonempty and every pair is valid."""
    results = [evaluate_pair(baseline, optimized) for baseline, optimized in pairs]
    pair_ids = [baseline.pair_id for baseline, _ in pairs]
    duplicate_pair_ids = len(set(pair_ids)) != len(pair_ids)
    valid = (
        bool(results)
        and not duplicate_pair_ids
        and all(item["status"] == "CERTIFIED_PAIR" for item in results)
    )
    suite: dict[str, object] = {
        "schema": "pie-certification-regression-v1",
        "status": "CERTIFIED" if valid else "NOT_CERTIFIED",
        "pair_count": len(results),
        "per_pair": results,
    }
    if not valid:
        if not results:
            suite["reasons"] = ["empty_suite"]
        else:
            suite["reasons"] = ["one_or_more_pairs_not_certified"]
            if duplicate_pair_ids:
                suite["reasons"].append("duplicate_pair_id")
        suite["aggregate_savings"] = None
        return suite
    savings = [item["savings"] for item in results]
    baseline_total = sum(item["baseline_total_tokens"] for item in savings)
    optimized_total = sum(item["optimized_total_tokens"] for item in savings)
    baseline_uncached = sum(item["baseline_uncached_input_tokens"] for item in savings)
    optimized_uncached = sum(item["optimized_uncached_input_tokens"] for item in savings)
    suite["aggregate_savings"] = {
        "baseline_total_tokens": baseline_total,
        "optimized_total_tokens": optimized_total,
        "baseline_uncached_input_tokens": baseline_uncached,
        "optimized_uncached_input_tokens": optimized_uncached,
        "savings_total_percent": round((baseline_total - optimized_total) / baseline_total * 100.0, 6),
        "savings_input_percent": (
            None
            if baseline_uncached == 0
            else round((baseline_uncached - optimized_uncached) / baseline_uncached * 100.0, 6)
        ),
    }
    return suite


def evaluate_replication_suite(
    pairs: list[tuple[RunEvidence, RunEvidence]],
) -> dict[str, object]:
    """Apply strict identity and provenance gates before aggregating pairs."""
    base = evaluate_golden_suite(pairs)
    reasons = list(base.get("reasons", []))
    identities: list[tuple[str, str, int]] = []
    for baseline, optimized in pairs:
        fixture_values = (baseline.fixture_sha256, optimized.fixture_sha256)
        if not fixture_values[0] or fixture_values[0] != fixture_values[1]:
            reasons.append(f"{baseline.pair_id}_fixture_sha256_invalid")
        if baseline.actual_model != baseline.model or optimized.actual_model != optimized.model:
            reasons.append(f"{baseline.pair_id}_actual_model_mismatch")
        for label, run in (("baseline", baseline), ("optimized", optimized)):
            if not run.cache_observed:
                reasons.append(f"{label}_cache_unobserved")
            if run.automatic_retry:
                reasons.append(f"{label}_automatic_retry")
            if not run.mcp_methods or not {"initialize", "tools/list", "tools/call"}.issubset(run.mcp_methods):
                reasons.append(f"{label}_mcp_trace_incomplete")
        if fixture_values[0] and baseline.replication_index is not None:
            identities.append((baseline.scenario_id, fixture_values[0], baseline.replication_index))
        elif fixture_values[0]:
            reasons.append(f"{baseline.pair_id}_replication_index_missing")
    if len(identities) != len(set(identities)):
        reasons.append("duplicate_scenario_fixture")
    if reasons:
        return {
            "schema": "pie-certification-replication-v1",
            "status": "NOT_CERTIFIED",
            "pair_count": len(pairs),
            "reasons": sorted(set(reasons)),
            "per_pair": base.get("per_pair", []),
            "aggregate_savings": None,
        }
    return {
        "schema": "pie-certification-replication-v1",
        "status": base["status"],
        "pair_count": base["pair_count"],
        "reasons": [],
        "per_pair": base["per_pair"],
        "aggregate_savings": base["aggregate_savings"],
    }


__all__ = ["RunEvidence", "evaluate_pair", "evaluate_golden_suite", "evaluate_replication_suite"]
