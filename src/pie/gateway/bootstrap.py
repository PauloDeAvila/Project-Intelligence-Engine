"""Minimal pre-import lifecycle logger for the stdio gateway."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any


def _path() -> Path | None:
    value = os.environ.get("PIE_MCP_BOOTSTRAP_PATH") or os.environ.get("PIE_MCP_DIAGNOSTICS_PATH")
    if value:
        return Path(value).expanduser()
    # Codex may not inherit arbitrary parent environment variables. The
    # workspace argument is part of the persisted MCP command, so it is a safe
    # deterministic fallback for sanitized lifecycle events.
    try:
        index = sys.argv.index("--workspace")
        workspace = Path(sys.argv[index + 1]).expanduser()
        if workspace:
            return workspace / ".pie-live-store" / "mcp-lifecycle.jsonl"
    except (ValueError, IndexError):
        pass
    return None


def path() -> Path | None:
    return _path()


def event(name: str, **fields: Any) -> None:
    """Best-effort JSONL logging; never writes to the MCP protocol stream."""
    path = _path()
    if path is None:
        return
    row = {"ts_utc": datetime.now(timezone.utc).isoformat(), "event": name, "pid": os.getpid()}
    for key, value in fields.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            row[key] = value
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
            stream.flush()
    except OSError:
        return
