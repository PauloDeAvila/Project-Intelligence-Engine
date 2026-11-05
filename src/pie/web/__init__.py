"""Contracts for the isolated PIE web subsystem.

Phase 0 deliberately contains no browser, network, or third-party runtime
dependency.  Adapters and execution are introduced only after these contracts
are reviewed and verified.
"""

from .contracts import (
    ActionResult,
    ActionStatus,
    BrowserSession,
    ContentTrust,
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
    normalize_origin,
)

__all__ = [
    "ActionResult",
    "ActionStatus",
    "BrowserSession",
    "ContentTrust",
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
    "normalize_origin",
]
