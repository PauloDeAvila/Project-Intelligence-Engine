"""Persistent PIE warm service (JSON Lines over stdin/stdout).

Protocol is intentionally local: no TCP listener, authentication surface or
remote code execution. This is a correctness-first daemon foundation, not
a claim of sub-millisecond retrieval.
"""
from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
import threading
import json
from pathlib import Path
import sys
from typing import TextIO

from pie.indexing.indexer import index_project
from pie.retrieval.intelligence import smart_context
from pie.storage.database import connect
from pie.retrieval.fts import search_fts
from pie.graph.verified import VerifiedGraph
from pie.retrieval.packs import build_responsibility_pack
from pie.retrieval.predictive import predict_adjacent_queries


class WarmContextService:
    def __init__(self, root: Path, *, cache_size: int = 128, background_interval: float | None = None):
        if not 1 <= cache_size <= 2048:
            raise ValueError("cache_size out of range")
        self.root = root.resolve()
        self.db_path = self.root / ".pie" / "index.sqlite3"
        if not self.db_path.is_file():
            raise ValueError("Run pie index first")
        if background_interval is not None and background_interval < 0.1:
            raise ValueError('background_interval must be >= 0.1')
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._worker = None
        self._refresh_error = None
        self.cache_size = cache_size
        self._cache: OrderedDict[tuple, dict] = OrderedDict()
        self._connection = connect(self.db_path)
        self._generation = self._snapshot()
        self._verified_graph = VerifiedGraph([])
        self._warm()
        if background_interval is not None:
            self._worker = threading.Thread(target=self._background_loop, args=(background_interval,), daemon=True)
            self._worker.start()

    def _background_loop(self, interval):
        while not self._stop.wait(interval):
            try:
                with self._lock:
                    self.refresh()
                self._refresh_error = None
            except Exception as exc:
                self._refresh_error = type(exc).__name__
                with self._lock:
                    self._cache.clear()

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
        self._verified_graph = VerifiedGraph.from_connection(self._connection)

    def refresh(self) -> dict:
        """Reindex changed files and invalidate dependent cached responses."""
        report = index_project(self.root)
        generation = self._snapshot()
        if generation != self._generation:
            self._cache.clear()
            self._generation = generation
            self._warm()
        return {"index": report, "cached_queries": len(self._cache)}

    def _source_valid(self, result):
        # Each cached evidence is checked against the indexed SHA-256.
        paths = set(item["path"] for item in result.get("evidence", []))
        for path in paths:
            row = self._connection.execute(
                "SELECT sha256 FROM files WHERE path=?", (path,)
            ).fetchone()
            if not row:
                return False
            try:
                resolved = (self.root / path).resolve()
                if not resolved.is_relative_to(self.root):
                    return False
                if sha256(resolved.read_bytes()).hexdigest() != row[0]:
                    return False
            except OSError:
                return False
        return True

    def query(self, question: str, *, limit: int = 8, max_chars: int = 12000,
              include_body: bool = False) -> dict:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Nonempty query required")
        with self._lock:
            self.refresh()
            if self._refresh_error:
                raise RuntimeError("Background indexer failed: " + self._refresh_error)
            key = (question, limit, max_chars, include_body)
            if key in self._cache:
                value = self._cache[key]
                if self._source_valid(value):
                    self._cache.move_to_end(key)
                    return {"cache_hit": True, "result": value}
                self._cache.clear()
                self.refresh()
            value = smart_context(self.root, question, limit=limit,
                                  max_chars=max_chars, include_body=include_body)
            if value["context_state"] == "CURRENT" and not value["diagnostics"]:
                self._cache[key] = value
                if len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
            return {"cache_hit": False, "result": value}

    def task_pack(self, question: str, limit: int = 5, max_chars: int = 12000) -> dict:
        """Return a fully budgeted, strictly source-verified responsibility pack."""
        with self._lock:
            result = self.query(question, limit=limit, max_chars=max_chars,
                                include_body=True)["result"]
            return build_responsibility_pack(
                self.root, question, result, self._verified_graph,
                self._connection, max_chars=max_chars)

    def prefetch(self, queries: list[str]) -> dict:
        if not isinstance(queries, list) or len(queries) > 20 or any(
                not isinstance(q, str) or not q.strip() for q in queries):
            raise ValueError("Expected up to 20 nonempty queries")
        with self._lock:
            for query in queries:
                self.query(query, include_body=True, limit=5)
            return {"prepared": len(queries)}

    def predictive_prefetch(self, question: str, *, limit: int = 6) -> dict:
        """Prepare graph-neighbor queries with strict freshness checks."""
        with self._lock:
            pack = self.task_pack(question)
            proposed = predict_adjacent_queries(pack, limit=limit)
            if proposed:
                self.prefetch(proposed)
            return {"seed": question, "predicted": proposed,
                    "prepared": len(proposed), "consistency": "strict"}

    def search_candidates(self, question: str, limit: int = 50) -> dict:
        self.refresh()
        hits = search_fts(self._connection, question, limit=limit)
        return {"ids": [symbol_id for symbol_id, _ in hits], "count": len(hits)}

    def close(self):
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=10)
            if self._worker.is_alive():
                raise RuntimeError('Background worker still running')
        with self._lock:
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
                                            include_body=request.get("include_body", False),
)
                elif method == "task_pack":
                    payload = service.task_pack(request["query"],
                                                limit=request.get("limit", 5),
                                                max_chars=request.get("max_chars", 12000))
                elif method == "prefetch":
                    payload = service.prefetch(request["queries"])
                elif method == "predictive_prefetch":
                    payload = service.predictive_prefetch(request["query"],
                                                         limit=request.get("limit", 6))
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
