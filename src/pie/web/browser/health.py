"""Browser health monitoring without automatic unsafe recovery."""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import SessionState
from .connector import BrowserConnector


@dataclass(frozen=True, slots=True)
class HealthResult:
    session_id: str
    healthy: bool
    state: SessionState
    error_code: str | None = None


class BrowserHealthMonitor:
    """Checks liveness and marks failures degraded; it never auto-reconnects."""

    def __init__(self, connector: BrowserConnector) -> None:
        self._connector = connector

    def check(self, session_id: str) -> HealthResult:
        session = self._connector.session(session_id)
        if session.state is SessionState.CLOSED:
            return HealthResult(session_id, False, session.state, "session_closed")
        healthy, updated = self._connector.health_check(session_id)
        if healthy:
            return HealthResult(session_id, True, updated.state)
        return HealthResult(session_id, False, updated.state, "health_failed")


__all__ = ["BrowserHealthMonitor", "HealthResult"]
