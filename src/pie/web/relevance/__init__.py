"""Quantified Web Context and deterministic relevance filtering."""

from .gate import WebRelevanceGate
from .models import OmissionRecord, QuantifiedWebContext, ReductionResult, ScoredCandidate
from .ranker import CandidateRanker
from .reducer import RedundancyReducer
from .scorer import RelevanceScorer
from .threshold import DecisionThresholdController

__all__ = [
    "CandidateRanker",
    "DecisionThresholdController",
    "OmissionRecord",
    "QuantifiedWebContext",
    "RedundancyReducer",
    "ReductionResult",
    "RelevanceScorer",
    "ScoredCandidate",
    "WebRelevanceGate",
]
