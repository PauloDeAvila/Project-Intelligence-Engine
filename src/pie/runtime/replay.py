"""Local deterministic idempotency journal for side-effecting operations.

Only operation and result hashes are persisted. A started operation is never
executed automatically after a restart because its external side effect may
have happened before the process stopped.
"""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
from datetime import datetime, timezone

_OPERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_PAYLOAD_BYTES = 64 * 1024
_MAX_METADATA_BYTES = 16 * 1024
_SENSITIVE_METADATA_FRAGMENTS = (
    "prompt", "answer", "cookie", "password", "secret", "credential", "token"
)
_STARTED = "started"
_COMPLETED = "completed"
_FAILED = "failed"


class ReplayConflict(ValueError):
    """The same operation ID was used with a different payload."""


def _canonical_json(value: object) -> str:
    def validate(node: object) -> None:
        if isinstance(node, float):
            if not math.isfinite(node):
                raise ValueError("payload contains a non-finite number")
        elif isinstance(node, dict):
            for key, item in node.items():
                if not isinstance(key, str):
                    raise TypeError("payload object keys must be strings")
                validate(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                validate(item)

    validate(value)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if "\x00" in encoded:
        raise ValueError("payload contains NUL")
    if len(encoded.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raise ValueError(f"payload exceeds {_MAX_PAYLOAD_BYTES} canonical UTF-8 bytes")
    return encoded


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_metadata(value: object) -> str:
    def validate(node: object, depth: int = 0) -> None:
        if depth > 6:
            raise ValueError("metadata exceeds maximum depth")
        if isinstance(node, dict):
            if len(node) > 64:
                raise ValueError("metadata object exceeds key limit")
            for key, item in node.items():
                if not isinstance(key, str):
                    raise TypeError("metadata object keys must be strings")
                if any(fragment in key.lower() for fragment in _SENSITIVE_METADATA_FRAGMENTS):
                    raise ValueError("metadata contains a sensitive key")
                validate(item, depth + 1)
        elif isinstance(node, (list, tuple)):
            if len(node) > 128:
                raise ValueError("metadata sequence exceeds item limit")
            for item in node:
                validate(item, depth + 1)
        elif isinstance(node, str) and ("\x00" in node or len(node) > 512):
            raise ValueError("metadata string is outside the safe bound")
        elif isinstance(node, float) and not math.isfinite(node):
            raise ValueError("metadata contains a non-finite number")

    validate(value)
    encoded = _canonical_json(value)
    if len(encoded.encode("utf-8")) > _MAX_METADATA_BYTES:
        raise ValueError(f"metadata exceeds {_MAX_METADATA_BYTES} canonical UTF-8 bytes")
    return encoded


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class ExecutionJournal:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self._path, timeout=5, isolation_level=None, check_same_thread=False
        )
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._lock = threading.RLock()
        self._closed = False
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS execution_journal (
                        operation_id TEXT PRIMARY KEY,
                        payload_sha256 TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('started','completed','failed')),
                        result_sha256 TEXT,
                        error_code TEXT,
                        started_utc TEXT NOT NULL,
                        finished_utc TEXT,
                        result_metadata_json TEXT,
                        result_metadata_sha256 TEXT
                    )
                    """
                )
                columns = {
                    row[1]
                    for row in self._connection.execute(
                        "PRAGMA table_info(execution_journal)"
                    ).fetchall()
                }
                for name, definition in (
                    ("result_metadata_json", "TEXT"),
                    ("result_metadata_sha256", "TEXT"),
                ):
                    if name not in columns:
                        self._connection.execute(
                            f"ALTER TABLE execution_journal ADD COLUMN {name} {definition}"
                        )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def _reserve(self, operation_id: str, payload_hash: str) -> dict[str, object] | None:
        """Atomically inspect or reserve an operation without running it."""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT payload_sha256,status,result_sha256,error_code,"
                    "result_metadata_json,result_metadata_sha256 "
                    "FROM execution_journal WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                if row is not None:
                    stored_hash, status, result_hash, error_code, metadata_json, metadata_hash = row
                    if stored_hash != payload_hash:
                        raise ReplayConflict(
                            f"operation_id {operation_id!r} has a different payload"
                        )
                    self._connection.execute("COMMIT")
                    return {
                        "stored_hash": stored_hash,
                        "status": status,
                        "result_hash": result_hash,
                        "error_code": error_code,
                        "metadata_json": metadata_json,
                        "metadata_hash": metadata_hash,
                    }
                self._connection.execute(
                    "INSERT INTO execution_journal "
                    "(operation_id,payload_sha256,status,started_utc) "
                    "VALUES (?,?,?,?)",
                    (operation_id, payload_hash, _STARTED, _utc()),
                )
                self._connection.execute("COMMIT")
                return None
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def _finish(
        self,
        operation_id: str,
        status: str,
        result_hash: str | None,
        error_code: str | None,
        metadata_json: str | None = None,
        metadata_hash: str | None = None,
    ) -> None:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    "UPDATE execution_journal SET status=?,result_sha256=?,"
                    "error_code=?,finished_utc=?,result_metadata_json=?,"
                    "result_metadata_sha256=? WHERE operation_id=?",
                    (
                        status,
                        result_hash,
                        error_code,
                        _utc(),
                        metadata_json,
                        metadata_hash,
                        operation_id,
                    ),
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def execute_once(
        self,
        operation_id: str,
        payload: object,
        executor: Callable[[], object],
        result_metadata: Callable[[object], object] | None = None,
    ) -> dict[str, object]:
        """Reserve and execute once; never replay a started side effect."""
        if not isinstance(operation_id, str) or not _OPERATION_ID.fullmatch(operation_id):
            raise ValueError("operation_id must match the bounded identifier format")
        payload_hash = _sha256(_canonical_json(payload))
        prior = self._reserve(operation_id, payload_hash)
        if prior is not None:
            if prior["status"] == _COMPLETED:
                replayed = {
                    "status": "REPLAYED",
                    "operation_id": operation_id,
                    "payload_sha256": payload_hash,
                    "result_sha256": prior["result_hash"],
                }
                metadata_json = prior["metadata_json"]
                metadata_hash = prior["metadata_hash"]
                if metadata_json is not None:
                    if metadata_hash is None or _sha256(metadata_json) != metadata_hash:
                        raise ValueError("Stored result metadata hash mismatch")
                    try:
                        metadata = json.loads(metadata_json)
                        if _canonical_metadata(metadata) != metadata_json:
                            raise ValueError("Stored result metadata is not canonical")
                    except (TypeError, ValueError, json.JSONDecodeError) as exc:
                        raise ValueError("Stored result metadata is invalid") from exc
                    replayed["result_metadata"] = metadata
                return replayed
            if prior["status"] == _STARTED:
                return {
                    "status": "REQUIRES_RECONCILIATION",
                    "operation_id": operation_id,
                    "payload_sha256": payload_hash,
                }
            # A failed operation is safe to retry with the same payload.
            with self._lock:
                self._connection.execute("BEGIN IMMEDIATE")
                try:
                    self._connection.execute(
                        "DELETE FROM execution_journal WHERE operation_id=? AND status=?",
                        (operation_id, _FAILED),
                    )
                    self._connection.execute(
                        "INSERT INTO execution_journal "
                        "(operation_id,payload_sha256,status,started_utc) VALUES (?,?,?,?)",
                        (operation_id, payload_hash, _STARTED, _utc()),
                    )
                    self._connection.execute("COMMIT")
                except Exception:
                    self._connection.execute("ROLLBACK")
                    raise
        try:
            result = executor()
        except Exception:
            self._finish(operation_id, _FAILED, None, "execution_failed")
            return {
                "status": "FAILED",
                "operation_id": operation_id,
                "payload_sha256": payload_hash,
                "error_code": "execution_failed",
            }
        try:
            result_hash = _sha256(_canonical_json(result))
        except (TypeError, ValueError):
            self._finish(operation_id, _FAILED, None, "result_not_serializable")
            return {
                "status": "FAILED",
                "operation_id": operation_id,
                "payload_sha256": payload_hash,
                "error_code": "result_not_serializable",
            }
        metadata_json = None
        metadata_hash = None
        if result_metadata is not None:
            try:
                metadata_json = _canonical_metadata(result_metadata(result))
                metadata_hash = _sha256(metadata_json)
            except Exception:
                self._finish(operation_id, _FAILED, None, "metadata_not_serializable")
                return {
                    "status": "FAILED",
                    "operation_id": operation_id,
                    "payload_sha256": payload_hash,
                    "error_code": "metadata_not_serializable",
                }
        self._finish(operation_id, _COMPLETED, result_hash, None, metadata_json, metadata_hash)
        executed = {
            "status": "EXECUTED",
            "operation_id": operation_id,
            "payload_sha256": payload_hash,
            "result_sha256": result_hash,
        }
        if metadata_json is not None:
            executed["result_metadata"] = json.loads(metadata_json)
        return executed


__all__ = ["ExecutionJournal", "ReplayConflict"]
