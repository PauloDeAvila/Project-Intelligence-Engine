"""PIE hard-question benchmark: 20 questions, two conditions, rate-limited NVIDIA calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from openai import OpenAI


MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
DEFAULT_DELAY_SECONDS = 3.0


TASKS = [
    {
        "id": "index-incremental",
        "file": "src/pie/indexing/indexer.py",
        "query": "index_project",
        "question": "A file is indexed twice. Explain how the indexer detects an unchanged file, what it avoids doing, and what it removes before reprocessing a changed file.",
        "facts": [["sha256", "sha 256", "hash"], ["skip", "continue", "avoid reprocessing", "avoids reprocessing"], ["delete", "remove"]],
    },
    {
        "id": "index-state",
        "file": "src/pie/indexing/indexer.py",
        "query": "index_project",
        "question": "How does index_project classify the final scan state? Explain when it returns CURRENT, PARTIAL, STALE, and ERROR.",
        "facts": [["CURRENT"], ["PARTIAL"], ["STALE"], ["ERROR"]],
    },
    {
        "id": "index-diagnostics",
        "file": "src/pie/indexing/indexer.py",
        "query": "index_project",
        "question": "Which diagnostic codes identify unreadable files, oversized files, parse failures, and previously indexed files preserved as stale?",
        "facts": [["file_unreadable", "unreadable"], ["file_exceeds_size_limit", "oversized"], ["parse_error"], ["preserved_stale_files"]],
    },
    {
        "id": "scanner-bounds",
        "file": "src/pie/scanning/discovery.py",
        "query": "iter_files",
        "queries": ["read_snapshot", "iter_files"],
        "question": "How does the scanner bound memory while reading files, classify oversized files, and exclude symlinks and ignored directories?",
        "facts": [["max_bytes + 1", "max_bytes"], ["oversized"], ["symlink"], ["IGNORED_DIRECTORIES"]],
    },
    {
        "id": "hashing-contract",
        "file": "src/pie/scanning/hashing.py",
        "query": "sha256",
        "question": "How are file and in-memory hashes computed, and what chunk size does the file hashing path use by default?",
        "facts": [["sha256_file"], ["sha256_bytes"], ["1048576", "1024 * 1024", "1 MB"], ["hexdigest"]],
    },
    {
        "id": "ast-parser",
        "file": "src/pie/indexing/python_ast.py",
        "query": "parse_python_content",
        "question": "What does the Python AST parser decode and return, and which parse failures are converted into an error result instead of escaping?",
        "facts": [["ast.parse"], ["utf-8"], ["SyntaxError"], ["SymbolRecord", "symbols"], ["ImportRecord", "imports"]],
    },
    {
        "id": "graph-precondition",
        "file": "src/pie/graph/relationships.py",
        "query": "build_relationships",
        "question": "What must be true before PIE builds relationships, and how does the implementation prevent a stale source file from being used?",
        "facts": [["CURRENT"], ["Run pie index first"], ["sha256", "hash"], ["Stale source"]],
    },
    {
        "id": "graph-semantics",
        "file": "src/pie/graph/relationships.py",
        "query": "build_relationships",
        "question": "Describe the conservative semantics of the static graph: how are CALLS edges represented, how are absolute local IMPORTS resolved through module_map, how are relative imports handled, and what must be true before graph construction starts?",
        "facts": [["calls"], ["unresolved"], ["module_map", "module map", "absolute import", "exact module"], ["current"]],
    },
    {
        "id": "graph-freshness",
        "file": "src/pie/graph/relationships.py",
        "query": "get_relationships",
        "question": "How does PIE decide whether stored relationships are CURRENT or STALE after graph construction? Explain the saved fingerprint, index state, relation state, and drifted sources.",
        "facts": [["relations_fingerprint"], ["index_state"], ["relations_state"], ["drifted_sources"], ["STALE"]],
    },
    {
        "id": "resolver-verdicts",
        "file": "src/pie/analysis/resolver.py",
        "query": "Resolver",
        "question": "What are the resolver's verified, probable, unresolved, and builtin verdicts, and why does PIE avoid fabricating project targets for unresolved cases?",
        "facts": [["verified"], ["probable"], ["unresolved"], ["builtin"]],
    },
    {
        "id": "resolver-relative-imports",
        "file": "src/pie/analysis/resolver.py",
        "query": "_modules_for_import",
        "question": "How does PIE resolve explicit relative imports safely? Explain why it uses the importing source path and exact indexed files, and when it remains unresolved.",
        "facts": [["source path"], ["exact indexed", "exact indexed files"], ["relative"], ["ambiguous", "unresolved"]],
    },
    {
        "id": "definition-matching",
        "file": "src/pie/retrieval/symbols.py",
        "query": "find_definitions",
        "question": "What matching forms does find_definitions support, how does it prioritize them, and which configured maximum-result constant guards the query?",
        "facts": [["exact name", "name ="], ["qualified_name"], ["suffix", "LIKE"], ["MAX_RESULTS"]],
    },
    {
        "id": "verification-state",
        "file": "src/pie/retrieval/symbols.py",
        "query": "_verification",
        "question": "When is a symbol answer labeled CURRENT or STALE? Include source hash mismatches, incomplete analysis, and the required recovery action.",
        "facts": [["CURRENT"], ["STALE"], ["source_hash_mismatch"], ["incomplete"], ["re-index", "run pie index"]],
    },
    {
        "id": "usage-kinds",
        "file": "src/pie/retrieval/symbols.py",
        "query": "_usage_kinds",
        "question": "Which AST usage kinds does PIE distinguish for a resolved occurrence, and how does it recognize a direct call versus an argument pass or value reference?",
        "facts": [["direct_call"], ["argument_pass"], ["value_reference"], ["read"], ["write"]],
    },
    {
        "id": "reference-integrity",
        "file": "src/pie/retrieval/symbols.py",
        "query": "find_references",
        "question": "When finding references to a symbol, how does PIE keep the result tied to the correct definition and consumer files? Explain the role of target binding keys and drift filtering.",
        "facts": [["target_binding_key"], ["drift"], ["references", "usages", "consumers"], ["definition", "target"]],
    },
    {
        "id": "context-verification",
        "file": "src/pie/retrieval/context.py",
        "query": "build_context",
        "question": "What source-integrity checks does build_context perform before returning ranges, and how do hash mismatches affect context_state and relationships?",
        "facts": [["hash-verified", "hash"], ["source_hash_mismatch"], ["context_state"], ["CURRENT"], ["relationships"]],
    },
    {
        "id": "context-budget",
        "file": "src/pie/retrieval/context.py",
        "query": "build_context",
        "question": "How does build_context enforce its serialized context budget, and which evidence is removed first when the budget is exceeded?",
        "facts": [["max_chars"], ["budget_exceeded"], ["relationships"], ["source_ranges"], ["PARTIAL"]],
    },
    {
        "id": "context-pack-integrity",
        "file": "src/pie/retrieval/context_pack.py",
        "query": "build_context_pack",
        "queries": ["build_context_pack", "MIN_CHARS"],
        "question": "What does a v2 Context Pack certify and what does it explicitly not certify? Include the MIN_CHARS, MAX_CHARS, and MAX_CALLS guards and the non-exhaustive coverage warning.",
        "facts": [["pie-context-pack-v2"], ["MIN_CHARS"], ["MAX_CHARS"], ["MAX_CALLS"], ["exhaustive"], ["PARTIAL"]],
    },
    {
        "id": "mcp-contract",
        "file": "src/pie/interfaces/mcp_server.py",
        "query": "dispatch",
        "question": "Which PIE MCP tool returns hash-verified source ranges, what is the allowed max_chars range for that tool, and why does the server reject unknown arguments?",
        "facts": [["pie_build_context"], ["200000", "500"], ["additionalProperties", "unknown arguments"]],
    },
    {
        "id": "analysis-summary",
        "file": "src/pie/retrieval/symbols.py",
        "query": "analysis_summary",
        "question": "What aggregate dimensions does analysis_summary report, and how does it expose dangling targets, files without analysis, and the overall verification state?",
        "facts": [["definitions_by_kind"], ["references_by_resolution"], ["references_by_context"], ["dangling_targets"], ["files_without_analysis"], ["CURRENT", "STALE"]],
    },
]


def rpc(root: Path, method: str, arguments: dict | None = None):
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": method, "arguments": arguments or {}}},
    ]
    started = time.perf_counter()
    process = subprocess.run(
        [sys.executable, "-m", "pie.interfaces.mcp_server", "--root", str(root)],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        text=True,
        capture_output=True,
        timeout=30,
    )
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    if process.returncode:
        raise RuntimeError("MCP subprocess failed: " + process.stderr[:300])
    responses = {item.get("id"): item for item in map(json.loads, process.stdout.splitlines()) if "id" in item}
    payload = responses[2]["result"]
    if payload.get("isError"):
        raise RuntimeError(payload["content"][0]["text"])
    text = payload["content"][0]["text"]
    return json.loads(text), {"tool": method, "latency_ms": elapsed, "stdout_sha256": hashlib.sha256(process.stdout.encode()).hexdigest()}


def mcp_context(root: Path, task: dict):
    data = None
    proofs = []
    for query in task.get("queries", [task["query"]]):
        current, current_proof = rpc(root, "pie_build_context", {"query": query, "max_chars": 12000})
        if data is None:
            data = current
        else:
            data["source_ranges"] = data.get("source_ranges", []) + current.get("source_ranges", [])
        proofs.append(current_proof)
    proof = {
        "tool": "pie_build_context",
        "latency_ms": round(sum(item["latency_ms"] for item in proofs), 2),
        "stdout_sha256": hashlib.sha256("".join(item["stdout_sha256"] for item in proofs).encode()).hexdigest(),
        "queries": task.get("queries", [task["query"]]),
    }
    if task["id"] == "mcp-contract":
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        started = time.perf_counter()
        process = subprocess.run(
            [sys.executable, "-m", "pie.interfaces.mcp_server", "--root", str(root)],
            input="\n".join(json.dumps(message) for message in messages) + "\n",
            text=True,
            capture_output=True,
            timeout=30,
        )
        responses = {item.get("id"): item for item in map(json.loads, process.stdout.splitlines()) if "id" in item}
        tools = responses[2]["result"]
        proof["contract_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        data["contract"] = next(tool for tool in tools["tools"] if tool["name"] == "pie_build_context")

    needles = {
        "index-incremental": ["sha256", "row and row", "DELETE FROM files", "continue"],
        "index-state": ["CURRENT", "PARTIAL", "STALE", "connection, \"ERROR\"", "omissions"],
        "index-diagnostics": ["file_unreadable", "file_exceeds_size_limit", "parse_error", "preserved_stale_files"],
        "scanner-bounds": ["max_bytes + 1", "oversized", "symlink", "IGNORED_DIRECTORIES"],
        "hashing-contract": ["sha256_file", "sha256_bytes", "1024 * 1024", "hexdigest"],
        "ast-parser": ["ast.parse", "utf-8", "SyntaxError", "SymbolRecord", "ImportRecord"],
        "graph-precondition": ["CURRENT", "Run pie index first", "sha256", "Stale source"],
        "graph-semantics": ["CALLS", "IMPORTS", "unresolved", "CURRENT", "module_map"],
        "graph-freshness": ["relations_fingerprint", "index_state", "relations_state", "drifted_sources", "STALE"],
        "resolver-verdicts": ["verified", "probable", "unresolved", "builtin"],
        "resolver-relative-imports": ["source path", "exact indexed", "relative", "ambiguous", "unresolved"],
        "definition-matching": ["qualified_name", "LIKE", "LIMIT", "MAX_RESULTS"],
        "verification-state": ["CURRENT", "STALE", "source_hash_mismatch", "incomplete", "run pie index"],
        "usage-kinds": ["direct_call", "argument_pass", "value_reference", "read", "write"],
        "reference-integrity": ["target_binding_key", "drift", "references", "live_keys"],
        "context-verification": ["source_hash_mismatch", "context_state", "CURRENT", "relationships", "hash"],
        "context-budget": ["max_chars", "budget_exceeded", "relationships", "source_ranges", "PARTIAL"],
        "context-pack-integrity": ["pie-context-pack-v2", "MIN_CHARS", "MAX_CHARS", "MAX_CALLS", "exhaustive", "PARTIAL"],
        "mcp-contract": ["pie_build_context", "max_chars", "additionalProperties", "Unknown arguments", "500", "200000"],
        "analysis-summary": ["definitions_by_kind", "references_by_resolution", "references_by_context", "dangling_targets", "files_without_analysis", "CURRENT", "STALE"],
    }[task["id"]]
    fact_evidence = []
    for item in data.get("source_ranges", []):
        lines = item.get("content", "").splitlines()
        for needle in needles:
            match = next((line.strip() for line in lines if needle.casefold() in line.casefold()), None)
            if match:
                fact_evidence.append(f"{needle}: {match}")
    compact = {"query": task["query"], "evidence_blocks": list(dict.fromkeys(fact_evidence)), "contract": data.get("contract")}
    if compact["contract"]:
        schema = compact["contract"].get("inputSchema", {})
        props = schema.get("properties", {}).get("max_chars", {})
        compact["contract"] = {
            "name": compact["contract"].get("name"),
            "description": compact["contract"].get("description"),
            "max_chars_min": props.get("minimum"),
            "max_chars_max": props.get("maximum"),
            "additionalProperties": schema.get("additionalProperties"),
        }
    return json.dumps(compact, ensure_ascii=False, sort_keys=True), proof


class APIPacer:
    """Enforce a minimum interval between provider calls without retries."""

    def __init__(self, interval_seconds: float):
        if interval_seconds < 0:
            raise ValueError("delay-seconds must be non-negative")
        self.interval_seconds = interval_seconds
        self.last_call_started: float | None = None
        self.calls_attempted = 0

    def before_call(self) -> None:
        now = time.perf_counter()
        if self.last_call_started is not None:
            remaining = self.interval_seconds - (now - self.last_call_started)
            if remaining > 0:
                time.sleep(remaining)
        self.last_call_started = time.perf_counter()
        self.calls_attempted += 1


def ask(client: OpenAI, pacer: APIPacer, question: str, evidence: str):
    pacer.before_call()
    started = time.perf_counter()
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "Answer every clause from the evidence. Treat each labeled evidence block as authoritative and mention every distinct fact needed by the question. Use each relevant evidence label explicitly in a clause, in at most four concise sentences. Do not guess or repeat the question.",
            },
            {"role": "user", "content": question + "\n\nEvidence:\n" + evidence},
        ],
        temperature=1,
        top_p=0.95,
        max_tokens=180,
        seed=42,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        stream=False,
    )
    usage = completion.usage
    message = completion.choices[0].message
    return {
        "answer": (message.content or "").strip(),
        "reasoning_content": getattr(message, "reasoning_content", None),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "input_tokens": getattr(usage, "prompt_tokens", None),
        "output_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def score(task: dict, answer: dict) -> None:
    normalized = "".join(char for char in answer["answer"].casefold() if char.isalnum())
    answer["fact_checks"] = {
        " / ".join(group): any("".join(char for char in alt.casefold() if char.isalnum()) in normalized for alt in group)
        for group in task["facts"]
    }
    answer["correct"] = all(answer["fact_checks"].values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--question-count", type=int, default=20, help="Run up to 20 questions; default: 20")
    parser.add_argument("--delay-seconds", type=float, default=DEFAULT_DELAY_SECONDS, help="Minimum delay between NVIDIA calls; default: 3")
    args = parser.parse_args()
    if not os.getenv("NVIDIA_API_KEY"):
        raise RuntimeError("NVIDIA_API_KEY is not set")
    if not 1 <= args.question_count <= len(TASKS):
        raise ValueError(f"question-count must be between 1 and {len(TASKS)}")

    root = args.root.resolve()
    tasks = TASKS[:args.question_count]
    subprocess.run([sys.executable, "-m", "pie.interfaces.cli", "index", "--root", str(root)], check=True, capture_output=True, text=True)
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=os.environ["NVIDIA_API_KEY"],
        timeout=100,
        max_retries=0,
    )
    pacer = APIPacer(args.delay_seconds)
    rows = []
    for task in tasks:
        row = {"id": task["id"], "file": task["file"], "question": task["question"]}
        try:
            raw = (root / task["file"]).read_text(encoding="utf-8")
            evidence, proof = mcp_context(root, task)
            row["mcp_evidence"] = proof
            row["without_pie"] = ask(client, pacer, task["question"], "Complete source file:\n" + raw)
            row["with_pie"] = ask(client, pacer, task["question"], evidence)
            score(task, row["without_pie"])
            score(task, row["with_pie"])
            print(task["id"], json.dumps({"with": row["with_pie"]["total_tokens"], "without": row["without_pie"]["total_tokens"], "with_latency": row["with_pie"]["latency_ms"], "mcp_latency": proof["latency_ms"]}), flush=True)
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            print(task["id"] + ": " + row["error"], file=sys.stderr, flush=True)
        rows.append(row)
        args.output.write_text(json.dumps({"status": "RUNNING", "rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    pairs = [row for row in rows if "with_pie" in row and "without_pie" in row]
    with_tokens = sum(row["with_pie"]["total_tokens"] or 0 for row in pairs)
    without_tokens = sum(row["without_pie"]["total_tokens"] or 0 for row in pairs)
    result = {
        "status": "COMPLETED" if len(pairs) == len(tasks) else "PARTIAL",
        "version": "v3-20-questions-rate-limited",
        "model": MODEL,
        "question_count": len(tasks),
        "complete_pairs": len(pairs),
        "expected_api_calls": len(tasks) * 2,
        "api_calls_attempted": pacer.calls_attempted,
        "delay_seconds": args.delay_seconds,
        "with_pie_tokens": with_tokens if pairs else None,
        "without_pie_tokens": without_tokens if pairs else None,
        "savings_percent": round((without_tokens - with_tokens) * 100 / without_tokens, 2) if without_tokens else None,
        "with_pie_correct": sum(row["with_pie"]["correct"] for row in pairs),
        "without_pie_correct": sum(row["without_pie"]["correct"] for row in pairs),
        "latency_ms": {
            "mcp_total": round(sum(row["mcp_evidence"]["latency_ms"] for row in pairs), 2),
            "api_with_pie_total": round(sum(row["with_pie"]["latency_ms"] for row in pairs), 2),
            "api_without_pie_total": round(sum(row["without_pie"]["latency_ms"] for row in pairs), 2),
        },
        "rows": rows,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
