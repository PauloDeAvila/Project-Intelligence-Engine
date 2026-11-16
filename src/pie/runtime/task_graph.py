"""Bounded, deterministic task graph storage.

The graph stores only scalar metadata and hashes. It is intentionally
separate from the source index database so graph writes cannot corrupt code
indexing and can be used by multiple local agents safely.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SENSITIVE = (
    "prompt", "answer", "cookie", "password", "secret", "credential",
    "token", "api_key", "authorization",
)
_MAX_METADATA_KEYS = 32
_MAX_METADATA_STRING = 256
_MAX_METADATA_BYTES = 4096


class GraphValidationError(ValueError):
    """Input violates the bounded graph contract."""


class GraphConflictError(ValueError):
    """An existing node conflicts with the requested identity or metadata."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise GraphValidationError(f"invalid {field}")
    return value


def _sensitive(value: str) -> bool:
    lowered = value.lower()
    return any(fragment in lowered for fragment in _SENSITIVE)


def _metadata(value: object | None) -> tuple[str, str]:
    if value is None:
        value = {}
    if not isinstance(value, dict) or len(value) > _MAX_METADATA_KEYS:
        raise GraphValidationError("metadata must be a bounded object")
    normalized: dict[str, object] = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not key
            or "\x00" in key
            or len(key) > _MAX_METADATA_STRING
            or _sensitive(key)
        ):
            raise GraphValidationError("metadata contains an invalid key")
        if item is None or isinstance(item, bool) or isinstance(item, int):
            normalized[key] = item
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise GraphValidationError("metadata contains a non-finite number")
            normalized[key] = item
        elif isinstance(item, str):
            if "\x00" in item or len(item) > _MAX_METADATA_STRING or _sensitive(item):
                raise GraphValidationError("metadata contains an invalid string")
            normalized[key] = item
        else:
            raise GraphValidationError("metadata values must be scalar")
    encoded = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    )
    if len(encoded.encode("utf-8")) > _MAX_METADATA_BYTES:
        raise GraphValidationError("metadata exceeds its size limit")
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _verified_metadata(encoded: str, expected_hash: str) -> dict[str, object]:
    if not isinstance(encoded, str) or not isinstance(expected_hash, str):
        raise GraphValidationError("stored metadata is invalid")
    if hashlib.sha256(encoded.encode("utf-8")).hexdigest() != expected_hash:
        raise GraphValidationError("stored metadata hash mismatch")
    try:
        value = json.loads(encoded)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GraphValidationError("stored metadata is invalid") from exc
    canonical, digest = _metadata(value)
    if canonical != encoded or digest != expected_hash:
        raise GraphValidationError("stored metadata is not canonical")
    return value


