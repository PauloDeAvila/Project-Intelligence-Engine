"""Persistent PIE warm service (JSON Lines over stdin/stdout).

Protocol is intentionally local: no TCP listener, authentication surface or
remote code execution. This is a correctness-first daemon foundation, not
a claim of sub-millisecond retrieval.
"""
from __future__ import annotations

from collections import OrderedDict
import json
from pathlib import Path
import sys
from typing import TextIO

from pie.indexing.indexer import index_project
from pie.retrieval.intelligence import smart_context
from pie.storage.database import connect
from pie.retrieval.fts import search_fts


class WarmContextService:
    def __init__(self, root: Path, *, cache_size: int = 128):
        if not 1 <= cache_size <= 2048:
            raise ValueError("cache_size out of range")
        self.root = root.resolve()
        self.db_path = self.root / ".pie" / "index.sqlite3"
        if not self.db_path.is_file():
            raise ValueError("Run pie index first")
        self.cache_size = cache_size
        self._cache: OrderedDict[tuple, dict] = OrderedDict()
        self._connection = connect(self.db_path)
        self._generation = self._snapshot()
        self._warm()

    def _snapshot(self) -> tuple:
        """Cheap index-generation fingerprint; not a filesystem integrity proof."""
        rows = self._connection.execute(
            "SELECT path,sha256 FROM files ORDER BY path"
        ).fetchall()
        state = self._connection.execute(
            "SELECT value FROM metadata WHERE key='index_state'"
        ).fetchone()
        return (state[0] if state else "UNINDEXED",
                tuple((r["path"], r["sha256"]) for r in rows))

    def _warm(self) -> None:
        self._connection.execute("SELECT COUNT(*) FROM symbols").fetchone()
        self._connection.execute("SELECT COUNT(*) FROM symbol_docs").fetchone()
        self._connection.execute("SELECT COUNT(*) FROM usages WHERE resolution='verified'").fetchone()

    def refresh(self) -> dict:
        """Reindex changed files and invalidate dependent cached responses."""
        report = index_project(self.root)
        generation = self._snapshot()
        if generation != self._generation:
            self._cache.clear()
            self._generation = generation
            self._warm()
        return {"index": report, "cached_queries": len(self._cache)}

    def query(self, question: str, *, limit: int = 8, max_chars: int = 12000,
              include_body: bool = False) -> dict:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Nonempty query required")
        # Correctness-first: incremental scan before cached delivery.
        # This scan is outside a future separately measured warm-hit fast path.
        self.refresh()
        key = (question, limit, max_chars, include_body)
        if key in self._cache:
            # Source changes after last refresh are caught above. Index state
            # may be PARTIAL; never cache results reporting stale source.
            value = self._cache.pop(key)
            self._cache[key] = value
            return {"cache_hit": True, "result": value}
        value = smart_context(self.root, question, limit=limit,
                              max_chars=max_chars, include_body=include_body)
        if value["context_state"] == "CURRENT" and not value["diagnostics"]:
            self._cache[key] = value
            if len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return {"cache_hit": False, "result": value}

    def search_candidates(self, question: str, limit: int = 50) -> dict:
        self.refresh()
        hits = search_fts(self._connection, question, limit=limit)
        return {"ids": [symbol_id for symbol_id, _ in hits], "count": len(hits)}

    def close(self):
        self._cache.clear()
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def serve(root: Path, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout):
    with WarmContextService(root) as service:
        for line in stdin:
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise ValueError("JSON object required")
                method = request.get("method")
                if method == "query":
                    payload = service.query(request["query"],
                                            limit=request.get("limit", 8),
                                            max_chars=request.get("max_chars", 12000),
                                            include_body=request.get("include_body", False))
                elif method == "refresh":
                    payload = service.refresh()
                elif method == "candidates":
                    payload = service.search_candidates(request["query"],
                                                        limit=request.get("limit", 50))
                elif method == "ping":
                    payload = {"status": "ready", "cached_queries": len(service._cache)}
                else:
                    raise ValueError("Unknown method")
                response = {"ok": True, "data": payload}
            except (ValueError, KeyError, TypeError) as exc:
                response = {"ok": False, "error": type(exc).__name__, "message": str(exc)}
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()
