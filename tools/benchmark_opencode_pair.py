"""Paired OpenCode 2.2.x comparison: same model/questions, isolated sessions.

Both servers MUST be started separately on loopback, with identical
read-only permissions. WITH connects only the PIE MCP; WITHOUT has no PIE.
No secrets, source excerpts or raw model transcripts are saved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pie.orchestrator.opencode_v2 import OpenCodeV2Adapter


def load_questions(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, list) or not data or
            len(data) > 100):
        raise ValueError("Expected 1-100 independently verified questions")
    seen: set[str] = set()
    for q in data:
        if (not isinstance(q, dict) or set(q) != {"id", "question", "gold"}
                or any(not isinstance(q[k], str) or not q[k].strip()
                       for k in ("id", "question", "gold"))
                or len(q["question"]) > 3000 or len(q["gold"]) > 160
                or q["id"] in seen):
            raise ValueError("Invalid or repeated question record")
        seen.add(q["id"])
    return data


def _tool_proofs(messages: list[dict], pie_name: str) -> list[dict]:
    proofs = []
    for msg in messages:
        if msg.get("type") != "assistant":
            continue
        for part in msg.get("content", []):
            if not isinstance(part, dict) or part.get("type") != "tool":
                continue
            name, state = part.get("name"), part.get("state")
            if not isinstance(name, str) or not isinstance(state, dict):
                continue
            canonical = {
                "pie_query", "pie_verified_evidence", "pie_build_context_pack",
                "pie_project_status", "pie_search_symbols", "pie_inspect_symbol",
                "pie_relationships", "pie_build_context", "pie_find_definitions",
                "pie_find_references", "pie_analysis_summary"
            }
            recognized = {
                variant for tool in canonical
                for variant in (tool, pie_name + "_" + tool,
                                "mcp__" + pie_name + "__" + tool)
            }
            if name not in recognized:
                continue
            if state.get("status") != "completed":
                raise RuntimeError("PIE tool call did not finish successfully")
            content = state.get("content")
            if not isinstance(content, list) or not content:
                raise RuntimeError("PIE tool response is empty")
            payload = json.dumps(content, sort_keys=True,
                                 ensure_ascii=False).encode("utf-8")
            proofs.append({"tool": name, "call_id": part.get("id"),
                           "sha256": hashlib.sha256(payload).hexdigest(),
                           "bytes": len(payload)})
    return proofs


def _parse_final(messages: list[dict], require_pie: bool,
                 pie_name: str = "pie") -> tuple[str, dict, list[dict]]:
    if not isinstance(messages, list):
        raise RuntimeError("OpenCode transcript is not a list")
    if not messages or messages[-1].get("type") != "idle" or (
            messages[-1].get("outcome") != "succeeded"):
        raise RuntimeError("No successful final idle event")
    assistant = [m for m in messages if m.get("type") == "assistant"]
    if not assistant or assistant[-1].get("finish") != "stop":
        raise RuntimeError("No terminal assistant with finish=stop")
    if any(m.get("error") for m in assistant):
        raise RuntimeError("Assistant reported error")
    proofs = _tool_proofs(messages, pie_name)
    if not require_pie:
        for msg in assistant:
            for part in msg.get("content", []):
                if (isinstance(part, dict) and part.get("type") == "tool"
                        and part.get("name") not in
                        {"read", "glob", "grep", "ls", "list"}):
                    raise RuntimeError("WITHOUT_PIE used unapproved tool")
    if require_pie and not proofs:
        raise RuntimeError("WITH_PIE contains no completed PIE tool call")
    if not require_pie and proofs:
        raise RuntimeError("WITHOUT_PIE used PIE tool unexpectedly")
    parts = assistant[-1].get("content", [])
    texts = [p.get("text", "") for p in parts
             if isinstance(p, dict) and p.get("type") == "text"
             and isinstance(p.get("text"), str)]
    joined = "\n".join(texts)
    matches = re.findall(r"(?im)^\s*ANSWER:\s*(.*?)\s*$", joined)
    if not matches or not matches[-1].strip() or len(matches[-1]) > 160:
        raise RuntimeError("Missing short ANSWER: line")
    metrics = assistant[-1].get("tokens")
    return matches[-1].strip(), metrics if isinstance(metrics, dict) else {}, proofs


def _root_and_mcp(adapter: OpenCodeV2Adapter, root: Path,
                  expect_pie: bool) -> dict:
    response = adapter._request("GET", "/mcp")
    if not isinstance(response, dict) or not adapter._location_matches(response, root):
        raise RuntimeError("Server workspace is not the authorized root")
    entries = adapter._data(response)
    if not isinstance(entries, list):
        raise RuntimeError("Unexpected MCP list format")
    pie = [e for e in entries if isinstance(e, dict)
           and e.get("name") == "pie"]
    if expect_pie:
        if len(pie) != 1 or not isinstance(pie[0].get("status"), dict) or (
                pie[0]["status"].get("status") != "connected"):
            raise RuntimeError("WITH_PIE server lacks connected pie MCP")
    elif pie:
        raise RuntimeError("WITHOUT_PIE server still exposes pie MCP")
    return {"mcp_pie": bool(pie), "root_verified": True}


def _one(adapter: OpenCodeV2Adapter, root: Path, model: str, question: str,
         timeout: float, with_pie: bool) -> dict:
    provider, sep, model_id = model.partition("/")
    if not sep or not provider or not model_id:
        raise ValueError("Model must be provider/model")
    start = time.monotonic()
    session_id = None
    try:
        session = adapter._data(adapter._request("POST", "/session", {
            "title": "PIE paired benchmark",
            "location": {"directory": str(root)},
            "model": {"providerID": provider, "id": model_id},
        }))
        if not isinstance(session, dict) or not isinstance(session.get("id"), str):
            raise RuntimeError("Session did not return an ID")
        if (not isinstance(session.get("location"), dict) or
                Path(session["location"].get("directory", "")).resolve() != root):
            raise RuntimeError("Session root mismatch")
        session_id = session["id"]
        sid = quote(session_id, safe="")
        prompt = ("Answer the following question using project evidence. "
                  "Return exactly one final line ANSWER: <short answer>. "
                  "Never invent source facts. "
                  + ("Use the connected PIE MCP for evidence. " if with_pie
                     else "Do not use PIE or any MCP; use only permitted native read tools. ")
                  + question)
        admitted = adapter._data(adapter._request(
            "POST", f"/session/{sid}/prompt", {"text": prompt, "resume": True}))
        if not isinstance(admitted, dict):
            raise RuntimeError("Prompt not admitted")
        deadline = start + timeout
        while time.monotonic() < deadline:
            active = adapter._data(adapter._request("GET", "/session/active"))
            if not isinstance(active, dict):
                raise RuntimeError("Invalid session activity map")
            if session_id not in active:
                response = adapter._request(
                    "GET", f"/session/{sid}/message?order=asc&limit=100")
                messages = adapter._data(response)
                try:
                    answer, metrics, proofs = _parse_final(messages, with_pie)
                except RuntimeError as exc:
                    if ("No successful final idle event" in str(exc) or
                            "No terminal assistant" in str(exc)):
                        time.sleep(0.4)
                        continue
                    raise
                return {"status": "COMPLETED", "session_id": session_id,
                        "answer": answer, "tokens": metrics,
                        "pie_proofs": proofs,
                        "latency_ms": round((time.monotonic()-start)*1000)}
            time.sleep(0.4)
        raise TimeoutError("OpenCode run did not finish before deadline")
    except Exception as exc:
        return {"status": "FAILED", "session_id": session_id,
                "error": type(exc).__name__,
                "latency_ms": round((time.monotonic()-start)*1000)}


def _number(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def summarize(rows: list[dict]) -> dict:
    comparable = []
    for row in rows:
        pair = [row["with_pie"], row["without_pie"]]
        if any(item["status"] != "COMPLETED" for item in pair):
            continue
        inputs = [_number(item["tokens"].get("input")) for item in pair]
        outputs = [_number(item["tokens"].get("output")) for item in pair]
        if None in inputs or None in outputs:
            continue
        comparable.append((row, inputs[0] + outputs[0],
                           inputs[1] + outputs[1]))
    used_with = sum(t[1] for t in comparable)
    used_without = sum(t[2] for t in comparable)
    return {
        "question_count": len(rows),
        "completed_pairs": sum(
            r["with_pie"]["status"] == "COMPLETED"
            and r["without_pie"]["status"] == "COMPLETED" for r in rows),
        "token_comparable_pairs": len(comparable),
        "with_pie_correct": sum(r["with_pie"].get("correct", False) for r in rows),
        "without_pie_correct": sum(r["without_pie"].get("correct", False) for r in rows),
        "comparable_with_pie_tokens": used_with if comparable else None,
        "comparable_without_pie_tokens": used_without if comparable else None,
        "token_savings_pct": (
            round(100 * (used_without - used_with) / used_without, 2)
            if comparable and used_without > 0 else None),
        "certified": len(comparable) == len(rows) and len(rows) > 0,
    }


def run(with_client: OpenCodeV2Adapter, without_client: OpenCodeV2Adapter,
        root: Path, model: str, questions: list[dict],
        timeout: float) -> dict:
    root = root.resolve(strict=True)
    _root_and_mcp(with_client, root, True)
    _root_and_mcp(without_client, root, False)
    rows = []
    for question in questions:
        results = {}
        for mode, client in (("without_pie", without_client),
                             ("with_pie", with_client)):
            result = _one(client, root, model, question["question"],
                          timeout, mode == "with_pie")
            answer = result.pop("answer", None)
            result["correct"] = (
                result["status"] == "COMPLETED" and
                isinstance(answer, str) and
                answer.casefold().strip() == question["gold"].casefold().strip())
            if isinstance(answer, str):
                result["answer_sha256"] = hashlib.sha256(answer.encode()).hexdigest()
            results[mode] = result
        rows.append({"id": question["id"],
                     "question_sha256": hashlib.sha256(
                         question["question"].encode()).hexdigest(),
                     **results})
    return {"schema": 1, "model": model, "root": str(root),
            "rows": rows, "summary": summarize(rows)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--with-url", default="http://127.0.0.1:4097")
    parser.add_argument("--without-url", default="http://127.0.0.1:4098")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    if args.timeout < 5 or args.timeout > 3600 or args.with_url == args.without_url:
        parser.error("Separate URLs and a timeout of 5-3600 seconds required")
    with_secret = os.environ.get("OPENCODE_WITH_PASSWORD", "")
    without_secret = os.environ.get("OPENCODE_WITHOUT_PASSWORD", "")
    if not with_secret or not without_secret:
        parser.error("Set local OPENCODE_WITH_PASSWORD and OPENCODE_WITHOUT_PASSWORD")
    data = run(OpenCodeV2Adapter(args.with_url, with_secret),
               OpenCodeV2Adapter(args.without_url, without_secret),
               args.root, args.model, load_questions(args.questions),
               args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error("Output already exists; use a fresh run-specific filename")
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps(data["summary"], sort_keys=True))
    return 0 if data["summary"]["certified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
