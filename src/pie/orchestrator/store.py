from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import time
import uuid
from typing import Any

from .models import TRANSITIONS, Task, TaskStatus


class TaskStore:
    """Separate transactional database; never use the PIE index database here."""
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY, source TEXT NOT NULL, project_id TEXT NOT NULL,
          task_type TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
          priority INTEGER NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
          timeout_seconds INTEGER NOT NULL, token_limit INTEGER, cost_limit REAL,
          session_id TEXT, result_json TEXT, metrics_json TEXT, error TEXT
        );
        CREATE TABLE IF NOT EXISTS idempotency_keys (
          source TEXT NOT NULL, key TEXT NOT NULL, task_id TEXT NOT NULL REFERENCES tasks(id),
          PRIMARY KEY(source, key)
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL REFERENCES tasks(id),
          created_at INTEGER NOT NULL, kind TEXT NOT NULL, data_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS artifacts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL REFERENCES tasks(id),
          name TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, created_at INTEGER NOT NULL
        );
        """)

    def close(self) -> None: self.connection.close()
    def _now(self) -> int: return int(time.time())
    def _event(self, task_id: str, kind: str, data: dict[str, Any]) -> None:
        self.connection.execute("INSERT INTO events(task_id,created_at,kind,data_json) VALUES(?,?,?,?)", (task_id, self._now(), kind, json.dumps(data, sort_keys=True)))
    def _task(self, row: sqlite3.Row) -> Task:
        return Task(row["id"], row["source"], row["project_id"], row["task_type"], row["model"], TaskStatus(row["status"]), row["priority"], row["created_at"], row["updated_at"], row["timeout_seconds"], row["token_limit"], row["cost_limit"], row["session_id"], json.loads(row["result_json"]) if row["result_json"] else None, json.loads(row["metrics_json"]) if row["metrics_json"] else None, row["error"])
    def get(self, task_id: str) -> Task | None:
        row = self.connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._task(row) if row else None
    def create(self, *, source: str, key: str, project_id: str, task_type: str, model: str, priority: int = 0, timeout_seconds: int = 600, token_limit: int | None = None, cost_limit: float | None = None) -> tuple[Task, bool]:
        with self.connection:
            existing = self.connection.execute("SELECT task_id FROM idempotency_keys WHERE source=? AND key=?", (source, key)).fetchone()
            if existing: return self.get(existing["task_id"]), False  # type: ignore[return-value]
            now, task_id = self._now(), str(uuid.uuid4())
            self.connection.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (task_id, source, project_id, task_type, model, TaskStatus.PENDING, priority, now, now, timeout_seconds, token_limit, cost_limit, None, None, None, None))
            self.connection.execute("INSERT INTO idempotency_keys VALUES(?,?,?)", (source, key, task_id))
            self._event(task_id, "created", {"source": source})
        return self.get(task_id), True  # type: ignore[return-value]
    def transition(self, task_id: str, target: TaskStatus, *, data: dict[str, Any] | None = None, error: str | None = None) -> Task:
        with self.connection:
            task = self.get(task_id)
            if task is None: raise KeyError(task_id)
            if target != task.status and target not in TRANSITIONS.get(task.status, set()): raise ValueError(f"Illegal transition {task.status}->{target}")
            self.connection.execute("UPDATE tasks SET status=?,updated_at=?,error=COALESCE(?,error) WHERE id=?", (target, self._now(), error, task_id))
            self._event(task_id, "state", {"from": task.status, "to": target, **(data or {})})
        return self.get(task_id)  # type: ignore[return-value]
    def recover_interrupted(self) -> int:
        rows = self.connection.execute("SELECT id FROM tasks WHERE status=?", (TaskStatus.RUNNING,)).fetchall()
        for row in rows: self.transition(row["id"], TaskStatus.BLOCKED, data={"reason": "interrupted_restart"}, error="interrupted_restart")
        return len(rows)
    def events(self, task_id: str) -> list[dict[str, Any]]:
        return [{"id": r["id"], "created_at": r["created_at"], "kind": r["kind"], "data": json.loads(r["data_json"])} for r in self.connection.execute("SELECT * FROM events WHERE task_id=? ORDER BY id", (task_id,))]

    def bind_session(self, task_id: str, session_id: str) -> None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError('Invalid OpenCode session ID')
        with self.connection:
            task = self.get(task_id)
            if task is None or task.status != TaskStatus.RUNNING:
                raise ValueError('Cannot bind unless RUNNING')
            if task.session_id is not None:
                if task.session_id == session_id:
                    return
                raise ValueError('Session already bound')
            self.connection.execute('UPDATE tasks SET session_id=?,updated_at=? WHERE id=? AND session_id IS NULL', (session_id,self._now(),task_id))
            self._event(task_id,'session_bound', {'session_id':session_id})

    def record_execution(self, task_id: str, *, session_id: str | None, result: dict[str, Any] | None, metrics: dict[str, Any] | None) -> None:
        with self.connection:
            task=self.get(task_id)
            if task is None or task.status != TaskStatus.RUNNING or task.session_id != session_id:
                raise ValueError("Invalid execution state or session binding")
            self.connection.execute("UPDATE tasks SET result_json=?,metrics_json=?,updated_at=? WHERE id=?", (json.dumps(result) if result is not None else None, json.dumps(metrics) if metrics is not None else None, self._now(), task_id))
            self._event(task_id, "execution_recorded", {"session_id": session_id, "metrics_available": metrics is not None})
