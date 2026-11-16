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
