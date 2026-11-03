"""Deterministic claim validation and certified answer rendering.

An LLM is not an authority. Its optional claims are compared with canonical
evidence; free-text narratives are never promoted to verified facts.
"""
from __future__ import annotations

import json


ALLOWED_FACTS = ("signature", "path", "line", "direct_call_count")


def validate_claims(evidence: dict, proposed: object) -> dict:
    """Validate a bounded model proposal without assuming it is truthful."""
    if not isinstance(proposed, dict) or not isinstance(proposed.get("claims"), list):
        return {"status": "REJECTED", "reason": "invalid_structured_proposal", "checks": []}
    if len(proposed["claims"]) > 32:
        return {"status": "REJECTED", "reason": "too_many_claims", "checks": []}
    checks = []
    for claim in proposed["claims"]:
        if not isinstance(claim, dict):
            return {"status": "REJECTED", "reason": "invalid_claim_shape", "checks": checks}
        field = claim.get("field")
        if field not in ALLOWED_FACTS or claim.get("evidence_id") != evidence["evidence_id"]:
            checks.append({"field": field if isinstance(field, str) else None,
                           "status": "REJECTED", "reason": "unknown_or_unbound_evidence"})
            continue
        expected = evidence[field]
        matched = type(claim.get("value")) is type(expected) and claim["value"] == expected
        checks.append({"field": field, "status": "VERIFIED" if matched else "REJECTED",
                       "reason": "exact_match" if matched else "value_mismatch"})
    required = {"signature", "path"}
    certified = {
        c["field"] for c in checks if c["status"] == "VERIFIED"
    }
    passed = (required <= certified and bool(checks)
              and all(c["status"] == "VERIFIED" for c in checks))
    return {"status": "VERIFIED" if passed else "REJECTED",
            "reason": "all_required_claims_verified" if passed else "claim_mismatch_or_missing",
            "checks": checks}


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
