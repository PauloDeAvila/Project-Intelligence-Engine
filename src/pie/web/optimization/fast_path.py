"""Cache-assisted local fast path with mandatory downstream validation."""

from __future__ import annotations

import hashlib

from ..contracts import PageSnapshot, WebStateError
from .cache import PageCache
from .models import CacheKey, FastPathResult
from .reuse import ElementReuseManager


class BrowserFastPath:
    def __init__(self, *, cache: PageCache | None = None, reuse: ElementReuseManager | None = None) -> None:
        self.cache = cache or PageCache()
        self.reuse = reuse or ElementReuseManager()

    def task_fingerprint(self, task: str) -> str:
        if not isinstance(task, str) or not task.strip() or len(task) > 256:
            raise WebStateError("task is outside the safe bound")
        return hashlib.sha256(task.casefold().strip().encode("utf-8")).hexdigest()

    def get_or_compute(self, snapshot: PageSnapshot, *, region: str, task: str, compute) -> FastPathResult:
        if not isinstance(snapshot, PageSnapshot) or snapshot.state.value in {"STALE", "BLOCKED"}:
            raise WebStateError("fast path requires a non-stale snapshot")
        if not isinstance(region, str) or not region or len(region) > 128:
            raise WebStateError("region is outside the safe bound")
        if not callable(compute):
            raise WebStateError("compute must be callable")
        key = CacheKey(snapshot.session_id, snapshot.page_id, snapshot.generation, region, self.task_fingerprint(task))
        cached = self.cache.get(key)
        if cached is not None:
            return FastPathResult(cached, True)
        value = compute()
        self.cache.put(key, value)
        return FastPathResult(value, False)

    def invalidate_after_delta(self, before: PageSnapshot, after: PageSnapshot) -> int:
        if before.session_id != after.session_id or before.page_id != after.page_id:
            raise WebStateError("snapshots must share session and page")
        return self.cache.invalidate_page(after.session_id, after.page_id)


__all__ = ["BrowserFastPath"]
