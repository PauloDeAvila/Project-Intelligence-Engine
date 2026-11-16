"""Persistent, project-scoped task checkpoints for resuming agent work.

Stage 1 deliberately records explicit facts only: no automatic agent capture,
no semantic retrieval, and no claim that model context is persisted.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pie.storage.locations import workspace_file, workspace_storage
from pie.storage.database import connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS pie_tasks (
  task_id TEXT PRIMARY KEY,
  objective TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('in_progress','blocked','completed')),
  created_utc TEXT NOT NULL,
  updated_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pie_task_events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL REFERENCES pie_tasks(task_id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK(kind IN ('action','decision','result','checkpoint','note')),
  text TEXT NOT NULL,
  reference TEXT,
  created_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pie_tasks_recent ON pie_tasks(updated_utc DESC,task_id);
CREATE INDEX IF NOT EXISTS idx_pie_events_task ON pie_task_events(task_id,seq DESC);
"""
KINDS = frozenset(("action", "decision", "result", "checkpoint", "note"))
STATUSES = frozenset(("in_progress", "blocked", "completed"))


def _text(value: str, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\x00" in value:
        raise ValueError(f"{name} must be nonempty and <= {maximum} characters without NUL")
    return value.strip()


def _open(root: Path) -> sqlite3.Connection:
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Project root must be a directory")
    storage_dir = workspace_storage(root)
    if storage_dir.is_symlink() or storage_dir.resolve() != workspace_storage(root).resolve():
        raise ValueError("Project storage must not redirect outside the root")
    database = storage_dir / "index.sqlite3"
    if not database.is_file() or database.is_symlink():
        raise ValueError("Run pie init/index first")
    connection = connect(database)
    try:
        connection.executescript(SCHEMA)
    except Exception:
        connection.close()
        raise
    return connection


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def start_task(root: Path, objective: str) -> dict:
    """Start a task; UUID is opaque and generated locally."""
    objective = _text(objective, "objective", 2048)
    task_id = str(uuid.uuid4())
    timestamp = _utc()
    with closing(_open(root)) as db:
        with db:
            db.execute("INSERT INTO pie_tasks VALUES (?,?,?,?,?)",
                       (task_id, objective, "in_progress", timestamp, timestamp))
    return {"task_id": task_id, "objective": objective,
            "status": "in_progress", "created_utc": timestamp}


def record_task(root: Path, task_id: str, kind: str, text: str,
                reference: str | None = None, status: str | None = None) -> dict:
    """Atomically append evidence/decision and optionally transition task state."""
    task_id = _text(task_id, "task_id", 64)
    kind = _text(kind, "kind", 32)
    text = _text(text, "text", 4096)
    if kind not in KINDS:
        raise ValueError("Unsupported event kind")
    if reference is not None:
        reference = _text(reference, "reference", 1024)
    if status is not None and status not in STATUSES:
        raise ValueError("Unsupported task status")
    with closing(_open(root)) as db:
        with db:
            # Serialize status validation and insertion across concurrent MCP clients.
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT status FROM pie_tasks WHERE task_id=?",
                                 (task_id,)).fetchone()
            if current is None:
                raise ValueError("Unknown task_id")
            if current["status"] == "completed":
                raise ValueError("Completed task is immutable")
            now = _utc()
            new_status = status or current["status"]
            cursor = db.execute(
                "INSERT INTO pie_task_events(task_id,kind,text,reference,created_utc) "
                "VALUES (?,?,?,?,?)", (task_id, kind, text, reference, now))
            db.execute("UPDATE pie_tasks SET status=?,updated_utc=? WHERE task_id=?",
                       (new_status, now, task_id))
            return {"task_id": task_id, "event_id": cursor.lastrowid,
                    "status": new_status, "kind": kind, "updated_utc": now}


def resume_task(root: Path, task_id: str | None = None, limit: int = 30) -> dict:
    """Read the latest unfinished task or an explicit task with bounded history."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    if task_id is not None:
        task_id = _text(task_id, "task_id", 64)
    with closing(_open(root)) as db:
        if task_id is None:
            task = db.execute(
                "SELECT * FROM pie_tasks WHERE status IN ('in_progress','blocked') "
                "ORDER BY updated_utc DESC, task_id DESC LIMIT 1").fetchone()
        else:
            task = db.execute("SELECT * FROM pie_tasks WHERE task_id=?",
                              (task_id,)).fetchone()
        if task is None:
            return {"state": "NOT_FOUND", "task": None, "events": [],
                    "omitted_events": 0}
        count = db.execute("SELECT COUNT(*) FROM pie_task_events WHERE task_id=?",
                           (task["task_id"],)).fetchone()[0]
        events = db.execute(
            "SELECT seq,kind,text,reference,created_utc FROM "
            "(SELECT seq,kind,text,reference,created_utc FROM pie_task_events "
            "WHERE task_id=? ORDER BY seq DESC LIMIT ?) ORDER BY seq ASC",
            (task["task_id"], limit)).fetchall()
        return {"state": "FOUND",
                "task": dict(task), "events": [dict(event) for event in events],
                "omitted_events": count - len(events)}
