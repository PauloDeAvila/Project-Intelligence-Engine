"""Local baseline and savings counters; never claim character ratios are tokens."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import sqlite3
import os
import re
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
    exit_code INTEGER,
    source_event_id TEXT
);
CREATE INDEX IF NOT EXISTS pie_gateway_metrics_created
ON pie_gateway_metrics(created_utc);
"""
_EVENT_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


def _connect(database: Path) -> sqlite3.Connection:
    db = sqlite3.connect(database, timeout=5)
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    columns = {row[1] for row in db.execute("PRAGMA table_info(pie_gateway_metrics)")}
    if "source_event_id" not in columns:
        db.execute("ALTER TABLE pie_gateway_metrics ADD COLUMN source_event_id TEXT")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS pie_gateway_metrics_by_event "
        "ON pie_gateway_metrics(source_event_id) WHERE source_event_id IS NOT NULL"
    )
    return db


def record(root: Path, *, surface: str, tool: str, state: str,
           source_chars: int, returned_chars: int, elapsed_ms: float,
           output_id: str | None = None, exit_code: int | None = None,
           source_event_id: str | None = None) -> None:
    if surface not in ("terminal", "mcp") or not isinstance(tool, str):
        raise ValueError("Invalid tool surface or name")
    if not all(type(n) is int and n >= 0 for n in (source_chars, returned_chars)):
        raise ValueError("Invalid character counts")
    if source_event_id is not None and not _EVENT_ID.fullmatch(source_event_id):
        raise ValueError("Invalid source event identifier")
    database=workspace_file(root)
    database.parent.mkdir(parents=True,exist_ok=True)
    with closing(_connect(database)) as db:
        with db:
            db.executescript(SCHEMA)
            cursor = db.execute(
                "INSERT OR IGNORE INTO pie_gateway_metrics "
                "(created_utc,surface,tool,state,source_chars,returned_chars,"
                "elapsed_ms,output_id,exit_code,source_event_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(), surface, tool[:120],
                 state[:60], source_chars, returned_chars, elapsed_ms, output_id,
                 exit_code, source_event_id))
            if cursor.rowcount == 0:
                return
            db.execute("DELETE FROM pie_gateway_metrics WHERE id NOT IN "
                       "(SELECT id FROM pie_gateway_metrics ORDER BY id DESC LIMIT 1000)")
    # Keep the legacy counter independent from the task ledger.
    # The task ledger is best-effort and must not break MCP execution.
    try:
        record_task(root, surface=surface, tool=tool, state=state,
                    source_chars=source_chars, returned_chars=returned_chars,
                    elapsed_ms=elapsed_ms,
                    source_event_id=source_event_id,
                    condition=os.environ.get("PIE_CONDITION", "observed"))
    except (OSError, ValueError, sqlite3.Error):
        pass


def report(root: Path) -> dict:
    database = workspace_file(root)
    if not database.is_file():
        return {"events": 0, "measurement": "characters_not_model_tokens"}
    with closing(_connect(database)) as db:
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
