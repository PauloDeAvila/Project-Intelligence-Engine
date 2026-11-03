"""Benchmark dynamic evidence selection via the *integrated* PIE Gateway.

Uses 30 manually labeled questions from the deterministic test fixture, with
no expected fields passed to the model. Each case is requested once. No claim
of generalization or true model comprehension is implied.
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


def load_gold(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "CASES"
            for target in node.targets
        ):
            cases = ast.literal_eval(node.value)
            if len(cases) != 30:
                raise ValueError("Expected exactly 30 independent gold questions")
            return cases
    raise ValueError("Benchmark gold CASES not found")


def evaluate(base_url: str, cases: list, *, timeout: float = 60) -> dict:
    if base_url != "http://127.0.0.1:8766":
        raise ValueError("Benchmark only permits the local PIE Gateway on port 8766")
    results = []
    opener = build_opener(ProxyHandler({}))
    order = list(enumerate(cases, 1))
    random.Random(20261103).shuffle(order)
    for case_id, (category, question, expected) in order:
        request = Request(
            base_url + "/ask",
            data=json.dumps({
                "question": question,
                "symbol": "analyze_mesh",
                "validation_mode": "dynamic_selection",
            }, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError("Gateway response too large")
            payload = json.loads(raw)
            elapsed = time.perf_counter() - started
            verdict = payload.get("model_validation", {})
            actual = verdict.get("selected_fields", [])
            if not isinstance(actual, list):
                actual = []
            # Human-authored gold is used ONLY for scoring, never sent to the model.
            status = payload.get("status")
            ok = status == "ABSTAIN" if expected is None else (
                status == "CERTIFIED_FACTS"
                and verdict.get("status") == "VERIFIED"
                and set(actual) == set(expected)
                and len(actual) == len(expected)
            )
            expected_set = set(expected or [])
            actual_set = set(actual)
            true_positives = len(actual_set & expected_set)
            precision = true_positives / len(actual_set) if actual_set else (1.0 if not expected_set else 0.0)
            recall = true_positives / len(expected_set) if expected_set else (1.0 if not actual_set else 0.0)
            results.append({
                "case_id": case_id, "category": category,
                "gold": expected, "selected": actual, "status": status,
                "model_status": verdict.get("status"),
                "reason": verdict.get("reason"),
                "exact_or_safe_abstention": ok,
                "precision": precision, "recall": recall,
                "latency_s": round(elapsed, 4),
                "error": None,
            })
        except Exception as exc:
            results.append({
                "case_id": case_id, "category": category, "gold": expected,
                "selected": [], "status": "ERROR", "model_status": "ERROR",
                "reason": "request_failed", "exact_or_safe_abstention": False,
                "precision": 0.0, "recall": 0.0,
                "latency_s": round(time.perf_counter() - started, 4),
                "error": type(exc).__name__,
            })
        current = results[-1]
        print(f"{len(results):02}/30 {category:12} {current['status']:16} "
              f"pass={current['exact_or_safe_abstention']} "
              f"{current['latency_s']:.2f}s", flush=True)
    supported = [x for x in results if x["gold"] is not None]
    abstain = [x for x in results if x["gold"] is None]
    durations = [x["latency_s"] for x in results if x["status"] != "ERROR"]
    return {
        "design": "30 distinct fixed questions, deterministic shuffle; exact-symbol queries",
        "n": len(results),
        "supported_n": len(supported), "abstention_n": len(abstain),
        "positive_exact": sum(x["exact_or_safe_abstention"] for x in supported),
        "safe_abstentions": sum(x["exact_or_safe_abstention"] for x in abstain),
        "errors": sum(x["error"] is not None for x in results),
        "mean_precision_supported": round(statistics.mean(x["precision"] for x in supported), 3),
        "mean_recall_supported": round(statistics.mean(x["recall"] for x in supported), 3),
        "latency_mean_s": round(statistics.mean(durations), 3) if durations else None,
        "latency_median_s": round(statistics.median(durations), 3) if durations else None,
        "tokens": None,
        "token_note": "Not exposed through /ask; not measured",
        "limitations": [
            "Only one symbol, analyze_mesh; no cross-project generalization.",
            "The independent planner is keyword-based and uses fixed intents.",
            "Unsupported cases may abstain before invoking Qwen.",
            "The model never receives the expected gold field selection.",
        ],
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="PIE dynamic selection 30-case benchmark")
    parser.add_argument("--gateway", default="http://127.0.0.1:8766")
    parser.add_argument("--gold", type=Path, default=Path(__file__).resolve().parents[1]
                        / "tests" / "test_dynamic_evidence_planner.py")
    parser.add_argument("--output", type=Path, default=Path("dynamic-selection-results.json"))
    args = parser.parse_args()
    result = evaluate(args.gateway, load_gold(args.gold))
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("RESULT=" + json.dumps({key: value for key, value in result.items()
                                 if key != "results"}, ensure_ascii=False))
    print("Report saved to " + str(args.output))
    if result["errors"] or result["positive_exact"] != result["supported_n"] or (
        result["safe_abstentions"] != result["abstention_n"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
