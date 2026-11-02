"""Auditable 9Router benchmark reports. Never replace unavailable usage with zero."""
import argparse
import csv
import json
import math
import statistics
from pathlib import Path

COLUMNS = (
    "task", "mode", "model", "ok", "correct", "oracle_path", "oracle_symbol",
    "answer_path", "answer_symbol", "error", "error_detail", "http_status",
    "calls", "searches", "prompt_usage_calls", "completion_usage_calls",
    "prompt_tokens", "completion_tokens", "model_ms_total", "retrieval_ms_total",
    "model_ms_mean", "retrieval_ms_mean", "attempt_wall_ms"
)

def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    pos = (len(values) - 1) * p / 100
    low, high = math.floor(pos), math.ceil(pos)
    return round(values[low] + (values[high] - values[low]) * (pos - low), 3)

def number_list(value):
    return [float(x) for x in (value or []) if isinstance(x, (int, float)) and not isinstance(x, bool)]

def summarize(source: Path, directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    raw = json.loads(source.read_text(encoding="utf8")) if source.is_file() else {}
    attempts = raw.get("results", [])
    records = []
    retrieval_times, model_times = [], []
    for x in attempts:
        m = number_list(x.get("model_ms"))
        r = number_list(x.get("search_ms"))
        if x.get("mode") == "pie":
            retrieval_times.extend(r)
        model_times.extend(m)
        oracle, answer = x.get("oracle") or {}, x.get("answer") or {}
        records.append({
            "task": x.get("task"), "mode": x.get("mode"), "model": x.get("model"),
            "ok": x.get("ok"), "correct": x.get("correct"),
            "oracle_path": oracle.get("path"), "oracle_symbol": oracle.get("symbol"),
            "answer_path": answer.get("path"), "answer_symbol": answer.get("symbol"),
            "error": x.get("error"), "error_detail": x.get("error_detail"),
            "http_status": x.get("http_status"), "calls": x.get("calls"),
            "searches": x.get("searches"),
            "prompt_usage_calls": x.get("prompt_usage_calls"),
            "completion_usage_calls": x.get("completion_usage_calls"),
            "prompt_tokens": x.get("prompt_tokens"), "completion_tokens": x.get("completion_tokens"),
            "model_ms_total": round(sum(m), 3) if m else None,
            "retrieval_ms_total": round(sum(r), 3) if r else None,
            "model_ms_mean": round(statistics.mean(m), 3) if m else None,
            "retrieval_ms_mean": round(statistics.mean(r), 3) if r else None,
            "attempt_wall_ms": x.get("attempt_wall_ms")
        })
    with (directory / "attempts.csv").open("w", newline="", encoding="utf8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)
    completed = [x for x in records if x["ok"] is True]
    measured = [x for x in completed if isinstance(x["prompt_tokens"], int)]
    keyed = {(x["model"], x["task"], x["mode"]): x for x in records}
    pairs = []
    for model, task, _ in keyed:
        a = keyed.get((model, task, "baseline"))
        b = keyed.get((model, task, "pie"))
        if a and b and a["ok"] is True and b["ok"] is True:
            if (a, b) not in pairs:
                pairs.append((a, b))
    token_pairs = [(a, b) for a, b in pairs if isinstance(a["prompt_tokens"], int)
                   and isinstance(b["prompt_tokens"], int)]
    baseline_tokens = sum(a["prompt_tokens"] for a, b in token_pairs)
    pie_tokens = sum(b["prompt_tokens"] for a, b in token_pairs)
    saving = round(100 * (1 - pie_tokens / baseline_tokens), 2) if token_pairs and baseline_tokens > 0 else None
    latency_mean = round(statistics.mean(retrieval_times), 3) if retrieval_times else None
    summary = {
        "input_exists": source.is_file(), "attempts": len(records),
        "completed": len(completed), "failures": len(records) - len(completed),
        "http_failures": sum(x["error"] == "HTTPError" for x in records),
        "completed_pairs": len(pairs), "token_covered_pairs": len(token_pairs),
        "token_pair_coverage_pct": round(100 * len(token_pairs) / len(pairs), 2) if pairs else None,
        "prompt_token_covered_attempts": len(measured),
        "baseline_prompt_tokens_paired": baseline_tokens if token_pairs else None,
        "pie_prompt_tokens_paired": pie_tokens if token_pairs else None,
        "input_token_saving_pct": saving,
        "retrieval_samples": len(retrieval_times), "retrieval_mean_ms": latency_mean,
        "retrieval_p95_ms": percentile(retrieval_times, 95),
        "retrieval_mean_below_100ms": latency_mean < 100 if latency_mean is not None else None,
        "model_samples": len(model_times),
        "model_mean_ms": round(statistics.mean(model_times), 3) if model_times else None,
        "model_p95_ms": percentile(model_times, 95),
        "paired_baseline_correct": sum(a["correct"] is True for a, b in pairs),
        "paired_pie_correct": sum(b["correct"] is True for a, b in pairs),
        "results_by_mode": {
            mode: {
                "attempts": sum(x["mode"] == mode for x in records),
                "completed": sum(x["mode"] == mode and x["ok"] is True for x in records),
                "correct": sum(x["mode"] == mode and x["correct"] is True for x in records),
                "prompt_token_covered": sum(x["mode"] == mode and isinstance(x["prompt_tokens"], int)
                                            and x["ok"] is True for x in records)
            } for mode in ("pie", "baseline")
        },
        "note": "Token saving is calculated only for completed pairs with reported prompt usage in both conditions. Missing values remain null. Retrieval latency excludes model inference."
    }
    # Certification requires complete paired answers, full token accounting,
    # and real PIE retrieval samples. Missing metrics never count as passing.
    expected = 30
    summary["certification"] = {
        "expected_questions": expected,
        "all_pairs_complete": len(pairs) == expected,
        "all_token_pairs_measured": len(token_pairs) == expected,
        "pie_accuracy_pct": round(100 * summary["paired_pie_correct"] / expected, 2)
            if len(pairs) == expected else None,
        "baseline_accuracy_pct": round(100 * summary["paired_baseline_correct"] / expected, 2)
            if len(pairs) == expected else None,
        "latency_target_pass": bool(retrieval_times and latency_mean < 100),
        "token_saving_target_pass": bool(
            len(token_pairs) == expected and saving is not None and saving >= 85),
        "fully_certified": bool(
            len(pairs) == expected and len(token_pairs) == expected
            and retrieval_times and latency_mean < 100
            and saving is not None and saving >= 85),
    }
    (directory / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf8")
    try:
        from artifact_tool import Workbook, SpreadsheetFile
        book = Workbook.create()
        sheet = book.worksheets.add("Tentativas")
        sheet.get_range("A1:W1").values = [list(COLUMNS)]
        sheet.get_range("A1:W1").format = {"fill": "#17324A", "font": {"bold": True, "color": "#FFFFFF"}}
        for start in range(0, len(records), 100):
            chunk = records[start:start+100]
            cells = [[row[c] for c in COLUMNS] for row in chunk]
            sheet.get_range(f"A{start+2}:W{start+1+len(chunk)}").values = cells
        sheet.freeze_panes.freeze_rows(1)
        overview = book.worksheets.add("Resumo")
        values = list(summary.items())
        overview.get_range("A1:B1").values = [["Métrica", "Valor"]]
        overview.get_range("A1:B1").format = {"fill": "#17324A", "font": {"bold": True, "color": "#FFFFFF"}}
        for i, (key, value) in enumerate(values, 2):
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            overview.get_range(f"A{i}:B{i}").values = [[key, value]]
        SpreadsheetFile.export_xlsx(book).save(str(directory / "pie-agent-report.xlsx"))
    except Exception as exc:
        (directory / "excel_error.txt").write_text(type(exc).__name__ + ": " + str(exc)[:500], encoding="utf8")
    print("REPORT", json.dumps(summary, ensure_ascii=False))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="pie-agent-9router-results.json")
    ap.add_argument("--out", default="pie-agent-report")
    args = ap.parse_args()
    summarize(Path(args.input), Path(args.out))
