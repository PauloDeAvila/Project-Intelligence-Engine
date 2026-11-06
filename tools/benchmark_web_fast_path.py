"""Measure local cache-assisted lookup latency; no browser, network or model calls."""

from __future__ import annotations

import argparse
import json
from statistics import median
from time import perf_counter

from pie.web import AccessibilityNode, BrowserFastPath, SnapshotNormalizer


def _snapshot():
    tree = AccessibilityNode(role="main", name="Home", children=tuple(AccessibilityNode(role="button", name=f"Item {i}", region="main") for i in range(64)))
    return SnapshotNormalizer().normalize(
        session_id="benchmark", page_id="page", frame_id="main", generation=1,
        origin="https://example.test", path="/", title="Home", tree=tree,
        captured_at="2026-01-01T00:00:00Z",
    ).snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=1000)
    parser.add_argument("--output", default="web-fast-path-benchmark.json")
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 100_000:
        raise SystemExit("repetitions must be between 1 and 100000")
    snapshot = _snapshot()
    fast = BrowserFastPath()
    fast.get_or_compute(snapshot, region="main", task="open", compute=lambda: "warm")
    samples = []
    for _ in range(args.repetitions):
        started = perf_counter()
        result = fast.get_or_compute(snapshot, region="main", task="open", compute=lambda: "cold")
        samples.append((perf_counter() - started) * 1000.0)
    samples.sort()
    payload = {
        "repetitions": args.repetitions,
        "cache_hit_rate": 1.0,
        "median_ms": median(samples),
        "p95_ms": samples[min(len(samples) - 1, int(len(samples) * 0.95))],
        "max_ms": max(samples),
        "model_calls": 0,
        "network_calls": 0,
        "validation_required": result.validation_required,
    }
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
