"""Local, privacy-preserving task and application usage accounting.

Gateway character counts are observations, not provider token usage.
Provider tokens are imported only from validated Codex certification records.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import re
import sqlite3

from pie.storage.locations import workspace_file

SCHEMA = """
CREATE TABLE IF NOT EXISTS pie_task_usage (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 created_utc TEXT NOT NULL,
 app TEXT NOT NULL,
 task_id TEXT NOT NULL,
 run_id TEXT NOT NULL,
 surface TEXT NOT NULL,
 tool TEXT NOT NULL,
 tool_name TEXT NOT NULL,
 state TEXT NOT NULL,
 status TEXT NOT NULL,
 source_chars INTEGER NOT NULL,
 returned_chars INTEGER NOT NULL,
 elapsed_ms REAL NOT NULL,
 provider_input_tokens INTEGER,
 provider_cached_tokens INTEGER,
 provider_output_tokens INTEGER,
 condition TEXT NOT NULL DEFAULT 'observed',
 source_event_id TEXT
);
"""
_ALLOWED = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_MIGRATIONS = {
    "run_id": "TEXT NOT NULL DEFAULT 'run-legacy'",
    "tool_name": "TEXT NOT NULL DEFAULT ''",
    "status": "TEXT NOT NULL DEFAULT 'observed'",
    "source_event_id": "TEXT",
}


def _run_id() -> str:
    value = os.environ.get("PIE_RUN_ID") or f"run-{os.getpid()}"
    return value if _ALLOWED.fullmatch(value) else f"run-{os.getpid()}"


def _connect(root: Path) -> sqlite3.Connection:
    dbpath = workspace_file(root)
    dbpath.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(dbpath, timeout=5)
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    columns = {row[1] for row in db.execute("PRAGMA table_info(pie_task_usage)")}
    for name, definition in _MIGRATIONS.items():
        if name not in columns:
            db.execute(f"ALTER TABLE pie_task_usage ADD COLUMN {name} {definition}")
    db.execute("CREATE INDEX IF NOT EXISTS pie_task_usage_by_task ON pie_task_usage(app, task_id, run_id, created_utc)")
    db.execute("CREATE INDEX IF NOT EXISTS pie_task_usage_by_run ON pie_task_usage(run_id, created_utc)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS pie_task_usage_by_event ON pie_task_usage(source_event_id) WHERE source_event_id IS NOT NULL")
    return db


def app_for(surface: str, tool: str) -> str:
    t = tool.lower()
    if t == "pie_gateway_output_get":
        return os.environ.get("PIE_APP", "other_mcp")
    if t.startswith(("browser_", "playwright")) or "web" in t:
        return "web"
    if "blender" in t or t in ("get_scene_info", "get_object_info", "execute_blender_code"):
        return "blender"
    if surface == "terminal":
        return "terminal"
    return "other_mcp"


def task_id_from_env() -> str:
    value = os.environ.get("PIE_TASK_ID", "unassigned")
    return value if _ALLOWED.fullmatch(value) else "unassigned"


def record_task(root: Path, *, surface: str, tool: str, state: str,
                source_chars: int, returned_chars: int, elapsed_ms: float,
                app: str | None = None, task_id: str | None = None,
                run_id: str | None = None, condition: str | None = None,
                status: str | None = None) -> None:
    app = app or os.environ.get("PIE_APP") or app_for(surface, tool)
    task_id = task_id or task_id_from_env()
    run_id = run_id or _run_id()
    condition = condition or os.environ.get("PIE_CONDITION", "observed")
    status = status or state
    if not _ALLOWED.fullmatch(app) or not _ALLOWED.fullmatch(task_id) or not _ALLOWED.fullmatch(run_id):
        raise ValueError("Invalid app or task identifier")
    if any(type(x) is not int or x < 0 for x in (source_chars, returned_chars)):
        raise ValueError("Invalid character counts")
    if isinstance(elapsed_ms, bool) or not isinstance(elapsed_ms, (int, float)) or elapsed_ms < 0:
        raise ValueError("Invalid elapsed time")
    with closing(_connect(root)) as db:
        with db:
            db.executescript(SCHEMA)
            db.execute(
                """INSERT INTO pie_task_usage
                (created_utc,app,task_id,run_id,surface,tool,tool_name,state,status,
                 source_chars,returned_chars,elapsed_ms,condition) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (datetime.now(timezone.utc).isoformat(), app, task_id, run_id,
                 surface, tool[:120], tool[:120], state[:60], status[:60],
                 source_chars, returned_chars, float(elapsed_ms), condition[:60]))
            db.execute("""DELETE FROM pie_task_usage WHERE id NOT IN
                (SELECT id FROM pie_task_usage ORDER BY id DESC LIMIT 100000)""")


