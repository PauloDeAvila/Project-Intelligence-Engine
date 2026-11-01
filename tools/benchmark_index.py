#!/usr/bin/env python3
"""Produce a reproducible local indexing baseline without asserting a universal limit."""
import json
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pie.indexing.indexer import index_project


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        for number in range(100):
            (root / f"module_{number:03d}.py").write_text(f"class Service{number}:\n    def run(self):\n        return {number}\n", encoding="utf-8")
        start = time.perf_counter()
        result = index_project(root)
        elapsed = time.perf_counter() - start
        print(json.dumps({"files": result["files"], "symbols": result["symbols"], "seconds": round(elapsed, 4)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

