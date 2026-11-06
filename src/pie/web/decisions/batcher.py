"""Batch ambiguous candidates while minimizing and authorizing external input."""

from __future__ import annotations

from collections.abc import Mapping

from ..contracts import WebStateError
from ..relevance.models import QuantifiedWebContext
from ..security.sensitive import SensitiveDataFilter
from .classifier import ClassifierAdapter, validate_classifier_result
from .models import DecisionBatch, DecisionFeature, DecisionRoute, DecisionSource, SemanticDecision
from .router import FallbackRouter
from .uncertainty import UncertaintyEstimator


class DecisionBatcher:
    def __init__(
        self,
        *,
        estimator: UncertaintyEstimator | None = None,
        router: FallbackRouter | None = None,
        sensitive_filter: SensitiveDataFilter | None = None,
    ) -> None:
        self.estimator = estimator or UncertaintyEstimator()
        self.router = router or FallbackRouter()
        self.sensitive_filter = sensitive_filter or SensitiveDataFilter()

    def build(self, context: QuantifiedWebContext, *, max_features: int = 16) -> DecisionBatch:
        if not isinstance(context, QuantifiedWebContext) or not 1 <= max_features <= 16:
            raise WebStateError("invalid decision batch input")
        features: list[DecisionFeature] = []
        for scored in context.selected[:max_features]:
            classification = self.sensitive_filter.classify_candidate(scored.candidate)
            sensitive = bool(classification.categories and any(item.value in {"credentials", "financial", "page_instruction"} for item in classification.categories))
            label = "[REDACTED]" if sensitive else scored.candidate.accessible_name[:128]
            features.append(DecisionFeature(scored.candidate.ref, label, scored.candidate.role, scored.candidate.region, len(scored.candidate.available_actions), scored.score, sensitive))
        if not features:
            raise WebStateError("decision batch cannot be empty")
        return DecisionBatch(context.snapshot_id, context.query, tuple(features), external_safe=not any(item.sensitive for item in features))

    def decide(
        self,
        context: QuantifiedWebContext,
        *,
        classifier: ClassifierAdapter | None = None,
        allow_external: bool = False,
    ) -> tuple[SemanticDecision, ...]:
        batch = self.build(context)
        local: list[SemanticDecision] = []
        external_refs: list[str] = []
        for scored, feature in zip(context.selected, batch.features):
            uncertainty = self.estimator.estimate(context, scored)
            confidence = max(0.0, 1.0 - uncertainty)
            route = self.router.route(
                confidence=confidence,
                sensitive=feature.sensitive,
                classifier_available=classifier is not None,
                allow_external=allow_external and batch.external_safe,
            )
            if route is DecisionRoute.OPTIONAL_CLASSIFIER:
                external_refs.append(feature.ref)
                local.append(SemanticDecision(feature.ref, route, DecisionSource.FALLBACK, confidence, "external_classification_optional"))
            elif route is DecisionRoute.BLOCKED:
                local.append(SemanticDecision(feature.ref, route, DecisionSource.FALLBACK, confidence, "sensitive_context_blocked"))
            elif route is DecisionRoute.LOCAL:
                local.append(SemanticDecision(feature.ref, route, DecisionSource.LOCAL, confidence, "local_confidence_sufficient"))
            else:
                local.append(SemanticDecision(feature.ref, route, DecisionSource.FALLBACK, confidence, "more_context_required"))
        if external_refs and classifier is not None and allow_external and batch.external_safe:
            external = validate_classifier_result(batch, classifier.classify(batch))
            by_ref = {item.ref: item for item in external}
            local = [by_ref.get(item.ref, item) if item.ref in external_refs else item for item in local]
        return tuple(local)


__all__ = ["DecisionBatcher"]
