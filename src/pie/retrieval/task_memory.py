"""Persistent, project-scoped task checkpoints for resuming agent work.

Stage 1 deliberately records explicit facts only: no automatic agent capture,
no semantic retrieval, and no claim that model context is persisted.
"""
from __future__ import annotations

import hashlib
import json
import math
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
CREATE TABLE IF NOT EXISTS pie_task_checkpoints (
  task_id TEXT NOT NULL REFERENCES pie_tasks(task_id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  schema_version INTEGER NOT NULL,
  state_json TEXT NOT NULL,
  state_hash TEXT NOT NULL,
  provenance_json TEXT,
  provenance_hash TEXT,
  created_utc TEXT NOT NULL,
  PRIMARY KEY (task_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_pie_checkpoints_latest
  ON pie_task_checkpoints(task_id, seq DESC);
"""
KINDS = frozenset(("action", "decision", "result", "checkpoint", "note"))
STATUSES = frozenset(("in_progress", "blocked", "completed"))
CHECKPOINT_SCHEMA_VERSION = 1
CHECKPOINT_STATE_MAX_BYTES = 16 * 1024
CHECKPOINT_PROVENANCE_MAX_BYTES = 4 * 1024
_CHECKPOINT_MAX_DEPTH = 6
_CHECKPOINT_MAX_OBJECT_KEYS = 64
_CHECKPOINT_MAX_SEQUENCE_ITEMS = 128
_CHECKPOINT_MAX_STRING = 512
_SENSITIVE_FRAGMENTS = (
    "prompt", "answer", "cookie", "password", "secret", "credential", "token"
)


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


def _canonical_json(value: object) -> str:
    """Serialize JSON without whitespace or non-finite numeric values."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_checkpoint_node(value: object, path: str, depth: int) -> None:
    if depth > _CHECKPOINT_MAX_DEPTH:
        raise ValueError(f"Checkpoint exceeds maximum depth at {path}")
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Checkpoint contains a non-finite number at {path}")
        return
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError(f"Checkpoint contains NUL at {path}")
        if len(value) > _CHECKPOINT_MAX_STRING:
            raise ValueError(f"Checkpoint string exceeds {_CHECKPOINT_MAX_STRING} characters")
        if any(fragment in value.lower() for fragment in _SENSITIVE_FRAGMENTS):
            raise ValueError(f"Checkpoint contains a sensitive fragment at {path}")
        return
    if isinstance(value, dict):
        if len(value) > _CHECKPOINT_MAX_OBJECT_KEYS:
            raise ValueError(f"Checkpoint object exceeds {_CHECKPOINT_MAX_OBJECT_KEYS} keys")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"Checkpoint mapping keys must be strings at {path}")
            if any(fragment in key.lower() for fragment in _SENSITIVE_FRAGMENTS):
                raise ValueError(f"Checkpoint contains a sensitive key at {path}.{key}")
            _validate_checkpoint_node(item, f"{path}.{key}", depth + 1)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > _CHECKPOINT_MAX_SEQUENCE_ITEMS:
            raise ValueError(
                f"Checkpoint sequence exceeds {_CHECKPOINT_MAX_SEQUENCE_ITEMS} items"
            )
        for index, item in enumerate(value):
            _validate_checkpoint_node(item, f"{path}[{index}]", depth + 1)
        return
    raise ValueError(f"Unsupported checkpoint value type: {type(value).__name__}")


def _validate_checkpoint_payload(
    value: object, name: str, maximum_bytes: int, *, scalars_only: bool = False
) -> tuple[object, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    if scalars_only:
        if len(value) > _CHECKPOINT_MAX_OBJECT_KEYS:
            raise ValueError(f"{name} exceeds {_CHECKPOINT_MAX_OBJECT_KEYS} keys")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{name} mapping keys must be strings")
            if any(fragment in key.lower() for fragment in _SENSITIVE_FRAGMENTS):
                raise ValueError(f"{name} contains a sensitive key at $.{key}")
            if isinstance(item, (dict, list, tuple)):
                raise ValueError(f"{name} values must be scalar metadata")
            _validate_checkpoint_node(item, f"$.{key}", 1)
    else:
        _validate_checkpoint_node(value, "$", 0)
    try:
        canonical = _canonical_json(value)
        reparsed = json.loads(canonical)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"{name} is not canonical JSON: {error}") from error
    if _canonical_json(reparsed) != canonical:
        raise ValueError(f"{name} is not canonically stable")
    if len(canonical.encode("utf-8")) > maximum_bytes:
        raise ValueError(f"{name} exceeds {maximum_bytes} canonical UTF-8 bytes")
    return reparsed, canonical


def _verify_checkpoint_payload(
    encoded: str,
    expected_hash: str,
    name: str,
    maximum_bytes: int,
    *,
    scalars_only: bool = False,
) -> object:
    if not isinstance(encoded, str) or "\x00" in encoded:
        raise ValueError(f"Invalid {name} encoding")
    if _sha256(encoded) != expected_hash:
        raise ValueError(f"Checkpoint {name} hash mismatch")
    try:
        value = json.loads(encoded)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"Checkpoint {name} is not valid JSON") from error
    validated, canonical = _validate_checkpoint_payload(
        value, name, maximum_bytes, scalars_only=scalars_only
    )
    if canonical != encoded or _sha256(canonical) != expected_hash:
        raise ValueError(f"Checkpoint {name} canonical verification failed")
    return validated


def checkpoint_task(
    root: Path, task_id: str, state: object, provenance: object | None = None
) -> dict:
    """Persist bounded, hash-verified state without task text or objectives."""
    task_id = _text(task_id, "task_id", 64)
    _, state_json = _validate_checkpoint_payload(
        state, "state", CHECKPOINT_STATE_MAX_BYTES
    )
    state_hash = _sha256(state_json)
    if provenance is None:
        provenance_json = None
        provenance_hash = None
    else:
        _, provenance_json = _validate_checkpoint_payload(
            provenance,
            "provenance",
            CHECKPOINT_PROVENANCE_MAX_BYTES,
            scalars_only=True,
        )
        provenance_hash = _sha256(provenance_json)
    with closing(_open(root)) as db:
        with db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT status FROM pie_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if current is None:
                raise ValueError("Unknown task_id")
            if current["status"] == "completed":
                raise ValueError("Completed task is immutable")
            seq = db.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM pie_task_checkpoints "
                "WHERE task_id=?", (task_id,)
            ).fetchone()[0]
            now = _utc()
            db.execute(
                "INSERT INTO pie_task_checkpoints "
                "(task_id,seq,schema_version,state_json,state_hash,"
                "provenance_json,provenance_hash,created_utc) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    task_id,
                    seq,
                    CHECKPOINT_SCHEMA_VERSION,
                    state_json,
                    state_hash,
                    provenance_json,
                    provenance_hash,
                    now,
                ),
            )
            db.execute(
                "UPDATE pie_tasks SET updated_utc=? WHERE task_id=?", (now, task_id)
            )
            return {
                "task_id": task_id,
                "seq": seq,
                "schema_version": CHECKPOINT_SCHEMA_VERSION,
                "state_hash": state_hash,
                "provenance_hash": provenance_hash,
                "created_utc": now,
            }


