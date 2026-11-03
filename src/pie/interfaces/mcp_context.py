"""Unified MCP FTS5/ranked-symbol/verified-graph retrieval with strict budgets."""
from __future__ import annotations

import json
import time

from pie.retrieval.warm import WarmContextService
from pie.retrieval.symbols import find_references


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
            if lookup["result"]["context_state"] not in ("CURRENT", "PARTIAL"):
                raise ValueError("Cannot return stale navigation evidence")
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
                # Exact reverse references are separate from the outgoing
                # conservative CALLS graph. Only expose hash-verified
                # syntactic calls, and do not label generic LOAD as a call.
                for item in evidence:
                    refs = find_references(self.service.root, item["symbol"], limit=100)
                    if refs.get("state") != "CURRENT":
                        item["direct_call_sites_state"] = "STALE"
                        continue
                    sites = [
                        {"path": ref["path"], "line": ref["line"],
                         "consumer_symbol": ref["consumer_symbol"],
                         "usage_kind": "direct_call"}
                        for ref in refs.get("references", [])
                        if ref.get("resolution") == "verified"
                        and ref.get("usage_kind") == "direct_call"
                        and any(d.get("path") == item["path"]
                                and d.get("line") == item["start_line"]
                                for d in refs.get("definitions", [])
                                if d.get("binding") == ref.get("target"))
                    ]
                    item["direct_call_sites"] = sites[:8]
                    if len(sites) > 8:
                        item["direct_call_sites_omitted"] = len(sites) - 8
                output["caveat"] = (
                    "Verified consumers indicate potential impact, not guaranteed runtime effects.")
        # Exact duplicate names are explicitly ambiguous even if ranking prefers one.
        exact = self.service._connection.execute(
            "SELECT COUNT(DISTINCT f.path || ':' || s.qualified_name) "
            "FROM symbols s JOIN files f ON f.id=s.file_id "
            "WHERE s.name=? COLLATE NOCASE OR s.qualified_name=? COLLATE NOCASE", (query.strip(), query.strip())
        ).fetchone()[0]
        output["lookup_status"] = ("AMBIGUOUS" if exact > 1 else
                                   "FOUND" if evidence else "NOT_FOUND")
        output["exact_match_count"] = exact
        # Never relabel unresolved references as verified or manufacture inferred edges.
        # Verified relationship details remain in each responsibility's verified_consumers.
        verified_count = sum(len(item.get("verified_consumers", [])) for item in evidence)
        inferred_count = 0
        unresolved_count = 0
        for item in evidence:
            if mode != "navigation":
                inferred_count += len(item.get("inferred_references", []))
                unresolved_count += len(item.get("unresolved_references", []))
            else:
                rows = self.service._connection.execute(
                    "SELECT u.resolution, COUNT(*) AS amount FROM usages u "
                    "JOIN files f ON f.id=u.file_id "
                    "WHERE f.path=? AND u.origin_symbol=? AND u.resolution<>'verified' "
                    "GROUP BY u.resolution",
                    (item["path"], item["symbol"])
                ).fetchall()
                inferred_count += sum(r["amount"] for r in rows if r["resolution"]=="inferred")
                unresolved_count += sum(r["amount"] for r in rows if r["resolution"]!="inferred")
        output["relation_classes"] = {
            "verified": verified_count,
            "inferred": inferred_count,
            "unresolved": unresolved_count,
        }
        output["metrics"] = dict(metrics, serialization_ms=0.0, total_ms=0.0)
        # The total JSON payload, not just source snippets, must fit the budget.
        # Omit low-ranked complete evidence items; never slice source in mid-symbol.
        serialization_start = time.perf_counter()
        while _size(output) > max_chars and evidence:
            # Drop optional call-site detail before dropping an entire
            # high-ranked responsibility from a tightly budgeted response.
            trimmed = False
            for item in reversed(evidence):
                if item.get("direct_call_sites"):
                    item["direct_call_sites"].pop()
                    item["direct_call_sites_omitted"] = item.get("direct_call_sites_omitted", 0) + 1
                    trimmed = True
                    break
            if trimmed:
                continue
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
        if "pack" in output:
            # Keep the pack's own size field consistent after wrapper trimming.
            for _ in range(3):
                output["pack"]["serialized_chars"] = _size(output["pack"])
            while _size(output) > max_chars and evidence:
                evidence.pop()
                omitted_owner["omitted"] += 1
                if omitted_owner.get("context_state") == "CURRENT":
                    omitted_owner["context_state"] = "PARTIAL"
                output["pack"]["serialized_chars"] = _size(output["pack"])
        if _size(output) > max_chars:
            raise ValueError("Query metadata exceeds max_chars; use a larger budget")
        return output
