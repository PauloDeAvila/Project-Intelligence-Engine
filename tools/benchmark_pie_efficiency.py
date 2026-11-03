"""Paired Doctor Mesh retrieval benchmark (direct reads vs PIE MCP).

This measures the evidence pipeline only. It does not invoke a Codex model and
therefore never fabricates inference-token counts. Both conditions use the same
frozen source snapshot and five paired repetitions by default.
"""
from __future__ import annotations

import argparse, ast, hashlib, json, os, statistics, subprocess, sys, time
from pathlib import Path

TASKS = ["audit_component", "MeasurementCache.get", "analyze_mesh", "validate_change", "content_key"]

def snapshot(root: Path):
    files = {}
    for path in sorted(root.rglob("*.py")):
        if ".pie" in path.parts or any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        raw = path.read_bytes()
        files[path.relative_to(root).as_posix()] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "raw": raw}
    return files

def direct_calls(files, symbol):
    # Qualified-method callers require binding-aware resolution. The v2
    # contract deliberately returns no callers when an instance binding cannot
    # be proven; do not score unrelated ``get(...)`` calls as this method.
    if "." in symbol:
        return []
    name = symbol.rsplit(".", 1)[-1]
    rows = []
    for rel, meta in files.items():
        try: tree = ast.parse(meta["raw"].decode("utf-8-sig"), filename=rel)
        except (SyntaxError, UnicodeDecodeError): continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call): continue
            fn = node.func
            called = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
            if called == name:
                rows.append({"path": rel, "line": node.lineno})
    return sorted(rows, key=lambda r: (r["path"], r["line"]))

def rpc(proc, ident, method, params=None):
    proc.stdin.write(json.dumps({"jsonrpc":"2.0", "id":ident, "method":method, "params":params or {}}) + "\n")
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line: raise RuntimeError("MCP process exited without a response")
        reply = json.loads(line)
        if reply.get("id") == ident: return reply

def run_pie(python, source_root, project_root, symbols):
    env = os.environ.copy(); env["PYTHONPATH"] = str(source_root / "src")
    proc = subprocess.Popen([str(python), "-u", "-m", "pie.interfaces.mcp_server", "--root", str(project_root)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", env=env)
    try:
        rpc(proc, 1, "initialize", {"protocolVersion":"2025-03-26", "capabilities":{}, "clientInfo":{"name":"efficiency-benchmark","version":"1"}})
        for i, symbol in enumerate(symbols, 2):
            started = time.perf_counter(); reply = rpc(proc, i, "tools/call", {"name":"pie_build_context_pack", "arguments":{"symbol":symbol, "max_chars":32000, "max_calls":100}})
            elapsed = time.perf_counter() - started
            text = reply["result"]["content"][0]["text"]
            yield symbol, json.loads(text), elapsed
    finally:
        proc.kill(); proc.wait(timeout=5)

def score(pack, gold):
    got = sorted({(c.get("path"), c.get("line")) for c in pack.get("callers", [])})
    expected = sorted({(r["path"], r["line"]) for r in gold})
    tp = len(set(got) & set(expected)); precision = tp / len(got) if got else (1.0 if not expected else 0.0)
    recall = tp / len(expected) if expected else (1.0 if not got else 0.0)
    definition = pack.get("definition", {})
    return {"precision": precision, "recall": recall, "definition_present": bool(definition.get("path")), "returned_calls": len(got), "gold_calls": len(expected)}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--project-root", type=Path, required=True); ap.add_argument("--source-root", type=Path, required=True); ap.add_argument("--python", type=Path, required=True); ap.add_argument("--repetitions", type=int, default=5); ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args(); frozen = snapshot(a.project_root); gold = {s: direct_calls(frozen, s) for s in TASKS}; records = []
    for repeat in range(1, a.repetitions + 1):
        for mode in ("without_pie", "with_pie"):
            started = time.perf_counter(); source_bytes = 0; calls = []
            if mode == "without_pie":
                for symbol in TASKS: calls.append((symbol, {"callers": direct_calls(frozen, symbol), "definition": {"path": "direct-read"}}, 0.0))
                source_bytes = sum(x["bytes"] for x in frozen.values())
            else:
                for symbol, pack, elapsed in run_pie(a.python, a.source_root, a.project_root, TASKS):
                    # Count the definition/caller files actually re-read after MCP.
                    paths = {pack.get("definition", {}).get("path")} | {c.get("path") for c in pack.get("callers", [])}
                    source_bytes += sum(frozen[p]["bytes"] for p in paths if p in frozen)
                    calls.append((symbol, pack, elapsed))
            elapsed = time.perf_counter() - started
            scored = {s: score(p, gold[s]) for s, p, _ in calls}
            records.append({"repeat": repeat, "mode": mode, "seconds": elapsed, "mcp_seconds": sum(x[2] for x in calls), "source_bytes_read": source_bytes, "complementary_source_reads": len(calls) if mode == "with_pie" else 0, "scores": scored, "prompt_tokens": None})
    result = {"schema":"pie-efficiency-benchmark-v1", "project":str(a.project_root), "repetitions":a.repetitions, "tasks":TASKS, "snapshot":{"files":len(frozen), "sha256":hashlib.sha256("".join(f+v["sha256"] for f,v in sorted(frozen.items())).encode()).hexdigest()}, "token_telemetry":"unavailable", "records":records}
    a.output.parent.mkdir(parents=True, exist_ok=True); a.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    for mode in ("without_pie", "with_pie"):
        rows = [r for r in records if r["mode"] == mode]
        print(mode, "n=", len(rows), "median_seconds=", round(statistics.median(r["seconds"] for r in rows), 4), "median_bytes=", statistics.median(r["source_bytes_read"] for r in rows))

if __name__ == "__main__": main()
