"""Summarize Codex exec JSONL runs without inventing token data."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def analyze(path: Path):
    usage = None; tool_calls = []; final = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try: event = json.loads(line)
        except json.JSONDecodeError: continue
        if event.get("type") == "turn.completed": usage = event.get("usage")
        item = event.get("item", {})
        if item.get("type") == "mcp_tool_call":
            tool_calls.append({"server": item.get("server"), "tool": item.get("tool"), "status": item.get("status"), "error": (item.get("error") or {}).get("message")})
        if item.get("type") == "agent_message": final = item.get("text")
    return {"run": str(path), "usage": usage, "mcp_tool_calls": tool_calls, "mcp_executed": any(x["status"] == "completed" for x in tool_calls), "final": final}

def main():
    p = argparse.ArgumentParser(); p.add_argument("runs", nargs="+", type=Path); p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    result = {"schema": "codex-token-run-v1", "runs": [analyze(path) for path in a.runs]}
    a.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for run in result["runs"]: print(run["run"], run["usage"], "mcp_executed=", run["mcp_executed"])

if __name__ == "__main__": main()