def restore_state(root: Path, task_id: str, seq: int | None = None) -> dict:
    """Restore latest or explicit checkpoint after full integrity validation."""
    task_id = _text(task_id, "task_id", 64)
    if seq is not None and (type(seq) is not int or seq < 1):
        raise ValueError("seq must be a positive integer when provided")
    with closing(_open(root)) as db:
        if seq is None:
            checkpoint = db.execute(
                "SELECT * FROM pie_task_checkpoints WHERE task_id=? "
                "ORDER BY seq DESC LIMIT 1", (task_id,)
            ).fetchone()
        else:
            checkpoint = db.execute(
                "SELECT * FROM pie_task_checkpoints WHERE task_id=? AND seq=?",
                (task_id, seq),
            ).fetchone()
        if checkpoint is None:
            return {"state": "NOT_FOUND", "task_id": task_id, "seq": None}
        if checkpoint["schema_version"] != CHECKPOINT_SCHEMA_VERSION:
            raise ValueError("Checkpoint schema version mismatch")
        state = _verify_checkpoint_payload(
            checkpoint["state_json"],
            checkpoint["state_hash"],
            "state",
            CHECKPOINT_STATE_MAX_BYTES,
        )
        provenance_json = checkpoint["provenance_json"]
        provenance_hash = checkpoint["provenance_hash"]
        if provenance_json is None:
            if provenance_hash is not None:
                raise ValueError("Checkpoint provenance hash mismatch")
            provenance = None
        else:
            if provenance_hash is None:
                raise ValueError("Checkpoint provenance hash is missing")
            provenance = _verify_checkpoint_payload(
                provenance_json,
                provenance_hash,
                "provenance",
                CHECKPOINT_PROVENANCE_MAX_BYTES,
                scalars_only=True,
            )
        return {
            "state": "FOUND",
            "task_id": task_id,
            "seq": checkpoint["seq"],
            "schema_version": checkpoint["schema_version"],
            "state_value": state,
            "state_hash": checkpoint["state_hash"],
            "provenance": provenance,
            "provenance_hash": provenance_hash,
            "created_utc": checkpoint["created_utc"],
        }


