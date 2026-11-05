#!/usr/bin/env python3
"""Measure the Phase 1 browser connector against a local HTTP fixture only."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import statistics
import time
import threading
import sys

from pie.web import BrowserConnector, BrowserHealthMonitor, NavigationController, PlaywrightBrowserAdapter


class _FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib protocol name
        body = b"<html><body><main>PIE connector benchmark</main></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def _measure(function):
    started = time.perf_counter_ns()
    value = function()
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    return value, elapsed_ms


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int((len(ordered) * 95 + 99) / 100) - 1))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("web-connector-benchmark.json"))
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error("--repetitions must be between 1 and 20")

    server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    measurements: dict[str, list[float]] = {
        "connect_ms": [],
        "navigate_ms": [],
        "health_ms": [],
        "close_ms": [],
    }
    try:
        for index in range(args.repetitions):
            adapter = PlaywrightBrowserAdapter(headless=True, timeout_ms=15_000)
            connector = BrowserConnector()
            session_id = f"benchmark-{index}"
            connector.create_session(
                session_id=session_id,
                adapter=adapter,
                adapter_name="playwright",
                allowed_origins=(origin,),
            )
            _, connect_ms = _measure(lambda: connector.connect(session_id))
            measurements["connect_ms"].append(connect_ms)
            navigation = NavigationController(connector)
            _, navigation_ms = _measure(
                lambda: navigation.navigate(session_id, f"{origin}/page-{index}")
            )
            measurements["navigate_ms"].append(navigation_ms)
            monitor = BrowserHealthMonitor(connector)
            _, health_ms = _measure(lambda: monitor.check(session_id))
            measurements["health_ms"].append(health_ms)
            _, close_ms = _measure(lambda: connector.close(session_id))
            measurements["close_ms"].append(close_ms)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    if len(measurements["connect_ms"]) != args.repetitions:
        raise RuntimeError("connect benchmark did not produce one sample per repetition")
    summary = {
        "status": "COMPLETED",
        "python": sys.version.split()[0],
        "playwright": importlib.metadata.version("playwright"),
        "browser": "chromium",
        "fixture": "loopback-http-only",
        "repetitions": args.repetitions,
        "metrics_ms": {
            name: {
                "samples": values,
                "median": statistics.median(values),
                "p95": _p95(values),
            }
            for name, values in measurements.items()
        },
    }
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
