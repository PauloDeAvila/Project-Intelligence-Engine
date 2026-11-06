"""PIE Web Intelligence contracts and the optional browser connector.

The browser package is intentionally lazy: importing ``pie.web`` loads only
dependency-free contracts. Browser classes are loaded when one of their names
is requested explicitly.
"""

from typing import TYPE_CHECKING

from .contracts import (
    ActionResult,
    ActionStatus,
    BrowserSession,
    ContentTrust,
    ElementSupport,
    ElementCandidate,
    ElementReference,
    ExecutionState,
    PageSnapshot,
    ReferenceState,
    SnapshotState,
    SessionState,
    TaskIntent,
    VerificationState,
    WEB_CONTRACT_SCHEMA,
    WebMetric,
    WebStateError,
    MAX_PAGE_ELEMENTS,
    normalize_origin,
)

_BROWSER_EXPORTS = frozenset(
    {
        "BrowserAdapter",
        "BrowserAdapterError",
        "BrowserConnector",
        "BrowserConnectorError",
        "BrowserHealthMonitor",
        "BrowserPage",
        "BrowserFrame",
        "ConnectionResult",
        "HealthResult",
        "FrameObservation",
        "NavigationController",
        "PageObservation",
        "PlaywrightBrowserAdapter",
        "SessionManager",
    }
)
_SNAPSHOT_EXPORTS = frozenset(
    {
        "AccessibilityExtractor",
        "AccessibilityNode",
        "ElementRecord",
        "ElementRegistry",
        "DOMExtractionResult",
        "ExtractionResult",
        "NormalizationResult",
        "PageStateTracker",
        "PlaywrightDOMExtractor",
        "SnapshotNormalizer",
        "TrackingResult",
    }
)
_INDEXING_EXPORTS = frozenset(
    {
        "CandidateExtractor",
        "LocalWebSearch",
        "RegionIndex",
        "RegionIndexer",
        "SearchDocument",
        "SearchMatch",
        "SearchResponse",
        "SemanticRoleMatcher",
        "tokenize",
    }
)
_RELEVANCE_EXPORTS = frozenset(
    {
        "CandidateRanker",
        "DecisionThresholdController",
        "OmissionRecord",
        "QuantifiedWebContext",
        "RedundancyReducer",
        "ReductionResult",
        "RelevanceScorer",
        "ScoredCandidate",
        "WebRelevanceGate",
    }
)
_SECURITY_EXPORTS = frozenset(
    {
        "ApprovalManager",
        "ApprovalRequest",
        "OriginCheck",
        "OriginGuard",
        "PolicyEngine",
        "PolicyEvaluation",
        "RiskAssessment",
        "RiskCategory",
        "RiskLevel",
        "RiskScorer",
        "SecurityDecision",
        "SecurityDecisionStatus",
        "SecurityGate",
        "SensitiveClassification",
        "SensitiveDataFilter",
    }
)
_EVIDENCE_EXPORTS = frozenset(
    {
        "BudgetAllocation",
        "ContextBudgetController",
        "ContextExpansionFallback",
        "EvidenceItem",
        "EvidenceOmission",
        "EvidenceProvenance",
        "ExpansionPlan",
        "OmissionLedger",
        "PermissionState",
        "WebEvidencePack",
        "WebEvidencePackBuilder",
    }
)
_ACTIONS_EXPORTS = frozenset(
    {
        "ActionDriver",
        "ActionExecutor",
        "ActionPlan",
        "DriverOutcome",
        "PostActionVerifier",
        "PreflightValidator",
        "RecoveryAction",
        "RecoveryController",
        "RecoveryPlan",
        "ActionPlanner",
    }
)


def __getattr__(name: str):
    if name in _BROWSER_EXPORTS:
        from . import browser

        value = getattr(browser, name)
    elif name in _SNAPSHOT_EXPORTS:
        from . import snapshots

        value = getattr(snapshots, name)
    elif name in _INDEXING_EXPORTS:
        from . import indexing

        value = getattr(indexing, name)
    elif name in _RELEVANCE_EXPORTS:
        from . import relevance

        value = getattr(relevance, name)
    elif name in _SECURITY_EXPORTS:
        from . import security

        value = getattr(security, name)
    elif name in _EVIDENCE_EXPORTS:
        from . import evidence

        value = getattr(evidence, name)
    elif name in _ACTIONS_EXPORTS:
        from . import actions

        value = getattr(actions, name)
    else:
        raise AttributeError(name)
    globals()[name] = value
    return value


