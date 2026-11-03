"""Cross-project DES holdout: isolated synthetic projects, new symbols.

Runs a real local HTTP Gateway and optionally the real Qwen via LM Studio,
without binding port 8766 or changing existing projects and indexes. The
question/gold fixture is frozen and MUST NOT be used to tune the planner.
"""
from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import statistics
import tempfile
import threading
import time
from urllib.request import ProxyHandler, Request, build_opener

from pie.indexing.indexer import index_project
from pie.interfaces.cli import command_init
from pie.interfaces.gateway import Gateway, handler_factory
from benchmark_dynamic_selection import score_selection, ALLOWED_FIELDS

PROJECTS = {
    "billing": {
        "billing.py": (
            "def calculate_total(items, tax):\n"
            "    return sum(items) + tax\n"
        ),
        "service.py": (
            "from billing import calculate_total\n"
            "def checkout():\n"
            "    return calculate_total([10], 2)\n"
        ),
    },
    "configuration": {
        "configuration.py": (
            "def parse_flags(text, defaults):\n"
            "    return defaults\n"
        ),
        "runner.py": (
            "from configuration import parse_flags\n"
            "def bootstrap():\n"
            "    return parse_flags('x', {})\n"
        ),
    },
}
# Separate held-out labels; they are only read by the scoring harness.
# These deliberately reuse *capabilities* but not symbol names or projects.
CASES = [
    ("billing", "calculate_total", "Em qual arquivo calculate_total está definida?",
     ["path"], ["line"], False),
    ("billing", "calculate_total", "Quais parâmetros calculate_total declara?",
     ["signature"], [], False),
    ("billing", "calculate_total", "Quantas chamadas diretas existem para calculate_total?",
     ["direct_call_count"], [], False),
    ("billing", "calculate_total", "Quem chama calculate_total?",
     ["direct_call_sites"], [], False),
    ("billing", "calculate_total", "O que quebra se alterar calculate_total?",
     [], [], True),
    ("configuration", "parse_flags", "Onde parse_flags está definida?",
     ["path", "line"], [], False),
    ("configuration", "parse_flags", "Qual linha contém parse_flags?",
     ["line"], ["path"], False),
    ("configuration", "parse_flags", "Qual é a assinatura de parse_flags?",
     ["signature"], [], False),
    ("configuration", "parse_flags", "Qual a quantidade de chamadas de parse_flags?",
     ["direct_call_count"], [], False),
    ("configuration", "parse_flags", "Qual impacto de alterar parse_flags?",
     [], [], True),
]


def run(upstream: str, model: str) -> dict:
    opener = build_opener(ProxyHandler({}))
    results = []
    with tempfile.TemporaryDirectory(prefix="pie-des-holdout-") as workspace:
        for project, files in PROJECTS.items():
            root = Path(workspace) / project
            root.mkdir()
            for relative_path, content in files.items():
                (root / relative_path).write_text(content, encoding="utf-8")
            command_init(root)
            state = index_project(root)
            if state["index_state"] != "CURRENT":
                raise RuntimeError(f"Index not current for {project}")
            gateway = Gateway(root, upstream=upstream, model=model)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(gateway))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for case_id, (case_project, symbol, question, required, optional, abstain) in enumerate(CASES, 1):
                    if case_project != project:
                        continue
                    policy = {
                        "required": required, "optional": optional,
                        "forbidden": sorted(ALLOWED_FIELDS - set(required) - set(optional)),
                        "abstain": abstain,
                    }
                    data = json.dumps({
                        "question": question, "symbol": symbol,
                        "validation_mode": "dynamic_selection_schema",
                    }, ensure_ascii=False).encode("utf-8")
                    request = Request(
                        f"http://127.0.0.1:{server.server_port}/ask", data=data,
                        headers={"Content-Type": "application/json; charset=utf-8"},
                        method="POST")
                    started = time.perf_counter()
                    try:
                        with opener.open(request, timeout=60) as response:
                            payload = json.load(response)
                        verdict = payload.get("model_validation") or {}
                        chosen = verdict.get("selected_fields") or []
                        score = score_selection(chosen, policy)
                        certified = payload.get("status") == "CERTIFIED_FACTS" and verdict.get("status") == "VERIFIED"
                        pre_model_abstention = payload.get("status") == "ABSTAIN" and verdict.get("status") == "NOT_REQUESTED"
                        results.append({
                            "id": case_id, "project": project, "symbol": symbol,
                            "question": question, "gold_required": required,
                            "gold_optional": optional, "selected": chosen,
                            "semantically_sufficient": score["semantically_sufficient"] if not abstain else False,
                            "selection_exact": score["selection_exact"] if not abstain else False,
                            "gateway_certified": certified,
                            "safe_planner_abstention": bool(abstain and pre_model_abstention),
                            "model_status": verdict.get("status"), "status": payload.get("status"),
                            "reason": verdict.get("reason"),
                            "latency_s": round(time.perf_counter()-started, 4),
                            "error": None,
                        })
                    except Exception as exc:
                        results.append({
                            "id": case_id, "project": project, "symbol": symbol,
                            "question": question, "gold_required": required,
                            "gold_optional": optional, "selected": [],
                            "semantically_sufficient": False, "selection_exact": False,
                            "gateway_certified": False, "safe_planner_abstention": False,
                            "model_status": "ERROR", "status": "ERROR",
                            "reason": "request_failed",
                            "latency_s": round(time.perf_counter()-started, 4),
                            "error": type(exc).__name__,
                        })
                    print(f"case={case_id:02} project={project} "
                          f"status={results[-1]['status']} "
                          f"certified={results[-1]['gateway_certified']}", flush=True)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
    positives = [r for r in results if r["gold_required"]]
    negatives = [r for r in results if not r["gold_required"]]
    return {
        "design": "Held-out synthetic multi-project, multi-symbol integrated HTTP evaluation",
        "n": len(results), "projects": len(PROJECTS), "symbols": 2,
        "supported_n": len(positives), "abstention_n": len(negatives),
        "semantically_sufficient": sum(r["semantically_sufficient"] for r in positives),
        "exact_selection": sum(r["selection_exact"] for r in positives),
        "gateway_certified": sum(r["gateway_certified"] for r in positives),
        "pre_model_safe_abstentions": sum(r["safe_planner_abstention"] for r in negatives),
        "errors": sum(r["error"] is not None for r in results),
        "latency_mean_s": round(statistics.mean(r["latency_s"] for r in results), 3),
        "tokens": None,
        "limitations": [
            "Synthetic Python projects and intentionally small functions.",
            "Holdout validates codebase/symbol isolation, not broad generalization.",
            "Unsupported requests are intercepted by rules before Qwen.",
            "Never tune planner rules on this held-out set.",
        ],
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="PIE DES-03 held-out multi-project benchmark")
    parser.add_argument("--upstream", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--model", default="qwen3-4b-instruct-2507")
    parser.add_argument("--output", type=Path, default=Path("des03-holdout.json"))
    args = parser.parse_args()
    if args.upstream != "http://127.0.0.1:1234/v1":
        raise ValueError("Only the expected loopback LM Studio endpoint is permitted")
    report = run(args.upstream, args.model)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n",
                           encoding="utf-8")
    print("SUMMARY=" + json.dumps({k: v for k, v in report.items() if k != "results"}))
    if report["errors"] or report["gateway_certified"] != report["supported_n"] or (
        report["pre_model_safe_abstentions"] != report["abstention_n"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
