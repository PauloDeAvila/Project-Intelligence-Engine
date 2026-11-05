"""Browser connector subsystem for PIE Web Intelligence."""

from .adapter import BrowserAdapter, BrowserAdapterError, BrowserFrame, BrowserPage, PlaywrightBrowserAdapter
from .connector import (
    BrowserConnector,
    BrowserConnectorError,
    ConnectionResult,
    FrameObservation,
    PageObservation,
    SessionManager,
)
from .health import BrowserHealthMonitor, HealthResult
from .navigation import NavigationController

__all__ = [
    "BrowserAdapter",
    "BrowserAdapterError",
    "BrowserHealthMonitor",
    "BrowserConnector",
    "BrowserConnectorError",
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
