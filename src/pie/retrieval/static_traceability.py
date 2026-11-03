"""DES-04: conservative, source-backed direct-call traceability.

This report is intentionally NOT a causal impact analysis. A verified
syntactic call site is a fact about a source snapshot, not proof a change
will break a consumer. No execution or inference occurs here.
"""
from __future__ import annotations

from pathlib import Path

from pie.retrieval.evidence import build_evidence


def inspect_static_dependencies(root: Path, symbol: str) -> dict:
    """Emit verified direct-call edges only, with explicit epistemic bounds.

    build_evidence fails closed for stale, partial and ambiguous projects,
    and verifies source hashes and resolved direct-call references.
    """
    evidence = build_evidence(root, symbol, max_calls=100)
    edges = [
        {
            "kind": "verified_static_direct_call",
            "source": {
                "path": site["path"], "line": site["line"],
                "consumer_symbol": site["consumer_symbol"],
            },
            "target": {
                "binding": evidence["binding"],
                "path": evidence["path"], "line": evidence["line"],
                "symbol": evidence["symbol"],
            },
            "proof": {
                "resolution": site["resolution"],
                "usage_kind": site["usage_kind"],
                "target_sha256": evidence["sha256"],
                "evidence_id": evidence["evidence_id"],
            },
        }
        for site in evidence["direct_call_sites"]
    ]
    return {
        "status": "STATIC_EVIDENCE_ONLY",
        "symbol": symbol,
        "source_evidence_id": evidence["evidence_id"],
        "edges": edges,
        "verified_direct_call_count": evidence["direct_call_count"],
        "observed_edge_count": len(edges),
        "truncated_edge_count": evidence["direct_call_sites_omitted"],
        "impact": {
            "status": "UNDETERMINED",
            "breaking_change_proven": False,
            "runtime_effect_proven": False,
            "causal_claims_certified": [],
        },
        "coverage": {
            "verified": "Resolved direct syntactic calls in indexed local Python sources",
            "not_verified": [
                "dynamic dispatch", "indirect aliases", "runtime control flow",
                "unindexed or external callers", "semantic behavior changes",
                "whether a change will break a test or production execution",
            ],
            "warning": evidence["coverage_note"],
        },
    }
