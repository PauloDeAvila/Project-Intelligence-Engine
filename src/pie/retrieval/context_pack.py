"""Compact, deterministic source-backed Context Packs for MCP/CLI consumers.

This module only reads a verified PIE index and Python source. It never calls
an LLM, runs analyzed modules, or asserts that changing code causes breakage.
The char budget is an exact serialized-JSON bound, NOT a measured token count.
"""
from __future__ import annotations

import json
from pathlib import Path

from pie.retrieval.evidence import EvidenceError, _source_snapshot, build_evidence

MIN_CHARS = 1500
MAX_CHARS = 64000
MAX_CALLS = 100
MAX_SNIPPET_LINES = 12


def _snippet(text: str, line: int, *, before: int = 0, after: int = 0) -> dict:
    """Return a bounded source excerpt with original 1-based line numbers."""
    lines = text.splitlines()
    if not 1 <= line <= len(lines):
        raise EvidenceError("Indexed source line is no longer available")
    start = max(1, line - before)
    end = min(len(lines), line + after, start + MAX_SNIPPET_LINES - 1)
    return {
        "start_line": start,
        "end_line": end,
        "text": "\n".join(f"{number}: {lines[number - 1]}" for number in range(start, end + 1)),
    }


def _size(value: dict) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def build_context_pack(
    root: Path, symbol: str, *, max_chars: int = 12000,
    max_calls: int = MAX_CALLS, include_snippets: bool = True,
) -> dict:
    """Build an exact-budget Context Pack from verified, unambiguous facts.

    Structural omissions are explicit. If even the minimal truthful answer
    cannot fit, fail closed instead of publishing half a definition or claim.
    """
    if type(max_chars) is not int or not MIN_CHARS <= max_chars <= MAX_CHARS:
        raise ValueError(f"max_chars must be an integer in [{MIN_CHARS},{MAX_CHARS}]")
    if type(max_calls) is not int or not 1 <= max_calls <= MAX_CALLS:
        raise ValueError("max_calls must be an integer in [1,100]")
    if type(include_snippets) is not bool:
        raise ValueError("include_snippets must be a boolean")

    root = Path(root).resolve(strict=True)
    evidence = build_evidence(root, symbol, max_calls=max_calls)
    source, target_hash = _source_snapshot(root, evidence["path"])
    definition = {
        "symbol": evidence["symbol"],
        "binding": evidence["binding"],
        "path": evidence["path"],
        "line": evidence["line"],
        "end_line": evidence["end_line"],
        "signature": evidence["signature"],
        "sha256": target_hash,
    }
    if include_snippets:
        definition["snippet"] = _snippet(source, evidence["line"], after=5)

    result = {
        "schema_version": "pie-context-pack-v1",
        "status": "VERIFIED_STATIC_CONTEXT",
        "source_evidence_id": evidence["evidence_id"],
        "definition": definition,
        "callers": [],
        "coverage": {
            "verified_direct_call_count": evidence["direct_call_count"],
            "returned_direct_call_count": 0,
            "omitted_by_call_limit": evidence["direct_call_sites_omitted"],
            "omitted_by_budget": 0,
            "source_snippets_omitted_by_budget": 0,
            "complete_direct_call_list": False,
            "limitations": [
                "Static direct calls only; dynamic dispatch and indirect aliases may be missed",
                "Unindexed and external consumers are outside the indexed project",
                "Runtime breakage and behavioral impact are not established",
            ],
        },
        "impact": {"status": "UNDETERMINED", "breaking_change_proven": False},
        "budget": {
            "max_chars": max_chars,
            "used_chars": 0,
            "unit": "serialized_json_characters_not_model_tokens",
        },
    }
    # Candidate caller content is checked against the index before inclusion.
    # build_evidence has already verified every returned caller file hash.
    source_cache: dict[str, tuple[str, str]] = {evidence["path"]: (source, target_hash)}
    sites = sorted(
        evidence["direct_call_sites"],
        key=lambda s: (s["path"], s["line"], s.get("consumer_symbol") or ""),
    )
    for site in sites:
        if site["path"] not in source_cache:
            source_cache[site["path"]] = _source_snapshot(root, site["path"])
        caller_source, caller_hash = source_cache[site["path"]]
        item = {
            "path": site["path"],
            "line": site["line"],
            "consumer_symbol": site.get("consumer_symbol"),
            "resolution": "verified",
            "usage_kind": "direct_call",
            "source_sha256": caller_hash,
            "target_binding": evidence["binding"],
        }
        if include_snippets:
            item["snippet"] = _snippet(caller_source, site["line"])
        result["callers"].append(item)

    def finalize() -> None:
        count = len(result["callers"])
        coverage = result["coverage"]
        coverage["returned_direct_call_count"] = count
        coverage["omitted_by_budget"] = len(sites) - count
        coverage["complete_direct_call_list"] = (
            coverage["omitted_by_call_limit"] == 0 and coverage["omitted_by_budget"] == 0
        )
        # Used length counts its own numeric value: reach a stable fixed point.
        for _ in range(8):
            updated = _size(result)
            if result["budget"]["used_chars"] == updated:
                break
            result["budget"]["used_chars"] = updated

    finalize()
    # Drop snippets before dropping evidence edges, preserving the usefulness
    # of a compact dependency map under tight budgets.
    if _size(result) > max_chars:
        for item in reversed(result["callers"]):
            if "snippet" in item:
                del item["snippet"]
                result["coverage"]["source_snippets_omitted_by_budget"] += 1
                finalize()
                if _size(result) <= max_chars:
                    break
    if _size(result) > max_chars and "snippet" in definition:
        del definition["snippet"]
        result["coverage"]["source_snippets_omitted_by_budget"] += 1
        finalize()
    while _size(result) > max_chars and result["callers"]:
        result["callers"].pop()
        finalize()
    if _size(result) > max_chars:
        raise EvidenceError("BUDGET_TOO_SMALL: unable to fit a trustworthy Context Pack")
    finalize()
    if _size(result) > max_chars:
        raise EvidenceError("BUDGET_TOO_SMALL: unable to finalize Context Pack")
    return result
