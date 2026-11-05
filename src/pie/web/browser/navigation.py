"""Allowlisted navigation for an established browser session."""

from __future__ import annotations

from .connector import BrowserConnector, ConnectionResult


class NavigationController:
    """Performs navigation only after exact-origin authorization."""

    def __init__(self, connector: BrowserConnector) -> None:
        self._connector = connector

    def navigate(self, session_id: str, url: str) -> ConnectionResult:
        return self._connector.navigate(session_id, url)


__all__ = ["NavigationController"]
