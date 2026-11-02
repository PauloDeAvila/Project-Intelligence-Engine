"""Unified MCP retrieval backed by one persistent WarmContextService.

All answers remain source-grounded. This is deterministic retrieval, not LLM inference.
"""
from __future__ import annotations

from pie.retrieval.warm import WarmContextService


class MCPContextEngine:
    def __init__(self, root):
        self.service = WarmContextService(root)

    def close(self):
        self.service.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def query(self, query: str, *, limit: int = 5, max_chars: int = 12000, mode: str = "responsibility"):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a nonempty string")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("limit must be 1..20")
        if type(max_chars) is not int or not 500 <= max_chars <= 200000:
            raise ValueError("max_chars must be 500..200000")
        if mode not in ("responsibility", "navigation", "impact"):
            raise ValueError("Unsupported query mode")
        if mode == "navigation":
            result = self.service.query(query, limit=limit, max_chars=max_chars, include_body=False)
            return {"query": query, "mode": mode, "cache_hit": result["cache_hit"],
                    "result": result["result"]}
        pack = self.service.task_pack(query, limit=limit, max_chars=max_chars)
        if mode == "impact":
            return {"query": query, "mode": mode, "pack": pack,
                    "caveat": "Verified consumers are evidence-backed potential impacts; not all downstream effects can be proven."}
        return {"query": query, "mode": mode, "pack": pack}
