"""Explainable local relevance scoring; no model or network calls."""

from __future__ import annotations

from ..contracts import ElementCandidate, WebStateError
from ..indexing.extractor import tokenize
from ..indexing.roles import SemanticRoleMatcher
from .models import ScoredCandidate


_SAFETY_TERMS = frozenset(
    {
        "alert",
        "alerta",
        "critical",
        "erro",
        "error",
        "warning",
        "aviso",
        "security",
        "seguranca",
        "segurança",
        "password",
        "senha",
        "verification",
        "verificacao",
        "verificação",
        "required",
        "obrigatorio",
        "obrigatório",
    }
)


class RelevanceScorer:
    """Score a candidate using bounded lexical and structural signals."""

    def __init__(self, *, role_matcher: SemanticRoleMatcher | None = None) -> None:
        self.role_matcher = role_matcher or SemanticRoleMatcher()

    def score(
        self,
        candidate: ElementCandidate,
        *,
        ordinal: int,
        query: str,
        semantic_role: str | None = None,
        region: str | None = None,
    ) -> ScoredCandidate:
        if not isinstance(candidate, ElementCandidate):
            raise WebStateError("candidate must be an ElementCandidate")
        if not isinstance(query, str) or not query.strip() or len(query) > 256:
            raise WebStateError("query is outside the safe bound")
        if query.strip().startswith(("#", ".", "[", ">")) or "]" in query:
            raise WebStateError("selector-like queries are not accepted")
        if semantic_role is not None:
            targets = self.role_matcher.targets_for(semantic_role)
        else:
            targets = frozenset()
        query_terms = set(tokenize(query))
        name_terms = set(tokenize(candidate.accessible_name))
        region_terms = set(tokenize(candidate.region or ""))
        matched = query_terms.intersection(name_terms)
        coverage = len(matched) / max(1, len(query_terms))
        inferred = self.role_matcher.infer(query)
        role_hit = candidate.role in targets or any(
            candidate.role in self.role_matcher.targets_for(role) for role in inferred
        ) or candidate.role in query_terms
        region_hit = region is not None and candidate.region is not None and candidate.region.casefold() == region.casefold()
        safety_hit = bool((_SAFETY_TERMS.intersection(name_terms)) or (_SAFETY_TERMS.intersection(region_terms)))
        reasons = [f"name_coverage:{coverage:.2f}"]
        score = 0.55 * coverage
        if role_hit:
            score += 0.20
            reasons.append("semantic_role_match")
        if region_hit:
            score += 0.10
            reasons.append("region_match")
        if candidate.visible:
            score += 0.05
            reasons.append("visible")
        if candidate.enabled:
            score += 0.05
            reasons.append("enabled")
        if candidate.available_actions:
            score += 0.05
            reasons.append("actionable")
        if candidate.support.value == "UNSUPPORTED":
            score *= 0.5
            reasons.append("unsupported")
        if safety_hit:
            score = max(score, 0.80)
            reasons.append("safety_signal")
        estimated_chars = min(4096, 64 + len(candidate.accessible_name) * 2 + len(candidate.region or "") * 2)
        return ScoredCandidate(
            candidate=candidate,
            ordinal=ordinal,
            score=round(min(1.0, score), 6),
            reasons=tuple(reasons),
            protected=safety_hit,
            estimated_chars=estimated_chars,
        )


__all__ = ["RelevanceScorer"]
