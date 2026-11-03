"""DES-04 post-fix smoke check against the two existing real-repo snapshots.

Copies the source code into disposable directories, indexes from scratch and
reports verified static call sites. Never modifies the baseline, indexed
original snapshots or stable PIE Gateway. This is an exploratory comparison,
NOT a reviewed gold recall benchmark or a Qwen test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile

from pie.indexing.indexer import index_project
from pie.interfaces.cli import command_init
from pie.retrieval.evidence import EvidenceError
from pie.retrieval.static_traceability import inspect_static_dependencies

TARGETS = {
    "requests": ("extract_cookies_to_jar", "merge_setting"),
    "click": ("format_filename", "style"),
}
PRELIMINARY_SOURCE_CANDIDATES = {
    ("requests", "extract_cookies_to_jar"): 6,
    ("requests", "merge_setting"): 8,
    ("click", "format_filename"): 9,
    ("click", "style"): 1,
}


def inspect_project(source: Path, project_name: str, destination: Path) -> dict:
    if not source.is_dir() or not (source / "src").is_dir():
        raise ValueError(f"Expected an unpacked Python project with src/: {source}")
    if source.resolve() == destination.resolve():
        raise ValueError("Refusing in-place indexing of baseline")
    shutil.copytree(
        source, destination,
        ignore=shutil.ignore_patterns(".git", ".pie", "__pycache__"),
    )
    command_init(destination)
    indexed = index_project(destination)
    if indexed["index_state"] != "CURRENT":
        raise ValueError(f"{project_name} copy indexed as {indexed['index_state']}")
    items = []
    for symbol in TARGETS[project_name]:
        try:
            report = inspect_static_dependencies(destination, symbol)
            items.append({
                "symbol": symbol,
                "status": report["status"],
                "observed_verified_edges": report["observed_edge_count"],
                "provisional_candidate_calls":
                    PRELIMINARY_SOURCE_CANDIDATES[(project_name, symbol)],
                "truncated_edges": report["truncated_edge_count"],
                "edges": report["edges"],
                "impact": report["impact"],
                "note": "Candidate inventory has not passed independent source review",
            })
        except EvidenceError as exc:
            items.append({
                "symbol": symbol, "status": "ABSTAIN",
                "reason": str(exc),
                "observed_verified_edges": 0,
                "provisional_candidate_calls":
                    PRELIMINARY_SOURCE_CANDIDATES[(project_name, symbol)],
            })
    return {
        "repository": project_name,
        "index_state": indexed["index_state"],
        "indexed_files": indexed["files"],
        "targets": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare DES-04 static edges on fresh disposable real-repo copies")
    parser.add_argument("--requests", required=True, type=Path,
                        help="Existing Requests v2.32.5 checked-out source directory")
    parser.add_argument("--click", required=True, type=Path,
                        help="Existing Click 8.3.1 checked-out source directory")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    roots = {"requests": args.requests, "click": args.click}
    with tempfile.TemporaryDirectory(prefix="pie-des04-postfix-") as sandbox:
        scratch = Path(sandbox)
        result = {
            "status": "EXPLORATORY_NOT_FROZEN",
            "model_inference_performed": False,
            "independently_reviewed_gold": False,
            "projects": [
                inspect_project(root, name, scratch / name)
                for name, root in roots.items()
            ],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("RESULT=" + json.dumps({
        item["repository"]: {
            entry["symbol"]: entry["observed_verified_edges"]
            for entry in item["targets"]
        } for item in result["projects"]
    }, ensure_ascii=False))
    print("REPORT=" + str(args.output))


if __name__ == "__main__":
    main()
