"""Minimal pre-import lifecycle logger for the stdio gateway."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


def _path() -> Path | None:
    value = os.environ.get("PIE_MCP_BOOTSTRAP_PATH") or os.environ.get("PIE_MCP_DIAGNOSTICS_PATH")
    return Path(value).expanduser() if value else None


def event(name: str, **fields: Any) -> None:
    """Best-effort JSONL logging; never writes to the MCP protocol stream."""
    path = _path()
    if path is None:
        return
    row = {"ts_utc": datetime.now(timezone.utc).isoformat(), "event": name}
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
