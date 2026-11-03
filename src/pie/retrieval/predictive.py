"""Deterministic graph-guided predictive query selection.

Prediction only proposes a bounded warm-up of verified adjacent symbols. It never
authorizes returning speculative or stale evidence.
"""
from __future__ import annotations

def predict_adjacent_queries(pack: dict, *, limit: int = 6) -> list[str]:
    if not 1 <= limit <= 20:
        raise ValueError("Prediction limit out of range")
    found = []
    seen = set()
    for item in pack.get("responsibilities", []):
        for relation in item.get("verified_consumers", []):
            name = relation.get("consumer")
            path = relation.get("source_path")
            if not name or not path:
                continue
            # Qualified symbol plus path gives lexical ranking a focused target.
            query = str(name).replace("_", " ").replace(".", " ") + " " + str(path).replace("/", " ")
            if query not in seen:
                seen.add(query)
                found.append(query)
                if len(found) == limit:
                    return found
    return found
