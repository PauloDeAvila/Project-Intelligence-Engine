"""Opt-in PIE-first navigation policy; no changes to source retrieval.

Pure policy over a typed observation. The caller owns freshness verification
and actual interception; this module does not claim to enforce agent behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    PIE_FIRST = "PIE_FIRST"
    ALLOW_RAW = "ALLOW_RAW"
    BLOCK_ONCE = "BLOCK_ONCE"


@dataclass(frozen=True)
class Observation:
    action: str
    in_project: bool
    indexed: bool
    index_current: bool
    pie_queried: bool
    evidence_sufficient: bool = False
    explicit_source_read: bool = False
    first_raw_navigation: bool = True


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    reason: str
    next_tool: str | None = None


def evaluate(observation: Observation, *, strict: bool = False) -> Verdict:
    """Choose next navigation action. Never prevent edits, tests or debugging.

    Strict policy's first denial only applies to raw navigation against a fresh
    indexed source. A prior PIE query or insufficient PIE coverage permits
    source inspection. Dynamic behavior cannot be certified from this policy.
    """
    if observation.action not in {"read", "grep", "glob", "edit", "test", "pie_query"}:
        return Verdict(Decision.ALLOW_RAW, "unmanaged_tool")
    if observation.action in {"edit", "test", "pie_query"}:
        return Verdict(Decision.ALLOW_RAW, "operation_exempt")
    if observation.explicit_source_read:
        return Verdict(Decision.ALLOW_RAW, "source_required_for_validation")
    if not observation.in_project or not observation.indexed:
        return Verdict(Decision.ALLOW_RAW, "outside_index_scope")
    if not observation.index_current:
        return Verdict(Decision.ALLOW_RAW, "stale_index_must_not_block")
    if observation.pie_queried:
        return Verdict(Decision.ALLOW_RAW, "already_oriented")
    if strict and observation.first_raw_navigation and observation.action in {"read", "grep"}:
        return Verdict(Decision.BLOCK_ONCE, "fresh_index_requires_orientation", "pie_query")
    return Verdict(Decision.PIE_FIRST, "prefer_verified_index_before_raw_navigation", "pie_query")
