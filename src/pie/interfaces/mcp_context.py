"""Unified MCP FTS5/ranked-symbol/verified-graph retrieval with strict budgets."""
from __future__ import annotations

import json
import time

from pie.retrieval.warm import WarmContextService


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


class MCPContextEngine:
    def __init__(self, root):
        self.service = WarmContextService(root)

    def close(self):
        self.service.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def query(self, query: str, *, limit: int = 5, max_chars: int = 12000,
              mode: str = "responsibility"):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a nonempty string")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("limit must be 1..20")
        if type(max_chars) is not int or not 500 <= max_chars <= 200000:
            raise ValueError("max_chars must be 500..200000")
        if mode not in ("responsibility", "navigation", "impact"):
            raise ValueError("Unsupported query mode")
        started = time.perf_counter()
        if mode == "navigation":
            lookup = self.service.query(query, limit=limit, max_chars=max_chars,
                                        include_body=False)
            metrics = {"cache_hit": lookup["cache_hit"],
                       "reindexed": lookup["reindexed"],
                       "refresh_ms": lookup["refresh_ms"],
                       "search_ms": lookup["search_ms"],
                       "graph_ms": 0.0}
            output = {"query": query, "mode": mode, "cache_hit": lookup["cache_hit"],
                      "result": lookup["result"]}
            evidence = output["result"]["evidence"]
            omitted_owner = output["result"]
        else:
            lookup = self.service.task_pack(query, limit=limit, max_chars=max_chars,
                                            with_metrics=True)
            metrics = lookup["metrics"]
            output = {"query": query, "mode": mode, "pack": lookup["pack"]}
            evidence = output["pack"]["responsibilities"]
            omitted_owner = output["pack"]
            if mode == "impact":
                output["caveat"] = (
                    "Verified consumers indicate potential impact, not guaranteed runtime effects.")
        output["metrics"] = dict(metrics, serialization_ms=0.0, total_ms=0.0)
        # The total JSON payload, not just source snippets, must fit the budget.
        # Omit low-ranked complete evidence items; never slice source in mid-symbol.
        serialization_start = time.perf_counter()
        while _size(output) > max_chars and evidence:
            evidence.pop()
            omitted_owner["omitted"] += 1
            if omitted_owner.get("context_state") == "CURRENT":
                omitted_owner["context_state"] = "PARTIAL"
        output["metrics"]["serialization_ms"] = round(
            (time.perf_counter() - serialization_start) * 1000, 3)
        output["metrics"]["total_ms"] = round(
            (time.perf_counter() - started) * 1000, 3)
        # Final counter serialization can grow slightly when a time field gains digits.
        while _size(output) > max_chars and evidence:
            evidence.pop()
            omitted_owner["omitted"] += 1
            if omitted_owner.get("context_state") == "CURRENT":
                omitted_owner["context_state"] = "PARTIAL"
        if _size(output) > max_chars:
            raise ValueError("Query metadata exceeds max_chars; use a larger budget")
        return output
