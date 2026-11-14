"""Fail-closed three-arm Codex/Blender token-and-correctness certification.

Does not call models or Blender, and never manufactures provider usage.
Consumes independently captured results with a reviewed correctness oracle.
Groups identical task/repetition/model/scene across baseline, current PIE,
and optimized PIE. Missing/invalid measurements produce NOT_CERTIFIED.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics

ARMS = ("baseline", "pie_current", "pie_optimized")
REQUIRED = ("scenario_id", "repetition", "model", "blender_version",
            "scene_sha256", "condition", "prompt_tokens", "completion_tokens",
            "wall_ms", "correct", "oracle_id")
TARGET_SAVINGS = 85.0


def _valid_record(value) -> bool:
    if not isinstance(value, dict) or any(k not in value for k in REQUIRED):
        return False
    for key in ("scenario_id", "model", "blender_version", "scene_sha256", "oracle_id"):
        if not isinstance(value[key], str) or not value[key].strip():
            return False
    if value["condition"] not in ARMS:
        return False
    if type(value["repetition"]) is not int or value["repetition"] < 1:
        return False
    for field in ("prompt_tokens", "completion_tokens"):
        if type(value[field]) is not int or value[field] < 0:
            return False
    if not isinstance(value["wall_ms"], (int, float)) or isinstance(value["wall_ms"], bool) or value["wall_ms"] < 0:
        return False
    return type(value["correct"]) is bool


def assess(raw: dict, *, min_pairs: int = 10, target_savings: float = TARGET_SAVINGS) -> dict:
    if type(min_pairs) is not int or not 1 <= min_pairs <= 1000:
        raise ValueError("min_pairs must be in 1..1000")
    if not isinstance(raw, dict) or not isinstance(raw.get("records"), list):
        raise ValueError("Expected JSON object with a records array")
    records = raw["records"]
    invalid = [i for i, value in enumerate(records) if not _valid_record(value)]
    groups: dict[tuple, dict] = {}
    duplicates = []
    for i, item in enumerate(records):
        if i in invalid:
            continue
        key = (item["scenario_id"], item["repetition"], item["model"],
               item["blender_version"], item["scene_sha256"], item["oracle_id"])
        if item["condition"] in groups.setdefault(key, {}):
            duplicates.append(i)
        else:
            groups[key][item["condition"]] = item
    pairs = [v for v in groups.values() if all(arm in v for arm in ARMS)]
    missing = sum(1 for g in groups.values() if len(g) != len(ARMS))
    baseline_tokens = sum(pair["baseline"]["prompt_tokens"] for pair in pairs)
    current_tokens = sum(pair["pie_current"]["prompt_tokens"] for pair in pairs)
    optimized_tokens = sum(pair["pie_optimized"]["prompt_tokens"] for pair in pairs)
    savings = round(100 * (1 - optimized_tokens / baseline_tokens), 3) if baseline_tokens > 0 else None
    present = len(records) > 0 and not invalid and not duplicates and not missing
    no_regression = bool(pairs) and all(
        (not p["baseline"]["correct"] or p["pie_optimized"]["correct"])
        and (not p["pie_current"]["correct"] or p["pie_optimized"]["correct"])
        for p in pairs
    )
    correctness = {arm: sum(p[arm]["correct"] for p in pairs) for arm in ARMS}
    median_ms = {arm: round(statistics.median(p[arm]["wall_ms"] for p in pairs), 3) if pairs else None
                 for arm in ARMS}
    certified = bool(
        present and len(pairs) >= min_pairs and baseline_tokens > 0 and
        no_regression and savings is not None and savings >= target_savings
    )
    return {
        "schema": "pie-three-arm-certification-v1",
        "status": "MEASUREMENT_GATE_PASSED" if certified else "NOT_CERTIFIED",
        "external_evidence_review_required": True,
        "observed_records": len(records),
        "invalid_records": invalid,
        "duplicate_records": duplicates,
        "incomplete_groups": missing,
        "complete_paired_trials": len(pairs),
        "min_pairs_required": min_pairs,
        "prompt_tokens_by_arm": {
            "baseline": baseline_tokens if pairs else None,
            "pie_current": current_tokens if pairs else None,
            "pie_optimized": optimized_tokens if pairs else None,
        },
        "paired_input_token_savings_pct": savings,
        "target_savings_pct": target_savings,
        "paired_correct_count": correctness,
        "optimized_no_correctness_regression": no_regression,
        "median_wall_ms": median_ms,
        "data_kind": "externally_provided_provider_usage_not_verified_by_this_script",
        "note": "Independent oracle and raw provider logs must be reviewed before any external certification claim.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--min-pairs", type=int, default=10)
    parser.add_argument("--strict", action="store_true", help="Exit 1 if not certified")
    args = parser.parse_args(argv)
    result = assess(json.loads(args.input.read_text(encoding="utf8")), min_pairs=args.min_pairs)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output+"\n", encoding="utf8")
    print(output)
    return 0 if result["status"] == "MEASUREMENT_GATE_PASSED" or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
