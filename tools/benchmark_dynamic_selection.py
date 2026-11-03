"""Benchmark dynamic PIE selection with independently audited question policy.

No model input includes the gold requirements, optional/prohibited fields,
or the expected answer. Semantic sufficiency and actual gateway certification
are measured separately. Prior DES-01/02 reports are never retroactively edited.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import random
import statistics
import time
from urllib.request import ProxyHandler, Request, build_opener

MAX_RESPONSE_BYTES = 262144
ALLOWED_FIELDS = {"signature", "path", "line", "direct_call_count",
                  "direct_call_sites"}


def load_gold(path: Path) -> list:
    """Retain the original question fixture without embedding answer keys in prompts."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "CASES"
            for target in node.targets
        ):
            cases = ast.literal_eval(node.value)
            if len(cases) != 30:
                raise ValueError("Expected 30 question cases")
            return cases
    raise ValueError("CASES was not found")


def load_policy(path: Path, cases: list) -> dict:
    """Fail closed on incomplete, contradictory or reordered independent policy."""
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("items")
    if not isinstance(entries, list) or len(entries) != len(cases):
        raise ValueError("Gold policy must contain an item for every question")
    by_id = {}
    for entry in entries:
        case_id = entry.get("case_id")
        if type(case_id) is not int or case_id in by_id or not 1 <= case_id <= len(cases):
            raise ValueError("Duplicate or invalid gold case ID")
        sections = []
        for key in ("required", "optional", "forbidden"):
            fields = entry.get(key)
            if not isinstance(fields, list) or any(
                not isinstance(value, str) for value in fields
            ) or len(fields) != len(set(fields)):
                raise ValueError(f"Invalid gold {key} for case {case_id}")
            sections.append(set(fields))
        if set.union(*sections) != ALLOWED_FIELDS or (
            sum(len(section) for section in sections) != len(ALLOWED_FIELDS)
        ):
            raise ValueError(f"Gold field partition overlaps or omits fields: {case_id}")
        if entry.get("question") != cases[case_id - 1][1]:
            raise ValueError(f"Gold question drift detected: {case_id}")
        expected_abstain = cases[case_id - 1][2] is None
        if type(entry.get("abstain")) is not bool or entry["abstain"] != expected_abstain:
            raise ValueError(f"Gold abstention mismatch: {case_id}")
        if entry["abstain"] and (entry["required"] or entry["optional"]):
            raise ValueError(f"Abstention case contains selectable fields: {case_id}")
        if not entry["abstain"] and not entry["required"]:
            raise ValueError(f"Positive case has no mandatory evidence: {case_id}")
        by_id[case_id] = entry
    if set(by_id) != set(range(1, len(cases) + 1)):
        raise ValueError("Missing gold case ID")
    return by_id


def score_selection(selected: object, policy: dict) -> dict:
    """Scoring is independent of the model verdict and the gateway answer."""
    if not isinstance(selected, list) or any(not isinstance(x, str) for x in selected):
        selected = []
    chosen = set(selected)
    required = set(policy["required"])
    optional = set(policy["optional"])
    forbidden = set(policy["forbidden"])
    valid_unique = len(selected) == len(chosen) and chosen <= ALLOWED_FIELDS
    sufficient = bool(not policy["abstain"] and chosen and valid_unique
                      and required <= chosen and not chosen.intersection(forbidden))
    exact = bool(not policy["abstain"] and valid_unique and chosen == required)
    acceptable = required | optional
    true_positive = len(chosen.intersection(acceptable))
    precision = true_positive / len(chosen) if chosen else 0.0
    recall = len(chosen.intersection(required)) / len(required) if required else 0.0
    return {
        "semantically_sufficient": sufficient,
        "selection_exact": exact,
        "precision": precision,
        "recall": recall,
        "missing_mandatory": sorted(required - chosen),
        "selected_forbidden": sorted(chosen & forbidden),
        "selected_optional": sorted(chosen & optional),
    }


