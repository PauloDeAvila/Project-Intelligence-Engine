"""Fail-closed normalization of provider-reported token usage.

This adapter accepts common OpenAI-compatible response shapes but never derives
tokens from text, characters, or model limits. Missing cache information keeps
the record unavailable for certification rather than becoming zero.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True)
class ProviderUsage:
    provider_usage_status: str
    model: str | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    duration_ms: float | None = None
    reason: str | None = None

    @property
    def uncached_input_tokens(self) -> int | None:
        if self.input_tokens is None or self.cached_input_tokens is None:
            return None
        return self.input_tokens - self.cached_input_tokens

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens

    def as_record(self) -> dict[str, Any]:
        return {
            "provider_usage_status": self.provider_usage_status,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "uncached_input_tokens": self.uncached_input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_output_tokens": self.reasoning_output_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": self.duration_ms,
            "reason": self.reason,
        }


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _duration(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return float(value)


def parse_provider_usage(
    payload: object,
    *,
    model: str | None = None,
    duration_ms: float | None = None,
) -> ProviderUsage:
    """Normalize a provider response without filling absent usage fields."""
    if not isinstance(payload, dict):
        return ProviderUsage("unavailable", model=model, reason="response_not_object")
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return ProviderUsage("unavailable", model=model, reason="usage_missing")

    input_tokens = _nonnegative_int(
        usage.get("input_tokens", usage.get("prompt_tokens"))
    )
    output_tokens = _nonnegative_int(
        usage.get("output_tokens", usage.get("completion_tokens"))
    )
    cached = usage.get("cached_input_tokens")
    prompt_details = usage.get("prompt_tokens_details")
    if cached is None and isinstance(prompt_details, dict):
        cached = prompt_details.get("cached_tokens")
    cached_input_tokens = _nonnegative_int(cached)

    reasoning = usage.get("reasoning_output_tokens")
    completion_details = usage.get("completion_tokens_details")
    if reasoning is None and isinstance(completion_details, dict):
        reasoning = completion_details.get("reasoning_tokens")
    reasoning_output_tokens = _nonnegative_int(reasoning) if reasoning is not None else None

    resolved_model = model if isinstance(model, str) and model else payload.get("model")
    if not isinstance(resolved_model, str) or not resolved_model:
        resolved_model = None
    resolved_duration = _duration(duration_ms)

    if input_tokens is None or output_tokens is None:
        return ProviderUsage(
            "unavailable",
            model=resolved_model,
            duration_ms=resolved_duration,
            reason="input_or_output_usage_missing_or_invalid",
        )
    if cached_input_tokens is None:
        return ProviderUsage(
            "unavailable",
            model=resolved_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_output_tokens=reasoning_output_tokens,
            duration_ms=resolved_duration,
            reason="cached_input_usage_missing_or_invalid",
        )
    if cached_input_tokens > input_tokens:
        return ProviderUsage(
            "unavailable",
            model=resolved_model,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            reasoning_output_tokens=reasoning_output_tokens,
            duration_ms=resolved_duration,
            reason="cached_input_exceeds_input",
        )
    return ProviderUsage(
        "available",
        model=resolved_model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_output_tokens,
        duration_ms=resolved_duration,
    )


__all__ = ["ProviderUsage", "parse_provider_usage"]
