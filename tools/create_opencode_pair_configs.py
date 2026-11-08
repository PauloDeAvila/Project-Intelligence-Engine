"""Generate a matched OpenCode 2.x PIE-vs-baseline configuration pair."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from create_opencode_pie_config import make_config


def pair(root: Path, python: Path) -> tuple[dict, dict]:
    with_pie = make_config(root, python)
    # Read-only PIE retrieval tools may be used in the research condition.
    for name in ("pie_pie_query", "pie_pie_search_symbols",
                 "pie_pie_inspect_symbol", "pie_pie_build_context",
                 "pie_pie_verified_evidence", "pie_pie_project_status"):
        with_pie["permissions"].append(
            {"action": name, "resource": "*", "effect": "allow"})
    # BOTH agents have exactly the same native access rules.
    baseline = copy.deepcopy(with_pie)
    baseline["mcp"]["servers"].pop("pie")
    return with_pie, baseline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    args = parser.parse_args()
    with_pie, baseline = pair(args.root, args.python)
    dest = args.outdir.expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    for name, value in (("with-pie.json", with_pie),
                        ("without-pie.json", baseline)):
        with (dest / name).open("x", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print("Created isolated comparison configs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
