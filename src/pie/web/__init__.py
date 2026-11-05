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


def __getattr__(name: str):
    if name not in _BROWSER_EXPORTS:
        raise AttributeError(name)
    from . import browser

    value = getattr(browser, name)
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
]
