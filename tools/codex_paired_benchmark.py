"""Reproducible paired Codex/MCP benchmark runner.

Model execution is opt-in. Raw JSONL is retained locally and a sanitized summary
is written for publication; no token value is inferred when usage is absent.
"""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, time
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

def main():
    p = argparse.ArgumentParser(); p.add_argument("--project", type=Path, required=True); p.add_argument("--prompt-without-pie", required=True); p.add_argument("--prompt-with-pie", required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--repetitions", type=int, default=5); p.add_argument("--run", action="store_true"); p.add_argument("--codex", default="codex"); p.add_argument("--bypass-approvals", action="store_true"); a = p.parse_args()
    files = sorted(p for p in a.project.rglob("*.py") if ".pie" not in p.parts)
    manifest = {str(p.relative_to(a.project)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    snapshot_hash = hashlib.sha256("".join(k+v for k,v in manifest.items()).encode()).hexdigest()
    records = []
    if a.run:
        for repeat in range(1, a.repetitions + 1):
            for mode, prompt in (("without_pie", a.prompt_without_pie), ("with_pie", a.prompt_with_pie)):
                raw = a.output.with_name(f"{a.output.stem}-{mode}-{repeat}.jsonl"); last = a.output.with_name(f"{a.output.stem}-{mode}-{repeat}.txt")
                cmd = [a.codex, "exec", "--ephemeral", "--json", "-C", str(a.project), "-s", "read-only", "-o", str(last)]
                if a.bypass_approvals: cmd.insert(4, "--dangerously-bypass-approvals-and-sandbox")
                started = time.perf_counter()
                with raw.open("w", encoding="utf-8") as stream: result = subprocess.run(cmd + [prompt], stdout=stream, stderr=subprocess.STDOUT, text=True, check=False)
                parsed = parse_events(raw); records.append({"repeat": repeat, "mode": mode, "returncode": result.returncode, "seconds": round(time.perf_counter()-started, 4), **parsed, "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest()})
    output = {"schema": "pie-codex-paired-benchmark-v1", "project": str(a.project), "snapshot_sha256": snapshot_hash, "files": len(files), "repetitions": a.repetitions, "executed": a.run, "records": records}
    a.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"snapshot_sha256": snapshot_hash, "files": len(files), "records": len(records), "executed": a.run}))

if __name__ == "__main__": main()
