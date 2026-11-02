"""RTK-inspired loss-aware adapters for PIE context and tool output.

Independent Python implementation of RTK's public design principles:
filtering, grouping, truncation with recovery, and deduplication.
No RTK code or bundled binaries are copied.
"""
from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_SENSITIVE = re.compile(
    r"(?i)(authorization\s*:\s*bearer\s+\S+|(?:sk-[A-Za-z0-9_-]{12,})|"
    r"(?:api[_-]?key|password|token)\s*[:=]\s*['\"]?[A-Za-z0-9_.-]{10,})"
)

def mask_secrets(text: str) -> str:
    """Mask common credential patterns before sending diagnostic output to a model."""
    return _SENSITIVE.sub("[REDACTED]", text)

def compress_tool_output(text: str, *, kind: str = "log",
                         max_chars: int = 12000) -> dict:
    """Compact repetitive tool output while retaining all unique failures.

    Never silently truncate: an overflow is explicitly marked as partial and
    the caller can request the complete original content from its source.
    """
    if max_chars < 256:
        raise ValueError("max_chars must be at least 256")
    raw = mask_secrets(_ANSI.sub("", text))
    lines = [line.rstrip() for line in raw.splitlines()]
    significant = []
    counts = Counter()
    for line in lines:
        normalized = line.strip()
        if not normalized:
            continue
        counts[normalized] += 1
        if counts[normalized] == 1:
            significant.append(normalized)
    if kind in {"pytest", "unittest"}:
        def order(line: str) -> tuple[int, str]:
            urgent = bool(re.search(r"FAIL|ERROR|Traceback|AssertionError|failed", line, re.I))
            return (0 if urgent else 1, line)
        significant.sort(key=order)
    output = []
    total = 0
    omitted = 0
    for line in significant:
        repeat = counts[line]
        representation = line if repeat == 1 else f"{line} [repeated {repeat}x]"
        if total + len(representation) + 1 > max_chars - 110:
            omitted += 1
            continue
        output.append(representation)
        total += len(representation) + 1
    state = "PARTIAL" if omitted else "COMPLETE"
    summary = f"[{kind}; {state}; source_lines={len(lines)}; unique_lines={len(significant)}; omitted_unique={omitted}]"
    return {
        "state": state,
        "output": summary + "\n" + "\n".join(output),
        "source_bytes": len(raw.encode("utf-8")),
        "output_bytes": len((summary + "\n" + "\n".join(output)).encode("utf-8")),
        "omitted_unique": omitted,
        "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }

def python_outline(source: str, path: str) -> str:
    """Generate a cheap AST navigation map. Does NOT claim to describe behavior."""
    tree = ast.parse(source, filename=path)
    lines = [f"FILE {path}"]
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.posonlyargs + node.args.args]
            lines.append(f"  {node.lineno}-{node.end_lineno} def {node.name}({', '.join(args)})")
        elif isinstance(node, ast.ClassDef):
            lines.append(f"  {node.lineno}-{node.end_lineno} class {node.name}")
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lines.append(f"    {method.lineno}-{method.end_lineno} def {method.name}")
    return "\n".join(lines)

def compact_source_evidence(report: dict, *, max_chars: int = 16000) -> dict:
    """Preserve complete hash-verified source snippets, omit repetitive metadata.

    Retrieval is performed upstream by PIE. This is a presentation adapter.
    A stale/unindexed state is rejected; PARTIAL is reported, never hidden.
    """
    if max_chars < 500:
        raise ValueError("max_chars must be at least 500")
    state = report.get("context_state", "UNKNOWN")
    if state not in ("CURRENT", "PARTIAL"):
        raise ValueError(f"Source evidence not usable: {state}")
    snippets = report.get("evidence", report.get("source_ranges", []))
    blocks, seen, omitted = [], set(), []
    used = 0
    for item in snippets:
        path = str(item["path"])
        start, end = int(item["start_line"]), int(item["end_line"])
        content = str(item["content"])
        fingerprint = (path, start, end, hashlib.sha256(content.encode()).hexdigest())
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        block = f"{path}:{start}-{end} ({item.get('symbol', '?')})\n{content}"
        if len(block) + used + 150 > max_chars:
            omitted.append({"path": path, "line": start, "reason": "budget"})
            continue
        blocks.append(block)
        used += len(block) + 2
    new_state = "PARTIAL" if state == "PARTIAL" or omitted else "CURRENT"
    header = f"PIE_SOURCE_EVIDENCE state={new_state} snippets={len(blocks)} omitted={len(omitted)}"
    content = header + "\n\n" + "\n\n".join(blocks)
    return {
        "state": new_state,
        "content": content,
        "omitted": omitted,
        "source_chars": sum(len(str(x["content"])) for x in snippets),
        "context_chars": len(content),
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
    }
