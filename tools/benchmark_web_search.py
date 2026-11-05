"""Benchmark local Page Intelligence search without a browser or model call."""

from __future__ import annotations

import argparse
import json
import math
import platform
from pathlib import Path
import sys
import time

from pie.web import AccessibilityExtractor, AccessibilityNode, LocalWebSearch, SnapshotNormalizer


def _snapshot(size: int):
    children = tuple(
        AccessibilityNode(
            role="textbox" if index % 4 == 0 else "button",
            name=f"Search field {index}" if index % 4 == 0 else f"Action {index}",
            region="Results" if index % 3 == 0 else "Navigation",
        )
        for index in range(size - 1)
    )
    return SnapshotNormalizer(extractor=AccessibilityExtractor(max_elements=512)).normalize(
        session_id="benchmark",
        page_id=f"page-{size}",
        frame_id="main",
        generation=1,
        origin="https://benchmark.invalid",
        path="/fixture",
        title="Synthetic benchmark fixture",
        tree=AccessibilityNode(role="main", name="Fixture", children=children),
        captured_at="2026-01-01T00:00:00Z",
    ).snapshot


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def run(repetitions: int) -> dict[str, object]:
    if not isinstance(repetitions, int) or not 1 <= repetitions <= 100_000:
        raise ValueError("repetitions must be between 1 and 100000")
    outputs: list[dict[str, object]] = []
    for size in (64, 256, 512):
        snapshot = _snapshot(size)
        search = LocalWebSearch()
        search.register(snapshot)
        query = "search field"
        search.search(snapshot.snapshot_id, query)
        samples: list[float] = []
        last = None
        for _ in range(repetitions):
            started = time.perf_counter_ns()
            last = search.search(snapshot.snapshot_id, query)
            samples.append((time.perf_counter_ns() - started) / 1_000_000)
        outputs.append(
            {
                "elements_requested": size,
                "elements_indexed": len(snapshot.elements),
                "snapshot_state": snapshot.state.value,
                "query": query,
                "matches": len(last.matches) if last is not None else 0,
                "p50_ms": round(_percentile(samples, 0.50), 6),
                "p95_ms": round(_percentile(samples, 0.95), 6),
                "max_ms": round(max(samples), 6),
            }
        )
    return {
        "schema": "pie.web.search-benchmark.v1",
        "status": "COMPLETED",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "repetitions": repetitions,
        "model_calls": 0,
        "external_network_calls": 0,
        "cases": outputs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("web-search-benchmark.json"))
    args = parser.parse_args()
    payload = run(args.repetitions)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
