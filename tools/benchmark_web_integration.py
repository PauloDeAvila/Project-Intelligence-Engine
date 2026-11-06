"""Certification benchmark for local PIE web stages; no provider or secret inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from pie.web import AccessibilityNode, WebIntelligenceService, SnapshotNormalizer


def _snapshot():
    tree = AccessibilityNode(role="main", name="Home", children=tuple(AccessibilityNode(role="button", name=f"Open {i}", region="main") for i in range(32)))
    return SnapshotNormalizer().normalize(
        session_id="certification", page_id="page", frame_id="main", generation=1,
        origin="https://example.test", path="/", title="Home", tree=tree,
        captured_at="2026-01-01T00:00:00Z",
    ).snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("web-integration-benchmark.json"))
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 10_000:
        raise SystemExit("repetitions must be between 1 and 10000")
    service = WebIntelligenceService()
    snapshot = _snapshot()
    samples = []
    pack = None
    for _ in range(args.repetitions):
        started = perf_counter()
        pack = service.context(snapshot, "open", context_budget_chars=4096, max_candidates=8)
        samples.append((perf_counter() - started) * 1000.0)
    samples.sort()
    result = {
        "schema": "pie.web.integration-benchmark.v1",
        "repetitions": args.repetitions,
        "local_pipeline": "snapshot->relevance->evidence-pack",
        "median_ms": median(samples),
        "p95_ms": samples[min(len(samples) - 1, int(len(samples) * 0.95))],
        "max_ms": max(samples),
        "model_calls": 0,
        "network_calls": 0,
        "selected_items": len(pack.items),
        "omissions": len(pack.omissions),
        "execution_authorized": pack.execution_authorized,
        "direct_playwright_baseline": "not_run",
        "external_classifier": "disabled",
        "certification_state": "LOCAL_PIPELINE_ONLY",
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
