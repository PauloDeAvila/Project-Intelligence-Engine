"""Local, privacy-preserving task and application usage accounting.

Gateway character counts are observations, not provider token usage.
Provider tokens are imported only from validated Codex certification records.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
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
 surface TEXT NOT NULL,
 tool TEXT NOT NULL,
 state TEXT NOT NULL,
 source_chars INTEGER NOT NULL,
 returned_chars INTEGER NOT NULL,
 elapsed_ms REAL NOT NULL,
 provider_input_tokens INTEGER,
 provider_cached_tokens INTEGER,
 provider_output_tokens INTEGER,
 condition TEXT NOT NULL DEFAULT 'observed'
);
CREATE INDEX IF NOT EXISTS pie_task_usage_by_task
 ON pie_task_usage(app, task_id, created_utc);
"""
_ALLOWED = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def app_for(surface: str, tool: str) -> str:
    t = tool.lower()
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
                app: str | None = None, task_id: str | None = None) -> None:
    app = app or os.environ.get("PIE_APP") or app_for(surface, tool)
    task_id = task_id or task_id_from_env()
    if not _ALLOWED.fullmatch(app) or not _ALLOWED.fullmatch(task_id):
        raise ValueError("Invalid app or task identifier")
    if any(type(x) is not int or x < 0 for x in (source_chars, returned_chars)):
        raise ValueError("Invalid character counts")
    dbpath = workspace_file(root)
    dbpath.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(dbpath, timeout=5)) as db:
        with db:
            db.executescript(SCHEMA)
            db.execute(
                """INSERT INTO pie_task_usage
                (created_utc,app,task_id,surface,tool,state,source_chars,
                 returned_chars,elapsed_ms) VALUES (?,?,?,?,?,?,?,?,?)""",
                (datetime.now(timezone.utc).isoformat(), app, task_id,
                 surface, tool[:120], state[:60], source_chars,
                 returned_chars, elapsed_ms))
            db.execute("""DELETE FROM pie_task_usage WHERE id NOT IN
                (SELECT id FROM pie_task_usage ORDER BY id DESC LIMIT 100000)""")


def import_provider_record(root: Path, record: dict, *, app: str, task_id: str) -> None:
    """Import one locally validated capture, never its prompt or answer."""
    from pie.certification.live_codex import _record
    _record(record)
    if not _ALLOWED.fullmatch(app) or not _ALLOWED.fullmatch(task_id):
        raise ValueError("Invalid app/task")
    u = record["usage"]
    dbpath = workspace_file(root)
    dbpath.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(dbpath, timeout=5)) as db:
        with db:
            db.executescript(SCHEMA)
            db.execute("""INSERT INTO pie_task_usage
                (created_utc,app,task_id,surface,tool,state,source_chars,
                 returned_chars,elapsed_ms,provider_input_tokens,
                 provider_cached_tokens,provider_output_tokens,condition)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (datetime.now(timezone.utc).isoformat(), app, task_id,
                 "provider", "codex_exec", "PROVIDER_REPORTED", 0, 0,
                 record["runtime_ms"], u["input_tokens"],
                 u["cached_input_tokens"], u["output_tokens"],
                 record["condition"]))


def report(root: Path) -> dict:
    dbpath = workspace_file(root)
    if not dbpath.exists():
        return {"state": "NO_OBSERVATIONS", "apps": [], "provider_certified": False}
    with closing(sqlite3.connect(dbpath, timeout=5)) as db:
        db.executescript(SCHEMA)
        rows = db.execute("""SELECT app,task_id,condition,COUNT(*),
            SUM(source_chars),SUM(returned_chars),
            SUM(provider_input_tokens),SUM(provider_cached_tokens),
            SUM(provider_output_tokens),SUM(elapsed_ms)
            FROM pie_task_usage GROUP BY app,task_id,condition
            ORDER BY app,task_id,condition""").fetchall()
    groups = []
    for app,task,condition,calls,src,returned,inp,cached,out,ms in rows:
        groups.append({"app": app, "task_id": task, "condition": condition,
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
    result = json.dumps(report(args.workspace), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result + "\n", encoding="utf-8")
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