class TaskGraphStore:
    """Thread-safe SQLite graph with idempotent writes and cycle detection."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        if self._path.is_symlink() or self._path.is_dir():
            raise GraphValidationError("graph path must be a regular file")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self._path, timeout=5, isolation_level=None, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._closed = False
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA busy_timeout=5000")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pie_task_graph_nodes (
                    task_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    metadata_sha256 TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    PRIMARY KEY (task_id, node_id)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pie_task_graph_edges (
                    task_id TEXT NOT NULL,
                    from_node TEXT NOT NULL,
                    to_node TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    PRIMARY KEY (task_id, from_node, to_node, relation)
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_pie_graph_nodes_task "
                "ON pie_task_graph_nodes(task_id, node_id)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_pie_graph_edges_task "
                "ON pie_task_graph_edges(task_id, from_node, to_node)"
            )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("task graph is closed")

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def add_node(
        self, task_id: str, node_id: str, kind: str,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        task_id = _identifier(task_id, "task_id")
        node_id = _identifier(node_id, "node_id")
        kind = _identifier(kind, "kind")
        encoded, digest = _metadata(metadata)
        with self._lock:
            self._ensure_open()
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT kind, metadata_sha256 FROM pie_task_graph_nodes "
                    "WHERE task_id=? AND node_id=?", (task_id, node_id)
                ).fetchone()
                if row is not None:
                    if row["kind"] != kind or row["metadata_sha256"] != digest:
                        raise GraphConflictError("node identity conflicts")
                    self._connection.execute("COMMIT")
                    return {"state": "EXISTING", "task_id": task_id, "node_id": node_id}
                self._connection.execute(
                    "INSERT INTO pie_task_graph_nodes "
                    "(task_id,node_id,kind,metadata_json,metadata_sha256,created_utc) "
                    "VALUES (?,?,?,?,?,?)",
                    (task_id, node_id, kind, encoded, digest, _utc()),
                )
                self._connection.execute("COMMIT")
                return {"state": "CREATED", "task_id": task_id, "node_id": node_id}
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def add_edge(
        self, task_id: str, from_node: str, to_node: str, relation: str,
    ) -> dict[str, object]:
        task_id = _identifier(task_id, "task_id")
        from_node = _identifier(from_node, "from_node")
        to_node = _identifier(to_node, "to_node")
        relation = _identifier(relation, "relation")
        if from_node == to_node:
            raise GraphValidationError("self-loop is not allowed")
        with self._lock:
            self._ensure_open()
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                count = self._connection.execute(
                    "SELECT COUNT(*) FROM pie_task_graph_nodes "
                    "WHERE task_id=? AND node_id IN (?,?)",
                    (task_id, from_node, to_node),
                ).fetchone()[0]
                if count != 2:
                    raise GraphValidationError("edge endpoint is unknown")
                row = self._connection.execute(
                    "SELECT 1 FROM pie_task_graph_edges WHERE task_id=? "
                    "AND from_node=? AND to_node=? AND relation=?",
                    (task_id, from_node, to_node, relation),
                ).fetchone()
                if row is not None:
                    self._connection.execute("COMMIT")
                    return {
                        "state": "EXISTING", "task_id": task_id,
                        "from_node": from_node, "to_node": to_node,
                        "relation": relation,
                    }
                self._connection.execute(
                    "INSERT INTO pie_task_graph_edges "
                    "(task_id,from_node,to_node,relation,created_utc) "
                    "VALUES (?,?,?,?,?)",
                    (task_id, from_node, to_node, relation, _utc()),
                )
                self._connection.execute("COMMIT")
                return {
                    "state": "CREATED", "task_id": task_id,
                    "from_node": from_node, "to_node": to_node,
                    "relation": relation,
                }
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def get_graph(self, task_id: str, limit: int = 100) -> dict[str, object]:
        task_id = _identifier(task_id, "task_id")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise GraphValidationError("limit must be 1..1000")
        with self._lock:
            self._ensure_open()
            nodes = self._connection.execute(
                "SELECT node_id,kind,metadata_json,metadata_sha256 FROM "
                "pie_task_graph_nodes WHERE task_id=? ORDER BY node_id LIMIT ?",
                (task_id, limit),
            ).fetchall()
            if not nodes:
                return {"state": "NOT_FOUND", "task_id": task_id, "nodes": [], "edges": []}
            node_ids = {row["node_id"] for row in nodes}
            edges = self._connection.execute(
                "SELECT from_node,to_node,relation FROM pie_task_graph_edges "
                "WHERE task_id=? ORDER BY from_node,to_node,relation LIMIT ?",
                (task_id, limit),
            ).fetchall()
        result_nodes = [
            {
                "node_id": row["node_id"], "kind": row["kind"],
                "metadata": _verified_metadata(row["metadata_json"], row["metadata_sha256"]),
            }
            for row in nodes
        ]
        result_edges = [
            {"from_node": row["from_node"], "to_node": row["to_node"], "relation": row["relation"]}
            for row in edges
            if row["from_node"] in node_ids and row["to_node"] in node_ids
        ]
        return {
            "state": "FOUND", "task_id": task_id,
            "nodes": result_nodes, "edges": result_edges,
            "complete": len(nodes) < limit,
        }

    def topological_order(self, task_id: str) -> dict[str, object]:
        task_id = _identifier(task_id, "task_id")
        with self._lock:
            self._ensure_open()
            node_rows = self._connection.execute(
                "SELECT node_id FROM pie_task_graph_nodes WHERE task_id=? ORDER BY node_id",
                (task_id,),
            ).fetchall()
            edge_rows = self._connection.execute(
                "SELECT from_node,to_node FROM pie_task_graph_edges "
                "WHERE task_id=? ORDER BY from_node,to_node", (task_id,)
            ).fetchall()
        nodes = [row["node_id"] for row in node_rows]
        if not nodes:
            return {"state": "NOT_FOUND", "task_id": task_id, "order": None}
        adjacency: dict[str, list[str]] = defaultdict(list)
        indegree = {node: 0 for node in nodes}
        for row in edge_rows:
            if row["from_node"] not in indegree or row["to_node"] not in indegree:
                raise GraphValidationError("graph contains an unknown edge endpoint")
            adjacency[row["from_node"]].append(row["to_node"])
            indegree[row["to_node"]] += 1
        ready = deque(sorted(node for node in nodes if indegree[node] == 0))
        order: list[str] = []
        while ready:
            current = ready.popleft()
            order.append(current)
            for target in sorted(adjacency[current]):
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
            ready = deque(sorted(ready))
        if len(order) != len(nodes):
            return {"state": "CYCLE", "task_id": task_id, "order": None}
        return {"state": "FOUND", "task_id": task_id, "order": order}


__all__ = ["GraphConflictError", "GraphValidationError", "TaskGraphStore"]
