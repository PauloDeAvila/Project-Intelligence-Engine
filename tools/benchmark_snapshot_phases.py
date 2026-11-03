"""Measure SnapshotVerifier phases on a fixed project snapshot."""
import argparse, hashlib, json, statistics, time
from pathlib import Path
from pie.retrieval.evidence import build_evidence
from pie.scanning.discovery import iter_files

SYMBOLS = ["audit_component", "MeasurementCache.get", "analyze_mesh", "validate_change", "content_key"]

def main():
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True); p.add_argument("--repetitions", type=int, default=5); p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    files = {r.path.as_posix(): r.sha256 for r in iter_files(a.root)}
    snapshot_hash = hashlib.sha256("".join(k+v for k,v in sorted(files.items())).encode()).hexdigest()
    rows = []
    for repeat in range(1, a.repetitions + 1):
        for symbol in SYMBOLS:
            started = time.perf_counter(); evidence = build_evidence(a.root, symbol); total = time.perf_counter() - started
            metrics = evidence["verification_metrics"]
            rows.append({"repeat": repeat, "symbol": symbol, "total_seconds": round(total, 6), **metrics})
    result = {"schema": "pie-snapshot-phases-v1", "root": str(a.root), "files": len(files), "snapshot_sha256": snapshot_hash, "repetitions": a.repetitions, "rows": rows, "medians": {k: {field: statistics.median(r[field] for r in rows if r["symbol"] == k) for field in ("total_seconds", "db_seconds", "read_seconds", "hash_seconds", "enumeration_seconds", "discovery_hash_seconds")} for k in SYMBOLS}}
    a.output.parent.mkdir(parents=True, exist_ok=True); a.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for symbol, values in result["medians"].items(): print(symbol, values)

if __name__ == "__main__": main()
