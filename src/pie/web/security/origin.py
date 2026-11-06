"""Exact-origin and session-bound destination validation."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

from ..contracts import BrowserSession, PageSnapshot, WebStateError, normalize_origin


@dataclass(frozen=True, slots=True)
class OriginCheck:
    allowed: bool
    origin: str
    reason_code: str


class OriginGuard:
    """Reject credentials, wildcards, cross-origin destinations and session drift."""

    def check(
        self,
        session: BrowserSession,
        snapshot: PageSnapshot,
        *,
        target_url: str | None = None,
    ) -> OriginCheck:
        if not isinstance(session, BrowserSession) or not isinstance(snapshot, PageSnapshot):
            raise WebStateError("session and snapshot are required")
        if session.session_id != snapshot.session_id or session.current_page_id != snapshot.page_id:
            return OriginCheck(False, snapshot.origin, "session_page_mismatch")
        if not session.allows(snapshot.origin):
            return OriginCheck(False, snapshot.origin, "origin_not_allowed")
        if target_url is None:
            return OriginCheck(True, snapshot.origin, "origin_allowed")
        try:
            target_origin = normalize_origin(target_url)
        except WebStateError:
            return OriginCheck(False, snapshot.origin, "invalid_destination")
        try:
            query_keys = {key.casefold().replace("-", "_") for key, _ in parse_qsl(urlsplit(target_url).query, keep_blank_values=True)}
        except ValueError:
            return OriginCheck(False, target_origin, "invalid_destination")
        if query_keys & {"password", "token", "api_key", "authorization", "cookie", "secret", "session"}:
            return OriginCheck(False, target_origin, "sensitive_destination")
        if not session.allows(target_url):
            return OriginCheck(False, target_origin, "origin_not_allowed")
        return OriginCheck(True, target_origin, "origin_allowed")


__all__ = ["OriginCheck", "OriginGuard"]
