"""Deterministic adaptive selection from provider-reported measurements.

This module never estimates tokens from characters and never turns unavailable
usage into zero. Candidates without the metric required by the objective are
ineligible for that decision.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

USAGE_STATUS_AVAILABLE = "available"
USAGE_STATUS_UNAVAILABLE = "unavailable"
_VALID_STATUSES = frozenset((USAGE_STATUS_AVAILABLE, USAGE_STATUS_UNAVAILABLE))
_INTEGER_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "mcp_calls",
    "recovery_calls",
)


@dataclass(frozen=True)
class MeasuredCandidate:
    representation: str
    provider_usage_status: str
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None
    quality_pass: bool = True
    mcp_calls: int | None = None
    recovery_calls: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.representation, str) or not self.representation.strip():
            raise ValueError("representation must be a nonempty string")
        if self.provider_usage_status not in _VALID_STATUSES:
            raise ValueError("unsupported provider usage status")
        if not isinstance(self.quality_pass, bool):
            raise ValueError("quality_pass must be a bool")
        for name in _INTEGER_FIELDS:
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative int or None")
        if self.cached_input_tokens is not None and self.input_tokens is None:
            raise ValueError("cached_input_tokens requires input_tokens")
        if (
            self.input_tokens is not None
            and self.cached_input_tokens is not None
            and self.cached_input_tokens > self.input_tokens
        ):
            raise ValueError("cached_input_tokens must be <= input_tokens")
        if self.latency_ms is not None:
            if isinstance(self.latency_ms, bool) or not isinstance(
                self.latency_ms, (int, float)
            ) or not math.isfinite(self.latency_ms) or self.latency_ms < 0:
                raise ValueError("latency_ms must be a finite nonnegative number")


def _token_rank(candidate: MeasuredCandidate) -> tuple[object, ...]:
    total = candidate.input_tokens + candidate.output_tokens  # validated by caller
    latency = (0, candidate.latency_ms) if candidate.latency_ms is not None else (1, 0)
    calls = (0, candidate.mcp_calls) if candidate.mcp_calls is not None else (1, 0)
    return total, latency, calls, candidate.representation


def _latency_rank(candidate: MeasuredCandidate) -> tuple[object, ...]:
    calls = (0, candidate.mcp_calls) if candidate.mcp_calls is not None else (1, 0)
    return candidate.latency_ms, calls, candidate.representation


def choose_candidate(
    candidates: list[MeasuredCandidate],
    *,
    objective: str = "tokens",
    require_quality: bool = True,
) -> dict[str, object]:
    """Choose a quality-valid representation using measured metrics only."""
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a nonempty list")
    if objective not in ("tokens", "latency"):
        raise ValueError("objective must be 'tokens' or 'latency'")

    eligible: list[MeasuredCandidate] = []
    reasons: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, MeasuredCandidate):
            reasons.append("not_a_measured_candidate")
            continue
        if require_quality and not candidate.quality_pass:
            reasons.append(f"quality_fail:{candidate.representation}")
            continue
        if objective == "tokens":
            if candidate.provider_usage_status != USAGE_STATUS_AVAILABLE:
                reasons.append(f"usage_unavailable:{candidate.representation}")
                continue
            if candidate.input_tokens is None or candidate.output_tokens is None:
                reasons.append(f"missing_total_tokens:{candidate.representation}")
                continue
        elif candidate.latency_ms is None:
            reasons.append(f"missing_latency:{candidate.representation}")
            continue
        eligible.append(candidate)

    if not eligible:
        return {
            "state": "NO_VALID_CANDIDATE",
            "representation": None,
            "metrics": None,
            "reasons": reasons,
            "decision_basis": [
                f"objective={objective}",
                f"require_quality={require_quality}",
            ],
        }

    if objective == "tokens":
        chosen = min(eligible, key=_token_rank)
        ranking = "total_tokens,latency_ms,mcp_calls,representation"
    else:
        chosen = min(eligible, key=_latency_rank)
        ranking = "latency_ms,mcp_calls,representation"

    total_tokens = None
    uncached_input_tokens = None
    if chosen.input_tokens is not None and chosen.output_tokens is not None:
        total_tokens = chosen.input_tokens + chosen.output_tokens
    if chosen.input_tokens is not None and chosen.cached_input_tokens is not None:
        uncached_input_tokens = chosen.input_tokens - chosen.cached_input_tokens
    return {
        "state": "SELECTED",
        "representation": chosen.representation,
        "metrics": {
            "provider_usage_status": chosen.provider_usage_status,
            "input_tokens": chosen.input_tokens,
            "cached_input_tokens": chosen.cached_input_tokens,
            "output_tokens": chosen.output_tokens,
            "total_tokens": total_tokens,
            "uncached_input_tokens": uncached_input_tokens,
            "latency_ms": chosen.latency_ms,
            "mcp_calls": chosen.mcp_calls,
            "recovery_calls": chosen.recovery_calls,
        },
        "decision_basis": [
            f"objective={objective}",
            f"ranked_by={ranking}",
            f"require_quality={require_quality}",
        ],
    }


__all__ = [
    "MeasuredCandidate",
    "USAGE_STATUS_AVAILABLE",
    "USAGE_STATUS_UNAVAILABLE",
    "choose_candidate",
]
