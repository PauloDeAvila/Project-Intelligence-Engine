"""Local baseline and savings counters; never claim character ratios are tokens."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import sqlite3
from pathlib import Path

from pie.storage.locations import workspace_file
from pie.certification.task_telemetry import record_task

SCHEMA = """
CREATE TABLE IF NOT EXISTS pie_gateway_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_utc TEXT NOT NULL,
    surface TEXT NOT NULL,
    tool TEXT NOT NULL,
    state TEXT NOT NULL,
    source_chars INTEGER NOT NULL,
    returned_chars INTEGER NOT NULL,
    elapsed_ms REAL NOT NULL,
    output_id TEXT,
    exit_code INTEGER
);
CREATE INDEX IF NOT EXISTS pie_gateway_metrics_created
ON pie_gateway_metrics(created_utc);
"""


def record(root: Path, *, surface: str, tool: str, state: str,
           source_chars: int, returned_chars: int, elapsed_ms: float,
           output_id: str | None = None, exit_code: int | None = None) -> None:
    if surface not in ("terminal", "mcp") or not isinstance(tool, str):
        raise ValueError("Invalid tool surface or name")
    if not all(type(n) is int and n >= 0 for n in (source_chars, returned_chars)):
        raise ValueError("Invalid character counts")
    database=workspace_file(root)
    database.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(database, timeout=5)) as db:
        with db:
            db.executescript(SCHEMA)
            db.execute(
                "INSERT INTO pie_gateway_metrics "
                "(created_utc,surface,tool,state,source_chars,returned_chars,"
                "elapsed_ms,output_id,exit_code) VALUES(?,?,?,?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(), surface, tool[:120],
                 state[:60], source_chars, returned_chars, elapsed_ms, output_id, exit_code))
            db.execute("DELETE FROM pie_gateway_metrics WHERE id NOT IN "
                       "(SELECT id FROM pie_gateway_metrics ORDER BY id DESC LIMIT 1000)")
    # Keep the legacy counter independent from the task ledger.
    # The task ledger is best-effort and must not break MCP execution.
    try:
        record_task(root, surface=surface, tool=tool, state=state,
                    source_chars=source_chars, returned_chars=returned_chars,
                    elapsed_ms=elapsed_ms)
    except (OSError, ValueError, sqlite3.Error):
        pass


def report(root: Path) -> dict:
    database = workspace_file(root)
    if not database.is_file():
        return {"events": 0, "measurement": "characters_not_model_tokens"}
    with closing(sqlite3.connect(database, timeout=5)) as db:
        db.executescript(SCHEMA)
        rows = db.execute(
            "SELECT surface, state, COUNT(*), SUM(source_chars), "
            "SUM(returned_chars) FROM pie_gateway_metrics "
            "GROUP BY surface,state ORDER BY surface,state").fetchall()
    values = [
        {"surface": x[0], "state": x[1], "calls": x[2],
         "source_chars": x[3], "returned_chars": x[4],
         "saved_chars": x[3] - x[4]}
        for x in rows
    ]
    return {"events": sum(x["calls"] for x in values), "groups": values,
            "measurement": "characters_not_model_tokens",
            "provider_prompt_tokens": None, "provider_completion_tokens": None,
            "provider_evidence_available": False}
