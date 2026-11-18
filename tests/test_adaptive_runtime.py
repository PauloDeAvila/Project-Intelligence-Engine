from __future__ import annotations

import pytest

from pie.retrieval.adaptive_runtime import MeasuredCandidate, choose_candidate


def test_selects_lowest_measured_total_tokens():
    result = choose_candidate(
        [
            MeasuredCandidate("larger", "available", 100, 20, 50, 10.0, True, 1),
            MeasuredCandidate("smaller", "available", 80, None, 40, 12.0),
        ]
    )
    assert result["state"] == "SELECTED"
    assert result["representation"] == "smaller"
    assert result["metrics"]["total_tokens"] == 120
    assert result["metrics"]["uncached_input_tokens"] is None


def test_quality_and_unavailable_usage_are_ineligible():
    result = choose_candidate(
        [
            MeasuredCandidate("bad", "available", 1, None, 1, quality_pass=False),
            MeasuredCandidate("unknown", "unavailable", 1, None, 1),
        ]
    )
    assert result["state"] == "NO_VALID_CANDIDATE"
    assert "quality_fail:bad" in result["reasons"]
    assert "usage_unavailable:unknown" in result["reasons"]


def test_missing_output_is_not_replaced_with_zero():
    result = choose_candidate([MeasuredCandidate("partial", "available", 100)])
    assert result["state"] == "NO_VALID_CANDIDATE"
    assert "missing_total_tokens:partial" in result["reasons"]


def test_deterministic_tie_break_and_latency_objective():
    first = choose_candidate(
        [
            MeasuredCandidate("zeta", "available", 50, None, 25, 5.0),
            MeasuredCandidate("alpha", "available", 50, None, 25, 5.0),
        ]
    )
    assert first["representation"] == "alpha"
    fast = choose_candidate(
        [
            MeasuredCandidate("slow", "available", latency_ms=50.0),
            MeasuredCandidate("fast", "unavailable", latency_ms=5.0),
        ],
        objective="latency",
    )
    assert fast["representation"] == "fast"


def test_latency_objective_marks_candidates_without_latency_ineligible():
    result = choose_candidate(
        [
            MeasuredCandidate("no-latency", "available", input_tokens=1, output_tokens=1),
            MeasuredCandidate("offline", "unavailable", latency_ms=None),
        ],
        objective="latency",
    )
    assert result["state"] == "NO_VALID_CANDIDATE"
    assert "missing_latency:no-latency" in result["reasons"]
    assert "missing_latency:offline" in result["reasons"]

    # Under the latency objective, usage availability is not a gate: an
    # unavailable candidate with a measured latency stays eligible.
    usable = choose_candidate(
        [
            MeasuredCandidate("measured", "unavailable", latency_ms=3.0),
            MeasuredCandidate("unmeasured", "available", input_tokens=1, output_tokens=1),
        ],
        objective="latency",
    )
    assert usable["state"] == "SELECTED"
    assert usable["representation"] == "measured"


def test_latency_objective_ranking_uses_mcp_calls_and_representation_for_ties():
    result = choose_candidate(
        [
            MeasuredCandidate("later", "available", latency_ms=10.0, mcp_calls=0),
            MeasuredCandidate("early", "available", latency_ms=10.0, mcp_calls=2),
        ],
        objective="latency",
    )
    assert result["state"] == "SELECTED"
    assert result["representation"] == "later"
    assert result["decision_basis"][1] == "ranked_by=latency_ms,mcp_calls,representation"

    same_latency = choose_candidate(
        [
            MeasuredCandidate("zulu", "available", latency_ms=10.0),
            MeasuredCandidate("alpha", "available", latency_ms=10.0),
        ],
        objective="latency",
    )
    assert same_latency["representation"] == "alpha"


def test_cost_objective_ties_break_deterministically_on_rank_fields():
    result = choose_candidate(
        [
            MeasuredCandidate("slow", "available", cost_usd=0.01, latency_ms=5.0),
            MeasuredCandidate("quick", "available", cost_usd=0.01, latency_ms=1.0),
        ],
        objective="cost",
    )
    assert result["state"] == "SELECTED"
    assert result["representation"] == "quick"

    identical = choose_candidate(
        [
            MeasuredCandidate("bravo", "available", cost_usd=0.01, latency_ms=1.0),
            MeasuredCandidate("alpha", "available", cost_usd=0.01, latency_ms=1.0),
        ],
        objective="cost",
    )
    assert identical["representation"] == "alpha"


def test_cost_objective_marks_candidates_without_cost_ineligible():
    result = choose_candidate(
        [
            MeasuredCandidate("free-form", "available", input_tokens=1, output_tokens=1),
            MeasuredCandidate("offline", "unavailable", cost_usd=0.01),
        ],
        objective="cost",
    )
    assert result["state"] == "NO_VALID_CANDIDATE"
    assert "missing_cost:free-form" in result["reasons"]
    assert "usage_unavailable:offline" in result["reasons"]


def test_validation_rejects_bad_measurements():
    with pytest.raises(ValueError):
        MeasuredCandidate("x", "available", input_tokens=10, cached_input_tokens=11)
    with pytest.raises(ValueError):
        MeasuredCandidate("x", "available", cached_input_tokens=1)
    with pytest.raises(ValueError):
        MeasuredCandidate("x", "available", latency_ms=float("inf"))
    with pytest.raises(ValueError):
        MeasuredCandidate("x", "available", input_tokens=-1)


def test_empty_input_is_rejected():
    with pytest.raises(ValueError):
        choose_candidate([])


def test_cost_objective_requires_verified_cost_and_is_deterministic():
    result = choose_candidate(
        [
            MeasuredCandidate("expensive", "available", cost_usd=0.02, latency_ms=1.0),
            MeasuredCandidate("cheap", "available", cost_usd=0.01, latency_ms=2.0),
            MeasuredCandidate("unknown", "available", latency_ms=0.1),
        ],
        objective="cost",
    )
    assert result["representation"] == "cheap"
    assert result["metrics"]["cost_usd"] == 0.01


def test_cost_validation_is_fail_closed():
    with pytest.raises(ValueError):
        MeasuredCandidate("bool", "available", cost_usd=True)
    with pytest.raises(ValueError):
        MeasuredCandidate("nan", "available", cost_usd=float("nan"))
    result = choose_candidate(
        [MeasuredCandidate("no-cost", "available", input_tokens=1, output_tokens=1)],
        objective="cost",
    )
    assert result["state"] == "NO_VALID_CANDIDATE"
    assert "missing_cost:no-cost" in result["reasons"]
