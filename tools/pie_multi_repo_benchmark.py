"""Multi-repository, source-grounded PIE retrieval benchmark (no model calls).

Runs on public repositories cloned by the companion GitHub Actions workflow.
Task oracles are selected before retrieval, using AST docstrings; the retrieval
algorithm never receives the oracle. Baseline: two independently ranked full
source files. Savings are estimated using UTF-8 bytes/4 and are NOT API tokens.
"""
from __future__ import annotations
import argparse
import ast
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pie.indexing.indexer import index_project
from pie.retrieval.intelligence import smart_context

STOP = set("a an the and or as of to in on at by with from for where what how which is are does do this that it its function method code returns return object value values all any use using can be".split())

def tokens(s):
    return set(re.findall(r"[a-z]{3,}", s.lower())) - STOP

def inventory(root):
    files = {}
    candidates = []
    for file in sorted(root.rglob("*.py")):
        if ".git" in file.parts or ".pie" in file.parts or any(part in {"tests", "test", "venv", ".venv"} for part in file.parts):
            continue
        try:
            body = file.read_text(encoding="utf-8-sig")
            if not 1500 <= len(body) <= 35000:
                continue
            tree = ast.parse(body)
        except (UnicodeError, OSError, SyntaxError):
            continue
        rel = file.relative_to(root).as_posix()
        files[rel] = body
        nodes = [(n, n.name) for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            nodes += [(n, cls.name + "." + n.name) for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for node, name in nodes:
            desc = re.split(r"(?<=[.!?])\s+|\n", (ast.get_docstring(node) or "").strip(), 1)[0]
            if 55 <= len(desc) <= 180 and len(tokens(desc)) >= 6:
                candidates.append({"path": rel, "symbol": name, "description": desc})
    return files, candidates

def one_repo(root, num, seed, repeats):
    t0 = time.perf_counter()
    index = index_project(root)
    index_ms = (time.perf_counter() - t0) * 1000
    if index.get("index_state") != "CURRENT":
        raise RuntimeError("Index not CURRENT: " + str(root))
    files, candidates = inventory(root)
    rng = random.Random(seed)
    rng.shuffle(candidates)
    picked = []
    seen = set()
    for c in candidates:
        if c["path"] in seen:
            continue
        seen.add(c["path"])
        picked.append(c)
        if len(picked) == num:
            break
    if len(picked) < num:
        raise RuntimeError(f"{root}: only {len(picked)} qualifying files; expected {num}")
    observations = []
    for case in picked:
        question = "Locate the implementation responsible for: " + case["description"]
        qterms = tokens(question)
        baseline_rank = sorted(files, key=lambda p: (-len(qterms & tokens(files[p])), p))
        baseline = "\n\n".join(files[p] for p in baseline_rank[:2])
        timings = []
        result = None
        for _ in range(repeats):
            start = time.perf_counter_ns()
            result = smart_context(root, question, max_chars=12000, limit=4, include_body=True)
            timings.append((time.perf_counter_ns() - start) / 1e6)
        assert result is not None
        evidence = result["evidence"]
        hit = any(e["path"] == case["path"] and e["symbol"] == case["symbol"] for e in evidence)
        output = json.dumps(result, ensure_ascii=False)
        saving = 100 * (1 - len(output.encode("utf8")) / max(1, len(baseline.encode("utf8"))))
        observations.append({
            "question": question, "oracle": {"path": case["path"], "symbol": case["symbol"]},
            "top4": [{"path": e["path"], "symbol": e["symbol"]} for e in evidence],
            "hit": hit, "baseline_file_hit": case["path"] in baseline_rank[:2],
            "baseline_bytes": len(baseline.encode("utf8")), "pie_bytes": len(output.encode("utf8")),
            "context_saving_pct": round(saving, 2), "latency_ms": timings,
        })
    samples = sorted(t for item in observations for t in item["latency_ms"])
    p95 = samples[max(0, int(.95 * (len(samples)-1)))]
    return {
        "repo": root.name, "indexed_files": len(files), "eligible_symbols": len(candidates),
        "index_ms": round(index_ms, 2), "questions": len(observations),
        "hit_at_4": round(sum(x["hit"] for x in observations)/len(observations), 4),
        "baseline_hit_at_2": round(sum(x["baseline_file_hit"] for x in observations)/len(observations), 4),
        "weighted_context_saving_pct": round(100*(1-sum(x["pie_bytes"] for x in observations)/max(1,sum(x["baseline_bytes"] for x in observations))), 2),
        "latency_p50_ms": round(statistics.median(samples), 3),
        "latency_p95_ms": round(p95, 3),
        "tests": observations,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repos", nargs="+", required=True)
    p.add_argument("--questions", type=int, default=12)
    p.add_argument("--repeats", type=int, default=7)
    p.add_argument("--output", default="pie-multi-repo-results.json")
    args = p.parse_args()
    if not 1 <= args.questions <= 100 or not 1 <= args.repeats <= 100:
        p.error("questions/repeats must be between 1 and 100")
    results = [one_repo(Path(path).resolve(), args.questions, 20261102, args.repeats) for path in args.repos]
    summary = {
        "method": "AST docstring oracle, hybrid FTS5 retrieval; two ranked complete files baseline",
        "token_note": "Bytes are a proxy for context volume, not actual API prompt tokens or billed token savings",
        "timing_note": "Warm local retrieval after indexing, includes JSON construction and SHA validation; no LLM/network",
        "repositories": [{k:v for k,v in r.items() if k != "tests"} for r in results],
        "aggregate_weighted_saving_pct": round(100*(1-sum(t["pie_bytes"] for r in results for t in r["tests"])/max(1,sum(t["baseline_bytes"] for r in results for t in r["tests"]))), 2),
        "aggregate_hit_at_4": round(sum(t["hit"] for r in results for t in r["tests"])/sum(len(r["tests"]) for r in results), 4),
        "targets": {"context_saving_at_least_85_pct": False, "latency_p95_at_most_0_9_ms": False},
    }
    summary["targets"]["context_saving_at_least_85_pct"] = summary["aggregate_weighted_saving_pct"] >= 85
    summary["targets"]["latency_p95_at_most_0_9_ms"] = all(r["latency_p95_ms"] <= .9 for r in results)
    Path(args.output).write_text(json.dumps({"summary": summary, "details": results}, indent=2), encoding="utf8")
    print(json.dumps(summary, indent=2))
    # Benchmark is diagnostic: persist evidence even when aggressive targets fail.
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