def import_provider_record(root: Path, record: dict, *, app: str, task_id: str) -> None:
    """Import one locally validated capture, never its prompt or answer."""
    from pie.certification.live_codex import _record
    _record(record)
    if not _ALLOWED.fullmatch(app) or not _ALLOWED.fullmatch(task_id):
        raise ValueError("Invalid app/task")
    u = record["usage"]
    event_id = hashlib.sha256("|".join(str(v) for v in (
        app, task_id, record.get("run_id") or "", record["condition"],
        record["scenario_id"], record["repetition"], record["configuration_sha256"]
    )).encode("utf-8")).hexdigest()
    with closing(_connect(root)) as db:
        with db:
            db.executescript(SCHEMA)
            db.execute("""INSERT OR IGNORE INTO pie_task_usage
                (created_utc,app,task_id,run_id,surface,tool,tool_name,state,status,source_chars,
                returned_chars,elapsed_ms,provider_input_tokens,
                provider_cached_tokens,provider_output_tokens,condition,source_event_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (datetime.now(timezone.utc).isoformat(), app, task_id,
                 record.get("run_id") or f"{record['condition']}-{record['scenario_id']}-{record['repetition']}",
                 "provider", "codex_exec", "codex_exec", "PROVIDER_REPORTED", "success", 0, 0,
                 record["runtime_ms"], u["input_tokens"],
                 u["cached_input_tokens"], u["output_tokens"],
                 record["condition"], event_id))


def report(root: Path, *, app: str | None = None, task_id: str | None = None,
           run_id: str | None = None, since: str | None = None,
           until: str | None = None) -> dict:
    dbpath = workspace_file(root)
    if not dbpath.exists():
        return {"state": "NO_OBSERVATIONS", "apps": [], "provider_certified": False}
    with closing(_connect(root)) as db:
        where = []
        params: list[str] = []
        for column, value in (("app", app), ("task_id", task_id),
                              ("run_id", run_id)):
            if value is not None:
                if not _ALLOWED.fullmatch(value):
                    raise ValueError(f"Invalid {column}")
                where.append(f"{column}=?")
                params.append(value)
        if since is not None:
            where.append("created_utc>=?")
            params.append(since)
        if until is not None:
            where.append("created_utc<=?")
            params.append(until)
        predicate = " WHERE " + " AND ".join(where) if where else ""
        query = """SELECT app,task_id,condition,COUNT(*),
            SUM(source_chars),SUM(returned_chars),
            SUM(provider_input_tokens),SUM(provider_cached_tokens),
            SUM(provider_output_tokens),SUM(elapsed_ms),run_id
            FROM pie_task_usage""" + predicate + """ GROUP BY app,task_id,condition,run_id
            ORDER BY app,task_id,condition"""
        rows = db.execute(query, params).fetchall()
    groups = []
    for app,task,condition,calls,src,returned,inp,cached,out,ms,run_id in rows:
        groups.append({"app": app, "task_id": task, "run_id": run_id, "condition": condition,
                       "events": calls, "source_chars": src,
                       "returned_chars": returned,
                       "saved_chars": src-returned,
                       "input_tokens": inp, "cached_input_tokens": cached,
                       "output_tokens": out, "elapsed_ms": round(ms, 3)})
    return {"state": "OBSERVED" if groups else "NO_OBSERVATIONS",
            "apps": groups, "provider_certified": False,
            "note": "Observed usage only. Savings certification requires paired oracle-validated runs; character savings are not tokens."}


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="PIE task-level usage telemetry")
    sub = p.add_subparsers(dest="action", required=True)
    r = sub.add_parser("report")
    r.add_argument("--workspace", type=Path, default=Path.cwd())
    r.add_argument("--output", type=Path)
    r.add_argument("--app", choices=("blender", "web", "terminal", "other_mcp"))
    r.add_argument("--task-id")
    r.add_argument("--run-id")
    r.add_argument("--since")
    r.add_argument("--until")
    i = sub.add_parser("import-codex")
    i.add_argument("--workspace", type=Path, default=Path.cwd())
    i.add_argument("--record", type=Path, required=True)
    i.add_argument("--app", choices=("blender", "web"), required=True)
    i.add_argument("--task-id", required=True)
    args = p.parse_args(argv)
    if args.action == "import-codex":
        import_provider_record(args.workspace, json.loads(args.record.read_text(encoding="utf-8")),
                               app=args.app, task_id=args.task_id)
        return 0
    result = json.dumps(report(args.workspace, app=args.app, task_id=args.task_id,
                               run_id=args.run_id, since=args.since, until=args.until),
                        ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result + "\n", encoding="utf-8")
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
