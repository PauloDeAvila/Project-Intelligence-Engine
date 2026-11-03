"""Reproducible paired Codex/MCP benchmark runner.

Model execution is opt-in. Raw JSONL is retained locally and a sanitized summary
is written for publication; no token value is inferred when usage is absent.
"""
from __future__ import annotations
import argparse, hashlib, json, os, platform, re, subprocess, sys, time
from pathlib import Path

def scrub(value):
    text = str(value or "")
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(token|secret|password|api[_-]?key)(\s*[:=]\s*)[^\s,;]+", r"\1\2[REDACTED]", text)
    return text

def parse_events(path):
    usage = None; mcp = []; final = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try: event = json.loads(line)
        except json.JSONDecodeError: continue
        if event.get("type") == "turn.completed": usage = event.get("usage")
        item = event.get("item", {})
        if item.get("type") == "mcp_tool_call":
            mcp.append({"server": scrub(item.get("server")), "tool": scrub(item.get("tool")), "status": item.get("status"), "error": scrub((item.get("error") or {}).get("message"))})
        if item.get("type") == "agent_message": final = scrub(item.get("text"))
    pie = [x for x in mcp if str(x.get("server", "")).startswith("pie-")]
    return {"usage": usage, "pie_mcp_executed": any(x["status"] == "completed" for x in pie), "mcp_calls": mcp, "final": final}

def manifest(root, pie_source_root):
    sys.path.insert(0, str(pie_source_root))
    from pie.scanning.discovery import iter_files
    records = list(iter_files(root))
    rows = {record.path.as_posix(): record.sha256 for record in records}
    digest = hashlib.sha256("".join(k+v for k,v in rows.items()).encode()).hexdigest()
    return rows, digest

def sanitize_jsonl(source, destination):
    with source.open(encoding="utf-8", errors="replace") as inp, destination.open("w", encoding="utf-8") as out:
        for line in inp:
            try: out.write(json.dumps(json.loads(scrub(line)), ensure_ascii=False) + "\n")
            except json.JSONDecodeError: out.write(scrub(line))

def _relative_evidence_path(value, project):
    raw = str(value or "").replace("\\", "/")
    root = str(project).replace("\\", "/").rstrip("/") + "/"
    if raw.startswith(root):
        return raw[len(root):]
    for marker in ("ai_mesh_doctor/", "tests/"):
        index = raw.find(marker)
        if index >= 0:
            return raw[index:]
    return raw

def structured_score(final, gold, symbol, project):
    try:
        text = final.strip().removeprefix("```json").removesuffix("```").strip()
        data = json.loads(text)
    except (AttributeError, json.JSONDecodeError): return {"passed": False, "reason": "invalid_json"}
    definition = data.get("definition") or {}; path = definition.get("path") or definition.get("file")
    line = definition.get("line")
    callers = data.get("callers") or []
    actual = set()
    for caller in callers:
        if not isinstance(caller, dict):
            continue
        base = _relative_evidence_path(caller.get("path") or caller.get("file"), project)
        nested = caller.get("calls")
        if isinstance(nested, list):
            actual.update((base, item.get("line")) for item in nested if isinstance(item, dict))
        else:
            actual.add((base, caller.get("line")))
    expected_definition = gold["definitions"][symbol]
    expected = {(c[0], c[1]) for c in gold["callers"][symbol]}
    definition_match = _relative_evidence_path(path, project) == expected_definition[0] and line == expected_definition[1]
    return {"passed": definition_match and actual == expected, "definition_match": definition_match, "callers_match": actual == expected, "actual_call_count": len(actual), "expected_call_count": len(expected)}

def main():
    p = argparse.ArgumentParser(); p.add_argument("--project", type=Path, required=True); p.add_argument("--pie-source-root", type=Path, required=True); p.add_argument("--prompt-without-pie", required=True); p.add_argument("--prompt-with-pie", required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--gold", type=Path, required=True); p.add_argument("--symbol", required=True); p.add_argument("--repetitions", type=int, default=5); p.add_argument("--run", action="store_true"); p.add_argument("--codex", default="codex"); p.add_argument("--model"); p.add_argument("--bypass-approvals", action="store_true"); a = p.parse_args()
    files, snapshot_hash = manifest(a.project, a.pie_source_root)
    gold = json.loads(a.gold.read_text(encoding="utf-8"))
    prompt_hashes = {"without_pie": hashlib.sha256(a.prompt_without_pie.encode()).hexdigest(), "with_pie": hashlib.sha256(a.prompt_with_pie.encode()).hexdigest()}
    try: codex_version = subprocess.check_output([a.codex, "--version"], text=True, stderr=subprocess.STDOUT).strip()
    except Exception: codex_version = None
    try: git_commit = subprocess.check_output(["git", "-C", str(a.project), "rev-parse", "HEAD"], text=True, stderr=subprocess.STDOUT).strip()
    except Exception: git_commit = None
    records = []
    if a.run:
        for repeat in range(1, a.repetitions + 1):
            for mode, prompt in (("without_pie", a.prompt_without_pie), ("with_pie", a.prompt_with_pie)):
                raw = a.output.with_name(f"{a.output.stem}-{mode}-{repeat}.jsonl"); last = a.output.with_name(f"{a.output.stem}-{mode}-{repeat}.txt")
                cmd = [a.codex, "exec", "--ephemeral", "--json", "-C", str(a.project), "-s", "read-only", "-o", str(last)]
                if a.model: cmd += ["-m", a.model]
                if mode == "without_pie": cmd += ["--ignore-user-config"]
                if a.bypass_approvals: cmd.insert(4, "--dangerously-bypass-approvals-and-sandbox")
                started = time.perf_counter()
                with raw.open("w", encoding="utf-8") as stream: result = subprocess.run(cmd + [prompt], stdout=stream, stderr=subprocess.STDOUT, text=True, check=False)
                parsed = parse_events(raw); sanitized = raw.with_suffix(".sanitized.jsonl"); sanitize_jsonl(raw, sanitized); final = parsed.get("final") or ""; records.append({"repeat": repeat, "mode": mode, "returncode": result.returncode, "seconds": round(time.perf_counter()-started, 4), "quality": structured_score(final, gold, a.symbol, a.project), **parsed, "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(), "sanitized_sha256": hashlib.sha256(sanitized.read_bytes()).hexdigest()})
        _, after_hash = manifest(a.project, a.pie_source_root)
        if after_hash != snapshot_hash: raise SystemExit("Project snapshot changed during benchmark")
    output = {"schema": "pie-codex-paired-benchmark-v2", "project": str(a.project), "snapshot_sha256": snapshot_hash, "project_git_commit": git_commit, "codex_version": codex_version, "model": a.model or "codex-config-default", "model_argument_passed": bool(a.model), "symbol": a.symbol, "platform": platform.platform(), "python": platform.python_version(), "prompts": {mode: {"sha256": prompt_hashes[mode], "sanitized_path": str(a.output.with_name(mode + ".prompt.txt"))} for mode in prompt_hashes}, "files": len(files), "gold": str(a.gold), "repetitions": a.repetitions, "executed": a.run, "records": records}
    for mode, prompt in (("without_pie", a.prompt_without_pie), ("with_pie", a.prompt_with_pie)):
        a.output.with_name(mode + ".prompt.txt").write_text(scrub(prompt), encoding="utf-8")
    a.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"snapshot_sha256": snapshot_hash, "files": len(files), "records": len(records), "executed": a.run}))

if __name__ == "__main__": main()
