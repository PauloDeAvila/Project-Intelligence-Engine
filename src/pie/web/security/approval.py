"""Explicit, bounded, one-time approvals for high-impact web actions."""

from __future__ import annotations

from dataclasses import replace
import threading
import time

from ..contracts import WebStateError
from .models import ApprovalRequest, RiskCategory


class ApprovalManager:
    def __init__(self, *, max_pending: int = 128, ttl_seconds: int = 120) -> None:
        if not isinstance(max_pending, int) or isinstance(max_pending, bool) or not 1 <= max_pending <= 1024:
            raise WebStateError("max_pending is outside the safe bound")
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= 300:
            raise WebStateError("ttl_seconds is outside the safe bound")
        self.max_pending = max_pending
        self.ttl_seconds = ttl_seconds
        self._requests: dict[str, ApprovalRequest] = {}
        self._expires: dict[str, float] = {}
        self._lock = threading.Lock()
        self._next_id = 1

    def request(
        self,
        *,
        fingerprint: str,
        session_id: str,
        page_id: str,
        snapshot_id: str,
        target_ref: str | None,
        categories: tuple[RiskCategory, ...],
    ) -> ApprovalRequest:
        with self._lock:
            self._purge_expired()
            if len(self._requests) >= self.max_pending:
                raise WebStateError("approval queue is full")
            request_id = f"approval-{self._next_id:06d}"
            self._next_id += 1
            item = ApprovalRequest(request_id, fingerprint, session_id, page_id, snapshot_id, target_ref, categories)
            self._requests[request_id] = item
            self._expires[request_id] = time.monotonic() + self.ttl_seconds
            return item

    def approve(self, request_id: str) -> ApprovalRequest:
        with self._lock:
            item = self._get(request_id)
            if item.status != "PENDING":
                raise WebStateError("approval request is not pending")
            updated = replace(item, status="APPROVED")
            self._requests[request_id] = updated
            return updated

    def reject(self, request_id: str) -> ApprovalRequest:
        with self._lock:
            item = self._get(request_id)
            if item.status != "PENDING":
                raise WebStateError("approval request is not pending")
            updated = replace(item, status="REJECTED")
            self._requests[request_id] = updated
            return updated

    def revoke(self, request_id: str) -> ApprovalRequest:
        with self._lock:
            item = self._get(request_id)
            if item.status in {"CONSUMED", "REJECTED"}:
                raise WebStateError("approval request cannot be revoked")
            updated = replace(item, status="REJECTED")
            self._requests[request_id] = updated
            return updated

    def consume(self, request_id: str, *, fingerprint: str) -> bool:
        with self._lock:
            self._purge_expired()
            item = self._get(request_id)
            if item.status != "APPROVED" or item.fingerprint != fingerprint:
                return False
            self._requests[request_id] = replace(item, status="CONSUMED")
            self._expires.pop(request_id, None)
            return True

    def _get(self, request_id: str) -> ApprovalRequest:
        if not isinstance(request_id, str) or request_id not in self._requests:
            raise WebStateError("approval request was not found")
        return self._requests[request_id]

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = [request_id for request_id, deadline in self._expires.items() if deadline <= now]
        for request_id in expired:
            self._requests.pop(request_id, None)
            self._expires.pop(request_id, None)


__all__ = ["ApprovalManager"]
