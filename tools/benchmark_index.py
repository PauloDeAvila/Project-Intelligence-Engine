#!/usr/bin/env python3
"""Produce a reproducible local indexing baseline without asserting a universal limit."""
import argparse
import json
import pathlib
import sys
import tempfile
import tracemalloc
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pie.indexing.indexer import index_project
from pie.interfaces.cli import command_search


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, default=100)
    parser.add_argument("--queries", type=int, default=20)
    args = parser.parse_args()
    if args.files < 1 or args.queries < 0:
        parser.error("--files must be positive and --queries cannot be negative")
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        for number in range(args.files):
            (root / f"module_{number:03d}.py").write_text(f"class Service{number}:\n    def run(self):\n        return {number}\n", encoding="utf-8")
        tracemalloc.start()
        start = time.perf_counter()
        result = index_project(root)
        elapsed = time.perf_counter() - start
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        query_start = time.perf_counter()
        for _ in range(args.queries):
            command_search(root, "Service")
        query_seconds = time.perf_counter() - query_start
        print(json.dumps({"files": result["files"], "symbols": result["symbols"], "index_seconds": round(elapsed, 4), "tracemalloc_peak_bytes": peak_bytes, "queries": args.queries, "query_seconds": round(query_seconds, 4)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

