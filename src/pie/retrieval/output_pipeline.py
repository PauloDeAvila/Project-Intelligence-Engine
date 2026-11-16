"""RTK-inspired, deterministic tool-output adapter with recoverable originals.

Not the RTK binary: no execution of shell commands, hooks or agent API interception.
Only redacted text is stored; full output can be retrieved by opaque ID.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from datetime import datetime, timezone, timedelta
import json
import hashlib
import re
import uuid
from pathlib import Path

from pie.retrieval.task_memory import _open

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
BEARER = re.compile(r"(?i)\b(authorization\s*:\s*bearer\s+)\S+")
CREDENTIAL = re.compile(r"(?i)\b(api[_-]?key|password|token)\s*[:=]\s*['\"]?[^\s,'\"]+")
OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")
FAILURE = re.compile(r"(?i)\b(fail(?:ed|ure)?|error|exception|traceback|assertionerror|fatal)\b")
MAX_OUTPUT_ROWS = 128
MAX_OUTPUT_BYTES = 8_000_000
RETENTION_DAYS = 7
SCHEMA = """
CREATE TABLE IF NOT EXISTS pie_tool_outputs (
 output_id TEXT PRIMARY KEY, kind TEXT NOT NULL, content TEXT NOT NULL,
 sha256 TEXT NOT NULL, created_utc TEXT NOT NULL
);
"""


def _redact(value: str) -> str:
    value = ANSI.sub("", value)
    value = BEARER.sub(r"\1[REDACTED]", value)
    value = CREDENTIAL.sub(lambda m: f"{m.group(1)}=[REDACTED]", value)
    return OPENAI_KEY.sub("[REDACTED]", value)


def _open_outputs(root: Path):
    db = _open(root)
    try:
        db.execute(SCHEMA)
        # Additive migration, transactionally protected for existing user databases.
        db.execute("BEGIN IMMEDIATE")
        columns = {row[1] for row in db.execute("PRAGMA table_info(pie_tool_outputs)")}
        if "manifest_json" not in columns:
            db.execute("ALTER TABLE pie_tool_outputs ADD COLUMN manifest_json TEXT")
        db.commit()
    except Exception:
        db.close()
        raise
    return db


def _validate_manifest(root: Path, manifest: list[dict] | None) -> list[dict]:
    if manifest is None:
        return []
    if not isinstance(manifest, list) or len(manifest) > 128:
        raise ValueError("Source manifest must have at most 128 entries")
    base = Path(root).resolve(strict=True)
    seen = {}
    for item in manifest:
        if not isinstance(item, dict):
            raise ValueError("Invalid source manifest item")
        path, expected = item.get("path"), item.get("sha256")
        if not isinstance(path, str) or not path or not isinstance(expected, str) or (
            len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected)):
            raise ValueError("Invalid source manifest entry")
        relative = Path(path)
        target = base / relative
        if relative.is_absolute() or ".." in relative.parts or target.is_symlink():
            raise ValueError("Source manifest path is not allowed")
        resolved = target.resolve()
        if not resolved.is_relative_to(base) or not resolved.is_file():
            raise ValueError("Source manifest path unavailable")
        if hashlib.sha256(resolved.read_bytes()).hexdigest() != expected:
            raise ValueError("Source evidence changed or stale")
        previous = seen.get(path)
        if previous and previous != expected:
            raise ValueError("Conflicting source manifest")
        seen[path] = expected
    return [{"path": path, "sha256": digest} for path, digest in sorted(seen.items())]


def _prune(db) -> None:
    oldest = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    db.execute("DELETE FROM pie_tool_outputs WHERE created_utc < ?", (oldest,))
    db.execute(
        "DELETE FROM pie_tool_outputs WHERE output_id NOT IN "
        "(SELECT output_id FROM pie_tool_outputs ORDER BY created_utc DESC, output_id DESC LIMIT ?)",
        (MAX_OUTPUT_ROWS,),
    )
    # Cap total stored UTF-8 bytes, not just row count.
    while True:
        size = db.execute("SELECT COALESCE(SUM(LENGTH(CAST(content AS BLOB))),0) "
                          "FROM pie_tool_outputs").fetchone()[0]
        if size <= MAX_OUTPUT_BYTES:
            return
        old = db.execute("SELECT output_id FROM pie_tool_outputs "
                         "ORDER BY created_utc ASC, output_id ASC LIMIT 1").fetchone()
        if old is None:
            return
        db.execute("DELETE FROM pie_tool_outputs WHERE output_id=?", (old[0],))


def compact_output(root: Path, content: str, *, kind: str = "log",
                   max_chars: int = 4000, exit_code: int | None = None,
                   source_manifest: list[dict] | None = None) -> dict:
    """Save the sanitized original and return a bounded, recoverable summary."""
    if not isinstance(content, str) or len(content) > 500_000:
        raise ValueError("content must be text <= 500000 characters")
    if not isinstance(kind, str) or kind not in ("log", "test", "git", "terminal", "web", "api"):
        raise ValueError("invalid output kind")
    if type(max_chars) is not int or not 256 <= max_chars <= 64000:
        raise ValueError("max_chars must be 256..64000")
    if exit_code is not None and (type(exit_code) is not int or not -65535 <= exit_code <= 65535):
        raise ValueError("exit_code must be an integer in range")
    verified_manifest = _validate_manifest(root, source_manifest)
    original = _redact(content)
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
    lines = [line.rstrip() for line in original.splitlines() if line.strip()]
    counts = Counter(lines)
    unique = list(counts)
    # Test and command failures first, preserving source line text (except secret redaction).
    if kind in ("test", "terminal", "log"):
        unique.sort(key=lambda line: 0 if FAILURE.search(line) else 1)
    output_id = uuid.uuid4().hex
    # Conservative fixed reserve: metadata are deliberately excluded from payload budget.
    budget = max_chars - 180
    compacted = []
    used = 0
    omitted = 0
    for line in unique:
        candidate = line if counts[line] == 1 else f"{line} [x{counts[line]}]"
        # Long lines are omitted, not cut in the middle of a stack trace or negation.
        if used + len(candidate) + 1 > budget:
            omitted += 1
            continue
        compacted.append(candidate)
        used += len(candidate) + 1
    manifest_json = json.dumps(verified_manifest, separators=(",", ":"))
    cache_hit = False
    with closing(_open_outputs(root)) as db:
        with db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT output_id,content FROM pie_tool_outputs "
                "WHERE sha256=? AND kind=? AND manifest_json=? "
                "ORDER BY created_utc DESC LIMIT 1",
                (digest, kind, manifest_json),
            ).fetchone()
            timestamp = datetime.now(timezone.utc).isoformat()
            if current is not None and current["content"] == original:
                output_id = current["output_id"]
                cache_hit = True
                db.execute("UPDATE pie_tool_outputs SET created_utc=? WHERE output_id=?",
                           (timestamp, output_id))
            else:
                db.execute(
                    "INSERT INTO pie_tool_outputs"
                    "(output_id,kind,content,sha256,created_utc,manifest_json) VALUES (?,?,?,?,?,?)",
                    (output_id, kind, original, digest, timestamp, manifest_json),
                )
            _prune(db)
    response_text = "\n".join(compacted)
    # Not a token estimate: these are exact Unicode character counts for the
    # observed text payload, prior to envelope serialization.
    return {"output_id": output_id, "kind": kind, "cache_hit": cache_hit,
            "state": "PARTIAL" if omitted else "COMPLETE",
            "text": response_text, "sha256": digest,
            "source_chars": len(original), "returned_chars": len(response_text),
            "unique_lines": len(unique), "omitted_unique_lines": omitted,
            "redacted_before_storage": True, "exit_code": exit_code,
            "sanitized_recovery": True,
            "note": "Character reduction is not measured token or session savings."}


def recover_output(root: Path, output_id: str) -> dict:
    """Recover a project-local sanitized original; unknown IDs fail closed."""
    if not isinstance(output_id, str) or not re.fullmatch(r"[a-f0-9]{32}", output_id):
        raise ValueError("Invalid output ID")
    with closing(_open_outputs(root)) as db:
        _prune(db)
        db.commit()
        row = db.execute("SELECT kind, content, sha256, manifest_json FROM pie_tool_outputs "
                         "WHERE output_id=?", (output_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown output ID")
    if hashlib.sha256(row["content"].encode("utf-8")).hexdigest() != row["sha256"]:
        raise ValueError("Output integrity verification failed")
    manifest = json.loads(row["manifest_json"] or "[]")
    _validate_manifest(root, manifest)
    return {"output_id": output_id, "kind": row["kind"],
            "text": row["content"], "sha256": row["sha256"],
            "redacted_before_storage": True, "state": "COMPLETE_SANITIZED"}
