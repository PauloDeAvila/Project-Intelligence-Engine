"""GitHub Actions warm-service validation, with honest latency measurements.

Correctness tests are mandatory. Performance targets are recorded as measured
objectives, not asserted as already achieved.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pie.indexing.indexer import index_project
from pie.retrieval.warm import WarmContextService


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered)-1, max(0, int((len(ordered)-1)*fraction)))]


def run():
    results = {}
    with tempfile.TemporaryDirectory(prefix="pie-warm-gate-") as folder:
        root = Path(folder)
        (root/"cache.py").write_text(
            'def invalidate_cache(key):\n    """Discard stale cache entries after updates."""\n    return key\n', encoding="utf8")
        (root/"other.py").write_text(
            'def persist_state(value):\n    """Persist application state safely to durable storage."""\n    return value\n', encoding="utf8")
        indexed = index_project(root)
        assert indexed["index_state"] == "CURRENT", indexed
        with WarmContextService(root, cache_size=2) as service:
            timings = []
            query = "Discard stale cache entries"
            initial = service.query(query, include_body=True)
            assert not initial["cache_hit"]
            assert any(e["path"] == "cache.py" for e in initial["result"]["evidence"]), initial
            assert initial["result"]["context_state"] == "CURRENT"
            for _ in range(31):
                start = time.perf_counter_ns()
                hit = service.query(query, include_body=True)
                timings.append((time.perf_counter_ns()-start)/1e6)
                assert hit["cache_hit"], hit
            assert hit["result"]["evidence"] == initial["result"]["evidence"]
            results["cache_hits"] = 31
            results["latency_ms"] = {
                "p50": round(statistics.median(timings), 4),
                "p95": round(percentile(timings, .95), 4),
                "max": round(max(timings), 4)}
            results["latency_target_p95_le_0_9ms"] = results["latency_ms"]["p95"] <= 0.9
            # Change source with identical character count: index must hash,
            # never rely solely on file size or timestamps.
            source = root/"cache.py"
            before = source.read_text(encoding="utf8")
            updated = before.replace("Discard", "Discard") .replace("stale", "fresh")
            assert len(updated) == len(before)
            source.write_text(updated, encoding="utf8")
            changed = service.query(query, include_body=True)
            assert not changed["cache_hit"], "stale warm response after edit"
            assert all("stale cache entries" not in e.get("content", "") for e in changed["result"]["evidence"])
            results["same_size_edit_invalidates"] = True
            source.unlink()
            deleted = service.query(query, include_body=True)
            assert not deleted["cache_hit"], "deleted source returned from cache"
            assert all(e["path"] != "cache.py" for e in deleted["result"]["evidence"])
            results["deletion_invalidates"] = True
            # A bound size must be respected; repeated queries should not evict
            # the just-requested item.
            service.query("persist state")
            service.query("unrelated no-match query")
            assert len(service._cache) <= 2
            results["lru_bound"] = True
    results["scope"] = ("Local warm-service queries including incremental index refresh, "
                        "not network/MCP/model latency; synthetic fixtures")
    results["overall_correctness"] = True
    output = Path(os.getenv("PIE_WARM_REPORT", "pie-warm-gate.json"))
    output.write_text(json.dumps(results, indent=2), encoding="utf8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    run()
