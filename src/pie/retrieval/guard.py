"""Deterministic claim validation and certified answer rendering.

An LLM is not an authority. Its optional claims are compared with canonical
evidence; free-text narratives are never promoted to verified facts.
"""
from __future__ import annotations

import json


ALLOWED_FACTS = ("signature", "path", "line", "direct_call_count")


def validate_claims(evidence: dict, proposed: object) -> dict:
    """Check exact grounded claims, exposing bounded actionable diagnostics.

    The validator never upgrades unverified model text into source evidence.
    Rejected values and raw model output are intentionally not echoed.
    """
    if not isinstance(proposed, dict) or not isinstance(proposed.get("claims"), list):
        return {"status": "REJECTED", "reason": "invalid_structured_proposal", "checks": [],
                "missing_required": ["signature", "path"]}
    claims = proposed["claims"]
    if len(claims) > 32:
        return {"status": "REJECTED", "reason": "too_many_claims", "checks": [],
                "missing_required": ["signature", "path"]}
    checks = []
    valid_fields = set()
    seen_fields = set()
    for claim in claims:
        if not isinstance(claim, dict):
            checks.append({"field": None, "status": "REJECTED", "reason": "invalid_claim_shape"})
            continue
        field = claim.get("field")
        if not isinstance(field, str) or field not in ALLOWED_FACTS:
            checks.append({"field": field if isinstance(field, str) else None,
                           "status": "REJECTED", "reason": "unknown_field"})
            continue
        if field in seen_fields:
            checks.append({"field": field, "status": "REJECTED", "reason": "duplicate_field"})
            continue
        seen_fields.add(field)
        if claim.get("evidence_id") != evidence["evidence_id"]:
            checks.append({"field": field, "status": "REJECTED", "reason": "evidence_id_mismatch"})
            continue
        if "value" not in claim:
            checks.append({"field": field, "status": "REJECTED", "reason": "missing_value"})
            continue
        expected = evidence[field]
        matched = type(claim["value"]) is type(expected) and claim["value"] == expected
        checks.append({"field": field, "status": "VERIFIED" if matched else "REJECTED",
                       "reason": "exact_match" if matched else "value_mismatch"})
        if matched:
            valid_fields.add(field)
    missing = sorted({"signature", "path"} - valid_fields)
    passed = not missing and bool(checks) and all(c["status"] == "VERIFIED" for c in checks)
    failure_reasons = {c["reason"] for c in checks if c["status"] == "REJECTED"}
    if passed:
        reason = "all_required_claims_verified"
    elif missing and not failure_reasons:
        reason = "missing_required_claims"
    elif len(failure_reasons) == 1 and not missing:
        reason = next(iter(failure_reasons))
    elif len(failure_reasons) == 1 and missing and len(checks) == 1:
        reason = next(iter(failure_reasons))
    else:
        reason = "claim_validation_failed"
    return {"status": "VERIFIED" if passed else "REJECTED",
            "reason": reason, "checks": checks, "missing_required": missing}


def render_certified(evidence: dict) -> str:
    """Template-based answer with no model-generated factual text."""
    if evidence.get("status") != "VERIFIED":
        raise ValueError("Evidence is not certified")
    lines = [
        f"Definição verificada: {evidence['symbol']}",
        f"Arquivo: {evidence['path']}:{evidence['line']}",
        f"Assinatura: {evidence['signature']}",
        f"Chamadas diretas verificadas: {evidence['direct_call_count']}",
    ]
    for call in evidence["direct_call_sites"]:
        lines.append(f"- {call['path']}:{call['line']} ({call['consumer_symbol']})")
    if evidence["direct_call_sites_omitted"]:
        lines.append(f"Chamadas omitidas pelo limite: {evidence['direct_call_sites_omitted']}")
    lines.append("Limitação: " + evidence["coverage_note"])
    lines.append("Evidência: " + evidence["evidence_id"])
    return "\n".join(lines)


def parse_model_proposal(raw: str) -> dict:
    """Accept only one JSON object; no markdown fences or regex salvage."""
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError("Oversized or invalid model proposal")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict) or set(parsed) - {"claims"}:
        raise ValueError("Unexpected proposal fields")
    return parsed
