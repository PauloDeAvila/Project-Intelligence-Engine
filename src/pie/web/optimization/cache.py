"""Session-bound bounded cache; cached values are never proof of validity."""

from __future__ import annotations

from collections import OrderedDict
from threading import RLock

from ..contracts import WebStateError
from .models import CacheKey


class PageCache:
    def __init__(self, *, max_entries: int = 256) -> None:
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or not 1 <= max_entries <= 4096:
            raise WebStateError("max_entries is outside the safe bound")
        self.max_entries = max_entries
        self._values: OrderedDict[CacheKey, object] = OrderedDict()
        self._lock = RLock()

    def get(self, key: CacheKey) -> object | None:
        if not isinstance(key, CacheKey):
            raise WebStateError("key must be a CacheKey")
        with self._lock:
            value = self._values.get(key)
            if value is not None:
                self._values.move_to_end(key)
            return value

    def put(self, key: CacheKey, value: object) -> None:
        if not isinstance(key, CacheKey):
            raise WebStateError("key must be a CacheKey")
        with self._lock:
            self._values[key] = value
            self._values.move_to_end(key)
            while len(self._values) > self.max_entries:
                self._values.popitem(last=False)

    def invalidate_session(self, session_id: str) -> int:
        with self._lock:
            keys = [key for key in self._values if key.session_id == session_id]
            for key in keys:
                self._values.pop(key, None)
            return len(keys)

    def invalidate_page(self, session_id: str, page_id: str) -> int:
        with self._lock:
            keys = [key for key in self._values if key.session_id == session_id and key.page_id == page_id]
            for key in keys:
                self._values.pop(key, None)
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


__all__ = ["PageCache"]
