"""Conservative intent planner and dynamic evidence-selection validator.

This is NOT an LLM semantic oracle. Rules are intentionally small, auditable
and abstain on unsupported/ambiguous requests. The model never sees the
planner's expected fields or canonical values. Model selection is compared
against this independent deterministic plan.
"""
from __future__ import annotations

import re
import unicodedata

FIELDS = {
    "signature": "Exact Python function signature and declared parameters",
    "path": "File containing the function definition",
    "line": "Starting line of the function definition",
    "direct_call_count": "Number of verified direct syntactic calls (not all runtime callers)",
    "direct_call_sites": "Verified direct-call file paths, line numbers and consumer symbols",
}
FIELD_ORDER = tuple(FIELDS)


def _normalized(question: str) -> str:
    translated = unicodedata.normalize("NFKD", question.casefold())
    stripped = "".join(char for char in translated if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", " ", stripped).strip()


def plan_evidence(question: str) -> dict:
    """Derive a narrow relevance oracle from intent terms; abstain otherwise.

    A field must be selected *because the question asks for it*. The model is
    not told these fields. This rule planner is a bootstrap, not a replacement
    for future semantic analysis.
    """
    if not isinstance(question, str) or not question.strip() or len(question) > 2048:
        raise ValueError("Question must be nonempty and <= 2048 chars")
    q = _normalized(question)
    def contains(*terms: str) -> bool:
        return any(re.search(r"\b" + re.escape(term) + r"\b", q) for term in terms)

    # Unsafe propositions are not proven by a static call count.
    if contains("quebra", "quebrar", "quebraria", "impacto", "afetaria",
                "seguro", "garantia", "executa", "executar", "runtime",
                "impact", "break", "breaking", "guarantee", "safe"):
        return {"status": "ABSTAIN", "reason": "requires_runtime_or_impact_proof",
                "required_fields": []}
    if contains("todos", "todas", "every", "all", "completo", "completa",
                "exhaustivo", "exhaustiva"):
        return {"status": "ABSTAIN", "reason": "exhaustive_coverage_not_proven",
                "required_fields": []}

    selected: set[str] = set()
    if contains("assinatura", "parametros", "parametro", "argumentos",
                "signature", "parameters", "argument", "arguments"):
        selected.add("signature")
    if contains("onde", "localizacao", "localizado", "localizada",
                "arquivo", "definida", "definido", "where", "located",
                "definition", "defined", "file"):
        selected.update(("path", "line"))
    if contains("linha", "line"):
        selected.add("line")
    if contains("quantas", "quantos", "numero", "quantidade",
                "count", "how many"):
        # Only count when a call/reference term is also present.
        if contains("chamadas", "chamada", "chamam", "calls",
                    "call", "referencias", "references"):
            selected.add("direct_call_count")
    if contains("quem", "quais", "locais", "sites", "consumidores",
                "consumers", "callers", "chamadores"):
        if contains("chama", "chamam", "chamada", "chamadas", "calls",
                    "call", "referencias", "references", "usam", "usa", "uses"):
            selected.add("direct_call_sites")
    # A bare "calls?" request is underspecified; do not guess which aspect.
    if not selected:
        return {"status": "ABSTAIN", "reason": "unsupported_or_unrecognized_intent",
                "required_fields": []}
    return {"status": "PLANNED", "reason": "static_query_intent",
            "required_fields": [field for field in FIELD_ORDER if field in selected]}


def validate_dynamic_selection(evidence: dict, proposed: object, plan: dict) -> dict:
    """Separate model syntax, source grounding and *planned* relevance."""
    if plan["status"] != "PLANNED":
        return {"status": "ABSTAIN", "reason": plan["reason"],
                "selected_fields": [], "missing_required": []}
    # Bind the source snapshot on the trusted Gateway side. A model should
    # choose fields, NOT reproduce a long hash-like evidence identifier.
    # Legacy ID-bearing proposals are rejected in dynamic mode rather than
    # silently accepting any model-supplied identifier.
    if not isinstance(proposed, dict) or set(proposed) != {"selected_fields"}:
        return {"status": "REJECTED", "reason": "invalid_selection_shape", "selected_fields": []}
    fields = proposed["selected_fields"]
    if not isinstance(fields, list) or not 1 <= len(fields) <= len(FIELDS):
        return {"status": "REJECTED", "reason": "invalid_selected_fields", "selected_fields": []}
    if any(not isinstance(field, str) or field not in FIELDS or field not in evidence for field in fields):
        return {"status": "REJECTED", "reason": "unknown_field", "selected_fields": []}
    if len(set(fields)) != len(fields):
        return {"status": "REJECTED", "reason": "duplicate_field", "selected_fields": []}
    expected = set(plan["required_fields"])
    chosen = set(fields)
    missing = [field for field in FIELD_ORDER if field in expected - chosen]
    extra = [field for field in FIELD_ORDER if field in chosen - expected]
    if missing or extra:
        return {"status": "REJECTED", "reason": "selection_relevance_mismatch",
                "selected_fields": fields, "missing_required": missing,
                "unexpected_fields": extra}
    return {"status": "VERIFIED", "reason": "selection_matches_independent_plan",
            "selected_fields": fields, "missing_required": [], "unexpected_fields": [],
            "resolved_facts": {field: evidence[field] for field in FIELD_ORDER if field in chosen}}


def selection_prompt(question: str, evidence_id: str | None = None) -> str:
    """Provide a catalog, never source IDs, canonical values or the answer key."""
    import json

    return (
        "Select evidence fields required to answer the QUESTION. "
        "Return exactly one JSON object with one key: selected_fields, "
        "an array of distinct names from CATALOG. No evidence_id, source "
        "values, explanations, markdown or other properties. "
        "Select the minimum fields necessary to answer this question. "
        "If no field is relevant, return {\\\"selected_fields\\\":[]}. "
        "CATALOG=" + json.dumps(FIELDS, ensure_ascii=False)
        + "\\nQUESTION=" + question
    )
