"""Immutable, evidence-backed adjacency snapshots for PIE's verified reference graph.

Edges use resolver binding keys rather than equal-looking names. SQLite source
is authoritative; the snapshot is replaced only following a successful index
refresh. Unresolved references never become verified graph edges.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True)
class Edge:
    source_path: str
    source_symbol: str | None
    target_path: str
    target_symbol: str
    target_binding_key: str
    source_line: int
    target_line: int | None

    def as_dict(self):
        return {
            "source_path": self.source_path,
            "consumer": self.source_symbol,
            "target_path": self.target_path,
            "target": self.target_symbol,
            "source_line": self.source_line,
            "target_line": self.target_line,
            "resolution": "verified",
        }


class VerifiedGraph:
    """Bounded reverse and forward traversal without speculative dependencies."""

    def __init__(self, rows):
        reverse = defaultdict(list)
        forward = defaultdict(list)
        for row in rows:
            edge = Edge(**dict(row))
            reverse[(edge.target_path, edge.target_symbol)].append(edge)
            if edge.source_symbol:
                forward[(edge.source_path, edge.source_symbol)].append(edge)
        self.reverse = {k: tuple(sorted(v, key=lambda e: (e.source_path, e.source_line)))
                        for k, v in reverse.items()}
        self.forward = {k: tuple(sorted(v, key=lambda e: (e.target_path, e.target_symbol)))
                        for k, v in forward.items()}
        self.edge_count = sum(len(v) for v in reverse.values())

    @classmethod
    def from_connection(cls, conn: sqlite3.Connection):
        # Binding existence is required: never trust a stale target annotation.
        rows = conn.execute("""
            SELECT src.path AS source_path,
                   u.origin_symbol AS source_symbol,
                   target.path AS target_path,
                   d.qualified_name AS target_symbol,
                   d.binding_key AS target_binding_key,
                   u.line AS source_line,
                   u.target_line AS target_line
            FROM usages u
            JOIN files src ON src.id=u.file_id
            JOIN definitions d ON d.binding_key=u.target_binding_key
            JOIN files target ON target.id=d.file_id
            WHERE u.resolution='verified'
              AND u.target_binding_key IS NOT NULL
              AND u.target_path=target.path
              AND u.target_name=d.name
              AND (u.target_line IS NULL OR u.target_line=d.start_line)
            ORDER BY src.path,u.line,d.qualified_name
        """).fetchall()
        return cls(rows)

    def consumers(self, path: str, symbol: str, *, depth: int = 1, limit: int = 100):
        if not 0 <= depth <= 5 or not 1 <= limit <= 500:
            raise ValueError("Invalid depth/limit")
        start = (path, symbol)
        visited = {start}
        queue = deque([(start, 0)])
        results = []
        while queue and len(results) < limit:
            node, level = queue.popleft()
            if level >= depth:
                continue
            for edge in self.reverse.get(node, ()):
                item = edge.as_dict()
                item["depth"] = level + 1
                if item not in results:
                    results.append(item)
                if len(results) == limit:
                    break
                if edge.source_symbol:
                    nxt = (edge.source_path, edge.source_symbol)
                    if nxt not in visited:
                        visited.add(nxt)
                        queue.append((nxt, level + 1))
        return {"edges": results, "truncated": bool(queue) or len(results) >= limit,
                "verified": True}

    def dependencies(self, path: str, symbol: str, *, limit: int = 100):
        if not 1 <= limit <= 500:
            raise ValueError("Invalid limit")
        edges = self.forward.get((path, symbol), ())
        return {"edges": [e.as_dict() for e in edges[:limit]],
                "truncated": len(edges) > limit, "verified": True}