def checkpoint_agent_state(
    root: Path,
    task_id: str,
    agent_id: str,
    state: object,
    provenance: object | None = None,
) -> dict:
    """Persist explicit agent state using the checkpoint security rules."""
    agent_id = _text(agent_id, "agent_id", 64)
    if provenance is None:
        merged = {"agent_id": agent_id}
    else:
        if not isinstance(provenance, dict):
            raise ValueError("provenance must be a dict or None")
        supplied = provenance.get("agent_id")
        if supplied is not None and supplied != agent_id:
            raise ValueError("provenance agent_id conflicts with agent_id argument")
        merged = dict(provenance)
        merged["agent_id"] = agent_id
    return checkpoint_task(root, task_id, state, merged)


def list_agent_checkpoints(
    root: Path,
    task_id: str,
    agent_id: str | None = None,
    limit: int = 100,
) -> dict:
    """List hash-backed checkpoint metadata without returning state or events."""
    task_id = _text(task_id, "task_id", 64)
    if agent_id is not None:
        agent_id = _text(agent_id, "agent_id", 64)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    checkpoints: list[dict] = []
    with closing(_open(root)) as db:
        rows = db.execute(
            "SELECT task_id,seq,schema_version,state_hash,provenance_json,"
            "provenance_hash,created_utc FROM pie_task_checkpoints "
            "WHERE task_id=? ORDER BY seq DESC LIMIT ?",
            (task_id, limit),
        ).fetchall()
        for row in rows:
            if row["schema_version"] != CHECKPOINT_SCHEMA_VERSION:
                raise ValueError("Checkpoint schema version mismatch")
            state_hash = row["state_hash"]
            if (
                not isinstance(state_hash, str)
                or len(state_hash) != 64
                or any(char not in "0123456789abcdef" for char in state_hash)
            ):
                raise ValueError("Checkpoint state hash is invalid")
            provenance_json = row["provenance_json"]
            provenance_hash = row["provenance_hash"]
            if provenance_json is None:
                if provenance_hash is not None:
                    raise ValueError("Checkpoint provenance hash mismatch")
                provenance = None
            else:
                if provenance_hash is None:
                    raise ValueError("Checkpoint provenance hash is missing")
                provenance = _verify_checkpoint_payload(
                    provenance_json,
                    provenance_hash,
                    "provenance",
                    CHECKPOINT_PROVENANCE_MAX_BYTES,
                    scalars_only=True,
                )
            if agent_id is not None and (
                not isinstance(provenance, dict) or provenance.get("agent_id") != agent_id
            ):
                continue
            checkpoints.append(
                {
                    "task_id": row["task_id"],
                    "seq": row["seq"],
                    "schema_version": row["schema_version"],
                    "state_hash": state_hash,
                    "provenance": provenance,
                    "provenance_hash": provenance_hash,
                    "created_utc": row["created_utc"],
                }
            )
    if not checkpoints:
        return {
            "state": "NOT_FOUND",
            "task_id": task_id,
            "agent_id": agent_id,
            "checkpoints": [],
        }
    return {
        "state": "FOUND",
        "task_id": task_id,
        "agent_id": agent_id,
        "checkpoints": checkpoints,
    }


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
    for field_name, value in (("text", text), ("reference", reference)):
        if value is not None:
            for fragment in _SENSITIVE_FRAGMENTS:
                if fragment in value.lower():
                    raise ValueError(
                        f"Task event contains a sensitive fragment in {field_name}"
                    )
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
