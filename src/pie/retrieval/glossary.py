"""Durable project glossary with evidence references; never fabricates facts."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from pie.storage.database import connect

MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS project_glossary (
 key TEXT PRIMARY KEY, description TEXT NOT NULL, source_path TEXT NOT NULL,
 source_sha256 TEXT NOT NULL, updated_utc TEXT NOT NULL
);
"""

def remember(root: Path, key: str, description: str, source_path: str) -> dict[str, object]:
    root = Path(root).resolve()
    if not key.strip() or not description.strip():
        raise ValueError("Glossary key and description are required")
    source = (root / source_path).resolve()
    if not source.is_relative_to(root) or not source.is_file() or source.is_symlink():
        raise ValueError("Evidence source must be a real file inside the project")
    import hashlib
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    conn = connect(root / ".pie" / "index.sqlite3")
    try:
        conn.executescript(MEMORY_SCHEMA)
        with conn:
            conn.execute("""INSERT INTO project_glossary(key,description,source_path,source_sha256,updated_utc)
                 VALUES (?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET description=excluded.description,
                 source_path=excluded.source_path,source_sha256=excluded.source_sha256,
                 updated_utc=excluded.updated_utc""",
                 (key.strip(),description.strip(),source.relative_to(root).as_posix(),
                  digest,datetime.now(timezone.utc).isoformat()))
        return {"key":key.strip(),"source":source.relative_to(root).as_posix(),"state":"CURRENT"}
    finally:
        conn.close()

def recall(root: Path, query: str = "", limit: int = 25) -> dict[str, object]:
    root = Path(root).resolve()
    if not 1 <= limit <= 200:
        raise ValueError("limit out of range")
    import hashlib
    conn = connect(root / ".pie" / "index.sqlite3")
    try:
        conn.executescript(MEMORY_SCHEMA)
        rows = conn.execute("""SELECT key,description,source_path,source_sha256,updated_utc
                  FROM project_glossary WHERE key LIKE ? OR description LIKE ?
                  ORDER BY key LIMIT ?""",
                  ("%"+query.replace("%","\\%").replace("_","\\_")+"%",)*2+(limit,)).fetchall()
        items=[]
        for row in rows:
            p=(root / row["source_path"]).resolve()
            state="STALE"
            if p.is_relative_to(root) and p.is_file():
                state="CURRENT" if hashlib.sha256(p.read_bytes()).hexdigest()==row["source_sha256"] else "STALE"
            items.append({"key":row["key"],"description":row["description"] if state=="CURRENT" else None,
                          "source":row["source_path"],"state":state,"updated_utc":row["updated_utc"]})
        return {"query":query,"entries":items}
    finally:
        conn.close()
