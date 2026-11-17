from __future__ import annotations

from dataclasses import replace

import pytest

from pie.certification.regression import (
    RunEvidence,
    evaluate_golden_suite,
    evaluate_pair,
    evaluate_replication_suite,
)


def make_run(**overrides):
    values = dict(
        pair_id="pair-1",
        scenario_id="scenario-1",
        application="blender",
        condition="baseline",
        model="model-a",
        prompt_sha256="a" * 64,
        configuration_sha256="b" * 64,
        provider_usage_status="available",
        input_tokens=100,
        cached_input_tokens=40,
        output_tokens=50,
        latency_ms=1200.0,
        mcp_calls=2,
        oracle_pass=True,
        route_verified=True,
    )
    values.update(overrides)
    return RunEvidence(**values)


def test_valid_pair_reports_real_arithmetic():
    result = evaluate_pair(
        make_run(),
        make_run(condition="optimized", input_tokens=60, cached_input_tokens=50, output_tokens=45, latency_ms=900.0, mcp_calls=1),
    )
    assert result["status"] == "CERTIFIED_PAIR"
    assert result["savings"]["baseline_total_tokens"] == 150
    assert result["savings"]["optimized_total_tokens"] == 105
    assert result["savings"]["baseline_uncached_input_tokens"] == 60
    assert result["savings"]["optimized_uncached_input_tokens"] == 10
    assert result["savings"]["savings_total_percent"] == 30.0
    assert result["savings"]["mcp_call_delta"] == -1


def test_identity_usage_oracle_route_and_duplicate_failures_block_certification():
    result = evaluate_pair(
        make_run(prompt_sha256="c" * 64, route_verified=False),
        make_run(condition="optimized", provider_usage_status="unavailable", oracle_pass=False, duplicate_calls=1),
    )
    assert result["status"] == "NOT_CERTIFIED"
    assert result["savings"] is None
    assert "prompt_sha256_mismatch" in result["reasons"]
    assert "optimized_provider_usage_unavailable" in result["reasons"]
    assert "baseline_route_unverified" in result["reasons"]
    assert "optimized_duplicate_calls" in result["reasons"]


def test_negative_savings_is_visible_and_missing_metrics_are_not_assertions():
    result = evaluate_pair(
        make_run(),
        make_run(condition="optimized", input_tokens=150, cached_input_tokens=40, output_tokens=80),
    )
    assert result["status"] == "CERTIFIED_PAIR"
    assert result["savings"]["savings_total_percent"] < 0
    missing = evaluate_pair(make_run(latency_ms=None), make_run(condition="optimized"))
    assert missing["status"] == "NOT_CERTIFIED"
    assert "baseline_latency_missing" in missing["reasons"]


def test_zero_uncached_input_has_null_input_savings():
    result = evaluate_pair(
        make_run(input_tokens=100, cached_input_tokens=100),
        make_run(condition="optimized", input_tokens=80, cached_input_tokens=80),
    )
    assert result["status"] == "CERTIFIED_PAIR"
    assert result["savings"]["savings_input_percent"] is None


def test_evidence_validation_is_strict():
    with pytest.raises(ValueError):
        make_run(cached_input_tokens=101)
    with pytest.raises(ValueError):
        make_run(latency_ms=float("inf"))
    with pytest.raises(ValueError):
        make_run(input_tokens=True)


def test_golden_suite_requires_all_valid_pairs_and_aggregates_sums():
    pair = (
        make_run(),
        make_run(condition="optimized", input_tokens=60, cached_input_tokens=50, output_tokens=45),
    )
    pair2 = (
        make_run(pair_id="pair-2"),
        make_run(pair_id="pair-2", condition="optimized", input_tokens=60, cached_input_tokens=50, output_tokens=45),
    )
    suite = evaluate_golden_suite([pair, pair2])
    assert suite["status"] == "CERTIFIED"
    assert suite["aggregate_savings"]["baseline_total_tokens"] == 300
    assert suite["aggregate_savings"]["optimized_total_tokens"] == 210
    duplicate = evaluate_golden_suite([pair, pair])
    assert duplicate["status"] == "NOT_CERTIFIED"
    assert "duplicate_pair_id" in duplicate["reasons"]
    assert evaluate_golden_suite([])["status"] == "NOT_CERTIFIED"


def strict_pair(pair_id="pair-1", scenario_id="scenario-1", fixture="f" * 64, replication_index=1):
    return (
        make_run(pair_id=pair_id, scenario_id=scenario_id, fixture_sha256=fixture,
                 actual_model="model-a", mcp_methods=("initialize", "tools/list", "tools/call"),
                 cache_observed=True, replication_index=replication_index),
        make_run(pair_id=pair_id, scenario_id=scenario_id, condition="optimized",
                 fixture_sha256=fixture, actual_model="model-a",
                 mcp_methods=("initialize", "tools/list", "tools/call"), cache_observed=True,
                 replication_index=replication_index),
    )


def test_replication_suite_rejects_duplicate_scenario_fixture_and_missing_trace():
    duplicate = evaluate_replication_suite([strict_pair(), strict_pair(pair_id="pair-2")])
    assert duplicate["status"] == "NOT_CERTIFIED"
    assert "duplicate_scenario_fixture" in duplicate["reasons"]
    pair = strict_pair(pair_id="pair-3", scenario_id="scenario-3")
    incomplete = (replace(pair[0], mcp_methods=None), pair[1])
    result = evaluate_replication_suite([incomplete])
    assert result["status"] == "NOT_CERTIFIED"
    assert "baseline_mcp_trace_incomplete" in result["reasons"]


def test_replication_suite_requires_cache_and_actual_provider_usage_identity():
    pair = strict_pair(pair_id="pair-4", scenario_id="scenario-4")
    pair = (pair[0], replace(pair[1], cache_observed=False, actual_model="other-model"))
    result = evaluate_replication_suite([pair])
    assert result["status"] == "NOT_CERTIFIED"
    assert "optimized_cache_unobserved" in result["reasons"]
    assert "pair-4_actual_model_mismatch" in result["reasons"]