if TYPE_CHECKING:
    from .browser import (
        BrowserAdapter,
        BrowserAdapterError,
        BrowserConnector,
        BrowserConnectorError,
        BrowserHealthMonitor,
        BrowserPage,
        BrowserFrame,
        ConnectionResult,
        HealthResult,
        FrameObservation,
        NavigationController,
        PageObservation,
        PlaywrightBrowserAdapter,
        SessionManager,
    )
    from .snapshots import (
        AccessibilityExtractor,
        AccessibilityNode,
        ElementRecord,
        ElementRegistry,
        DOMExtractionResult,
        ExtractionResult,
        NormalizationResult,
        PageStateTracker,
        PlaywrightDOMExtractor,
        SnapshotNormalizer,
        TrackingResult,
    )
    from .indexing import (
        CandidateExtractor,
        LocalWebSearch,
        RegionIndex,
        RegionIndexer,
        SearchDocument,
        SearchMatch,
        SearchResponse,
        SemanticRoleMatcher,
        tokenize,
    )
    from .relevance import (
        CandidateRanker,
        DecisionThresholdController,
        OmissionRecord,
        QuantifiedWebContext,
        RedundancyReducer,
        ReductionResult,
        RelevanceScorer,
        ScoredCandidate,
        WebRelevanceGate,
    )
    from .security import (
        ApprovalManager,
        ApprovalRequest,
        OriginCheck,
        OriginGuard,
        PolicyEngine,
        PolicyEvaluation,
        RiskAssessment,
        RiskCategory,
        RiskLevel,
        RiskScorer,
        SecurityDecision,
        SecurityDecisionStatus,
        SecurityGate,
        SensitiveClassification,
        SensitiveDataFilter,
    )
    from .evidence import (
        BudgetAllocation,
        ContextBudgetController,
        ContextExpansionFallback,
        EvidenceItem,
        EvidenceOmission,
        EvidenceProvenance,
        ExpansionPlan,
        OmissionLedger,
        PermissionState,
        WebEvidencePack,
        WebEvidencePackBuilder,
    )
    from .actions import (
        ActionDriver,
        ActionExecutor,
        ActionPlan,
        ActionPlanner,
        DriverOutcome,
        PostActionVerifier,
        PreflightValidator,
        RecoveryAction,
        RecoveryController,
        RecoveryPlan,
    )

__all__ = [
    "ActionResult",
    "ActionStatus",
    "BrowserSession",
    "ContentTrust",
    "ElementSupport",
    "ElementCandidate",
    "ElementReference",
    "ExecutionState",
    "PageSnapshot",
    "ReferenceState",
    "SnapshotState",
    "SessionState",
    "TaskIntent",
    "VerificationState",
    "WEB_CONTRACT_SCHEMA",
    "WebMetric",
    "WebStateError",
    "MAX_PAGE_ELEMENTS",
    "normalize_origin",
    "BrowserAdapter",
    "BrowserAdapterError",
    "BrowserConnector",
    "BrowserConnectorError",
    "BrowserHealthMonitor",
    "BrowserPage",
    "BrowserFrame",
    "ConnectionResult",
    "HealthResult",
    "FrameObservation",
    "NavigationController",
    "PageObservation",
    "PlaywrightBrowserAdapter",
    "SessionManager",
    "AccessibilityExtractor",
    "AccessibilityNode",
    "ElementRecord",
    "ElementRegistry",
    "DOMExtractionResult",
    "ExtractionResult",
    "NormalizationResult",
    "PageStateTracker",
    "PlaywrightDOMExtractor",
    "SnapshotNormalizer",
    "TrackingResult",
    "CandidateExtractor",
    "LocalWebSearch",
    "RegionIndex",
    "RegionIndexer",
    "SearchDocument",
    "SearchMatch",
    "SearchResponse",
    "SemanticRoleMatcher",
    "tokenize",
    "CandidateRanker",
    "DecisionThresholdController",
    "OmissionRecord",
    "QuantifiedWebContext",
    "RedundancyReducer",
    "ReductionResult",
    "RelevanceScorer",
    "ScoredCandidate",
    "WebRelevanceGate",
    "ApprovalManager",
    "ApprovalRequest",
    "OriginCheck",
    "OriginGuard",
    "PolicyEngine",
    "PolicyEvaluation",
    "RiskAssessment",
    "RiskCategory",
    "RiskLevel",
    "RiskScorer",
    "SecurityDecision",
    "SecurityDecisionStatus",
    "SecurityGate",
    "SensitiveClassification",
    "SensitiveDataFilter",
    "BudgetAllocation",
    "ContextBudgetController",
    "ContextExpansionFallback",
    "EvidenceItem",
    "EvidenceOmission",
    "EvidenceProvenance",
    "ExpansionPlan",
    "OmissionLedger",
    "PermissionState",
    "WebEvidencePack",
    "WebEvidencePackBuilder",
    "ActionDriver",
    "ActionExecutor",
    "ActionPlan",
    "ActionPlanner",
    "DriverOutcome",
    "PostActionVerifier",
    "PreflightValidator",
    "RecoveryAction",
    "RecoveryController",
    "RecoveryPlan",
]
