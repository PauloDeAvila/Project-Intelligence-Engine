"""Conservative deterministic output reduction shared by terminal and MCP.

Never invent tool success: failure status, exit code, native JSON-RPC errors and
structured content must survive. Only opt-in text-only observations are reduced.
Sanitized originals can be recovered using existing PIE output infrastructure.
"""
from __future__ import annotations

from contextlib import closing

import json
import time
from pathlib import Path
from typing import Any

from pie.gateway.metrics import record
from pie.storage.database import connect
from pie.storage.locations import workspace_file
from pie.retrieval.output_pipeline import compact_output, _redact

MAX_CAPTURE_CHARS = 500_000
DEFAULT_MAX_CHARS = 2500


def _is_structured_text(value: str) -> bool:
    stripped = value.lstrip()
    if not stripped.startswith(("{", "[")):
        return False
    try:
        return isinstance(json.loads(stripped), (list, dict))
    except (ValueError, TypeError):
        return False


def reduce_text(root: Path, source: str, *, surface: str, tool: str,
                max_chars: int = DEFAULT_MAX_CHARS,
                kind: str = "terminal", exit_code: int | None = None,
                safe_text: bool = True) -> dict[str, Any]:
    """Store a recoverable sanitized original, then return a bounded view.

    safe_text=False bypasses lossy compaction; the client sees the actual text.
    Redaction is best-effort, not comprehensive DLP. Unknown large protocols
    must be routed using separate policies rather than silently truncated.
    """
    if type(max_chars) is not int or not 800 <= max_chars <= 64000:
        raise ValueError("max_chars must be 800..64000")
    if not isinstance(source, str):
        raise ValueError("Expected UTF-8 decoded text")
    started = time.perf_counter()
    # Phase-1 gateways must work before a workspace has source-indexed Python.
    # This creates the central SQLite schema, but does not pretend to have
    # indexed the workspace. Global PIE indexes on its own bootstrap.
    database=workspace_file(root)
    if not database.is_file():
        with closing(connect(database)):
            pass
    if not safe_text:
        result = {"state": "PASSTHROUGH_UNSAFE_TO_COMPACT", "text": source,
                  "source_chars": len(source), "returned_chars": len(source),
                  "output_id": None, "exit_code": exit_code,
                  "recovery": "not_applicable"}
    elif len(source) > MAX_CAPTURE_CHARS:
        # Refuse to claim complete recovery of content beyond storage limit.
        result = {"state": "CAPTURE_LIMIT_EXCEEDED", "text": None,
                  "source_chars": len(source), "returned_chars": 0,
                  "output_id": None, "exit_code": exit_code,
                  "recovery": "unavailable_for_oversized_output"}
    else:
        compact = compact_output(root, source, kind=kind, max_chars=max_chars,
                                 exit_code=exit_code)
        clean = _redact(source)
        # Small responses are returned in their original sequence.
        if len(clean) <= max_chars:
            result = {"state": "COMPLETE_SANITIZED", "text": clean,
                      "source_chars": len(clean), "returned_chars": len(clean),
                      "output_id": compact["output_id"], "exit_code": exit_code,
                      "recovery": "pie_gateway_output_get"}
        else:
            result = {"state": "PARTIAL", "text": compact["text"],
                      "source_chars": len(clean),
                      "returned_chars": len(compact["text"]),
                      "output_id": compact["output_id"], "exit_code": exit_code,
                      "recovery": "pie_gateway_output_get",
                      "omitted_unique_lines": compact["omitted_unique_lines"]}
    record(root, surface=surface, tool=tool, state=result["state"],
           source_chars=result["source_chars"],
           returned_chars=result["returned_chars"],
           elapsed_ms=(time.perf_counter()-started)*1000,
           output_id=result["output_id"], exit_code=exit_code)
    return result


def mcp_compactable(response: dict, tool_name: str, opt_in: frozenset[str],
                    has_output_schema: bool = False) -> bool:
    """Only text-only, successful, explicitly opted-in tool results."""
    if tool_name not in opt_in or has_output_schema or "error" in response:
        return False
    result = response.get("result")
    if not isinstance(result, dict) or result.get("isError") or "structuredContent" in result:
        return False
    contents = result.get("content")
    if not isinstance(contents, list) or len(contents) != 1:
        return False
    item = contents[0]
    if not isinstance(item, dict) or item.get("type") != "text" or set(item)-{"type","text"}:
        return False
    value = item.get("text")
    if not isinstance(value, str) or _is_structured_text(value):
        return False
    # Never silence failures exposed as plain text in successful results.
    lower = value.lower()
    if lower.startswith(("error:", "traceback (most recent call last)", "permission denied")):
        return False
    return True
