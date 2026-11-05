"""Benchmark quantified context reduction without browser, network or model calls."""

from __future__ import annotations

import argparse
import json
import math
import platform
from pathlib import Path
import time

from pie.web import AccessibilityNode, SnapshotNormalizer, WebRelevanceGate


def _snapshot(size: int):
    children = tuple(
        AccessibilityNode(
            role="textbox" if index % 4 == 0 else "button",
            name=("Search field " if index % 4 == 0 else "Action ") + str(index),
            region="Results" if index % 3 == 0 else "Navigation",
        )
        for index in range(size - 1)
    )
    return SnapshotNormalizer().normalize(
        session_id="benchmark",
        page_id=f"page-{size}",
        frame_id="main",
        generation=1,
        origin="https://benchmark.invalid",
        path="/fixture",
        title="Synthetic fixture",
        tree=AccessibilityNode(role="main", name="Fixture", children=children),
        captured_at="2026-01-01T00:00:00Z",
    ).snapshot


def _p95(values: list[float]) -> float:
    return sorted(values)[max(0, min(len(values) - 1, math.ceil(len(values) * 0.95) - 1))]


def run(repetitions: int) -> dict[str, object]:
    if not isinstance(repetitions, int) or not 1 <= repetitions <= 100_000:
        raise ValueError("repetitions must be between 1 and 100000")
    cases = []
    for size in (64, 256, 512):
        snapshot = _snapshot(size)
        gate = WebRelevanceGate()
        gate.quantify(snapshot, "search field", context_budget_chars=2048, max_candidates=8)
        samples: list[float] = []
        last = None
        for _ in range(repetitions):
            started = time.perf_counter_ns()
            last = gate.quantify(snapshot, "search field", context_budget_chars=2048, max_candidates=8)
            samples.append((time.perf_counter_ns() - started) / 1_000_000)
        cases.append(
            {
                "elements": size,
                "selected": len(last.selected) if last is not None else 0,
                "omissions": len(last.omissions) if last is not None else 0,
                "estimated_chars": last.estimated_chars if last is not None else 0,
                "p50_ms": round(sorted(samples)[len(samples) // 2], 6),
                "p95_ms": round(_p95(samples), 6),
                "max_ms": round(max(samples), 6),
            }
        )
    return {
        "schema": "pie.web.relevance-benchmark.v1",
        "status": "COMPLETED",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "repetitions": repetitions,
        "model_calls": 0,
        "external_network_calls": 0,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("web-relevance-benchmark.json"))
    args = parser.parse_args()
    payload = run(args.repetitions)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