def evaluate(base_url: str, cases: list, *, policy: dict, timeout: float = 60,
             validation_mode: str = "dynamic_selection") -> dict:
    if validation_mode not in ("dynamic_selection", "dynamic_selection_schema"):
        raise ValueError("Unsupported validation_mode")
    if base_url != "http://127.0.0.1:8766":
        raise ValueError("Benchmark only permits localhost:8766")
    results = []
    opener = build_opener(ProxyHandler({}))
    order = list(enumerate(cases, 1))
    random.Random(20261103).shuffle(order)

    for case_id, (category, question, original_fields) in order:
        reference = policy[case_id]
        req = Request(
            base_url + "/ask",
            data=json.dumps({
                "question": question, "symbol": "analyze_mesh",
                "validation_mode": validation_mode,
            }, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with opener.open(req, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError("Gateway response too large")
            payload = json.loads(raw)
            latency = round(time.perf_counter() - started, 4)
            verdict = payload.get("model_validation") or {}
            selection = verdict.get("selected_fields") or []
            scored = score_selection(selection, reference)
            status = payload.get("status")
            model_status = verdict.get("status")
            # An abstention due to a deterministic pre-model rule is NOT a
            # successful model decision to abstain.
            planner_abstained = status == "ABSTAIN" and model_status == "NOT_REQUESTED"
            model_rejected = status == "ABSTAIN" and model_status == "REJECTED"
            certified = (status == "CERTIFIED_FACTS"
                         and model_status == "VERIFIED")
            results.append({
                "case_id": case_id, "category": category, "question": question,
                "gold": reference["required"], "optional": reference["optional"],
                "forbidden": reference["forbidden"], "abstain_gold": reference["abstain"],
                "selected": selection if isinstance(selection, list) else [],
                "status": status, "model_status": model_status,
                "reason": verdict.get("reason"),
                "semantically_sufficient": scored["semantically_sufficient"]
                    if not reference["abstain"] else False,
                "selection_exact": scored["selection_exact"]
                    if not reference["abstain"] else False,
                "gateway_certified": certified,
                "planner_abstained": planner_abstained,
                "model_rejected": model_rejected,
                "safe_abstention": bool(reference["abstain"] and planner_abstained),
                "precision": round(scored["precision"], 4),
                "recall": round(scored["recall"], 4),
                "missing_mandatory": scored["missing_mandatory"],
                "selected_forbidden": scored["selected_forbidden"],
                "selected_optional": scored["selected_optional"],
                "latency_s": latency, "error": None,
            })
        except Exception as exc:
            results.append({
                "case_id": case_id, "category": category, "question": question,
                "gold": reference["required"], "optional": reference["optional"],
                "forbidden": reference["forbidden"], "abstain_gold": reference["abstain"],
                "selected": [], "status": "ERROR", "model_status": "ERROR",
                "reason": "request_failed", "semantically_sufficient": False,
                "selection_exact": False, "gateway_certified": False,
                "planner_abstained": False, "model_rejected": False,
                "safe_abstention": False, "precision": 0.0, "recall": 0.0,
                "missing_mandatory": reference["required"], "selected_forbidden": [],
                "selected_optional": [], "latency_s": round(time.perf_counter()-started, 4),
                "error": type(exc).__name__,
            })
        current = results[-1]
        print(f"{len(results):02}/{len(order)} {category:12} {current['status']:16} "
              f"sufficient={current['semantically_sufficient']} "
              f"certified={current['gateway_certified']} "
              f"latency={current['latency_s']:.3f}s", flush=True)

    positive = [r for r in results if not r["abstain_gold"]]
    negative = [r for r in results if r["abstain_gold"]]
    answered = [r for r in results if r["status"] != "ERROR"]
    invoked = [r for r in results if r["model_status"] != "NOT_REQUESTED"
               and r["status"] != "ERROR"]
    def mean(values):
        return round(statistics.mean(values), 3) if values else None

    return {
        "design": "Thirty distinct manually audited single-symbol questions",
        "gold_version": "DES03-human-reviewed-v1",
        "validation_mode": validation_mode, "n": len(results),
        "supported_n": len(positive), "abstention_n": len(negative),
        "positive_semantically_sufficient": sum(r["semantically_sufficient"] for r in positive),
        "positive_exact": sum(r["selection_exact"] for r in positive),
        "positive_gateway_certified": sum(r["gateway_certified"] for r in positive),
        "safe_abstentions": sum(r["safe_abstention"] for r in negative),
        "planner_not_requested": sum(r["planner_abstained"] for r in results),
        "model_rejected_after_call": sum(r["model_rejected"] for r in results),
        "errors": sum(r["error"] is not None for r in results),
        "mean_precision_supported": mean([r["precision"] for r in positive]),
        "mean_recall_supported": mean([r["recall"] for r in positive]),
        "latency_mean_s": mean([r["latency_s"] for r in answered]),
        "latency_median_s": round(statistics.median([r["latency_s"] for r in answered]), 3)
            if answered else None,
        "inference_path_latency_mean_s": mean([r["latency_s"] for r in invoked]),
        "pre_model_abstention_latency_mean_s":
            mean([r["latency_s"] for r in results if r["planner_abstained"]]),
        "tokens": None, "token_note": "Not provided by Gateway /ask; not measured",
        "limitations": [
            "One symbol and one indexed project; no cross-project model generalization.",
            "Independent gold is manually reviewed; deterministic planner is keyword-based.",
            "Pre-model abstentions do not measure model abstention.",
            "The same labeled questions are reused from development; holdout needed.",
        ],
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="PIE DES-03 evidence sufficiency benchmark")
    parser.add_argument("--gateway", default="http://127.0.0.1:8766")
    parser.add_argument("--mode", choices=("dynamic_selection", "dynamic_selection_schema"),
                        default="dynamic_selection_schema")
    parser.add_argument("--gold", type=Path,
                        default=Path(__file__).resolve().parents[1]
                        / "tests" / "test_dynamic_evidence_planner.py")
    parser.add_argument("--policy", type=Path,
                        default=Path(__file__).resolve().parents[1]
                        / "tests" / "fixtures" / "dynamic_selection_gold_v3.json")
    parser.add_argument("--output", type=Path, default=Path("dynamic-selection-des03.json"))
    args = parser.parse_args()
    cases = load_gold(args.gold)
    result = evaluate(args.gateway, cases, policy=load_policy(args.policy, cases),
                      validation_mode=args.mode)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print("SUMMARY=" + json.dumps({key: value for key, value in result.items()
                                  if key != "results"}, ensure_ascii=False))
    print("Report saved to " + str(args.output))
    if result["errors"] or result["positive_gateway_certified"] != result["supported_n"] or (
        result["safe_abstentions"] != result["abstention_n"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
