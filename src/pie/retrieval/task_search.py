"""Task-memory retrieval using the local SQLite FTS5 index.

Task/event entries are supplied claims, never verified source evidence.
A first-time backfill upgrades Stage 1 databases without deleting records.
"""
from __future__ import annotations

from contextlib import closing
import json
import re
import sqlite3
from pathlib import Path

from pie.retrieval.task_memory import _open

TOKEN = re.compile(r"(?u)\b[^\W_]+\b")
STOP = frozenset(("a o os as de da do das dos e em para por com que qual quais "
                  "como onde quando eu meu minha um uma uma the and for from with "
                  "what when why how did you was were").split())

FTS_TRIGGERS = (
    """CREATE TRIGGER IF NOT EXISTS pie_memory_task_insert AFTER INSERT ON pie_tasks BEGIN
       INSERT INTO pie_memory_fts(task_id,event_seq,kind,objective,body,reference)
       VALUES (NEW.task_id,'','objective',NEW.objective,'','');
       END""",
    """CREATE TRIGGER IF NOT EXISTS pie_memory_event_insert AFTER INSERT ON pie_task_events BEGIN
       INSERT INTO pie_memory_fts(task_id,event_seq,kind,objective,body,reference)
       VALUES (NEW.task_id,CAST(NEW.seq AS TEXT),NEW.kind,'',NEW.text,COALESCE(NEW.reference,''));
       END""",
)


def _ensure_fts(db: sqlite3.Connection) -> bool:
    """Serialize first-time schema creation/backfill between concurrent MCP clients."""
    # Existing PIE connection setup may leave a transaction open after symbol FTS backfill.
    db.commit()
    try:
        db.execute("BEGIN IMMEDIATE")
        present = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pie_memory_fts'"
        ).fetchone() is not None
        db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS pie_memory_fts USING fts5(
            task_id UNINDEXED, event_seq UNINDEXED, kind UNINDEXED,
            objective, body, reference, tokenize='unicode61')""")
        for statement in FTS_TRIGGERS:
            db.execute(statement)
        if not present:
            db.execute("""INSERT INTO pie_memory_fts(task_id,event_seq,kind,objective,body,reference)
                SELECT task_id,'','objective',objective,'','' FROM pie_tasks""")
            db.execute("""INSERT INTO pie_memory_fts(task_id,event_seq,kind,objective,body,reference)
                SELECT task_id,CAST(seq AS TEXT),kind,'',text,COALESCE(reference,'')
                FROM pie_task_events""")
        db.commit()
        return True
    except sqlite3.OperationalError as exc:
        db.rollback()
        if "no such module" in str(exc).lower() or "fts5" in str(exc).lower():
            return False
        raise
    except Exception:
        db.rollback()
        raise


def _terms(query: str) -> list[str]:
    if not isinstance(query, str) or not query.strip() or len(query) > 1024 or "\x00" in query:
        raise ValueError("query must be nonempty and <= 1024 characters")
    return list(dict.fromkeys(word.casefold() for word in TOKEN.findall(query)
                              if len(word) >= 2 and word.casefold() not in STOP))[:12]


def _search_fts(db: sqlite3.Connection, terms: list[str], limit: int) -> list[dict]:
    # Quoted independent lexical terms: no user-supplied FTS operators.
    match = " OR ".join('"' + word.replace('"','""') + '"' for word in terms)
    rows = db.execute("""SELECT f.task_id,f.event_seq,f.kind,f.objective,
        f.body,f.reference,t.objective AS task_objective,t.status,t.updated_utc,
        bm25(pie_memory_fts,0,0,0,6.0,3.0,1.0) AS score
        FROM pie_memory_fts f JOIN pie_tasks t ON t.task_id=f.task_id
        WHERE pie_memory_fts MATCH ? ORDER BY score, f.rowid LIMIT ?""",
        (match, limit)).fetchall()
    return [dict(row) for row in rows]


def _search_lexical(db: sqlite3.Connection, terms: list[str], limit: int) -> list[dict]:
    """Safe fallback for Python builds without SQLite FTS5."""
    # Parameterized OR predicates; never interpolate an untrusted query.
    predicates = []
    params = []
    for term in terms:
        predicates.append("(instr(lower(objective), ?) > 0 OR instr(lower(body), ?) > 0 OR instr(lower(reference), ?) > 0)")
        params.extend((term, term, term))
    sql = f"""SELECT task_id,event_seq,kind,objective,body,reference,
        task_objective,status,updated_utc,0.0 AS score FROM (
        SELECT t.task_id, '' AS event_seq, 'objective' AS kind,
               t.objective, '' AS body, '' AS reference,
               t.objective AS task_objective,t.status,t.updated_utc FROM pie_tasks t
        UNION ALL
        SELECT t.task_id,CAST(e.seq AS TEXT),e.kind,'' AS objective,
               e.text AS body,COALESCE(e.reference,'') AS reference,
               t.objective AS task_objective,t.status,t.updated_utc
        FROM pie_task_events e JOIN pie_tasks t ON e.task_id=t.task_id
        ) WHERE {" OR ".join(predicates)} ORDER BY updated_utc DESC,task_id LIMIT ?"""
    return [dict(row) for row in db.execute(sql, (*params, limit)).fetchall()]


def search_tasks(root: Path, query: str, *, limit: int = 10,
                 max_chars: int = 12000) -> dict:
    """Search objectives and events across sessions, with bounded faithful results."""
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("limit must be 1..20")
    if type(max_chars) is not int or not 1000 <= max_chars <= 64000:
        raise ValueError("max_chars must be 1000..64000")
    terms = _terms(query)
    if not terms:
        return {"query": query, "state": "NO_SEARCH_TERMS", "matches": [],
                "omitted": 0, "verification": "agent_supplied_unverified"}
    with closing(_open(root)) as db:
        fts = _ensure_fts(db)
        hits = (_search_fts(db, terms, limit + 1) if fts
                else _search_lexical(db, terms, limit + 1))
    items = []
    for row in hits[:limit]:
        # Do not silently paraphrase user-provided facts. If a record is too
        # large to return, omit it and report the omission.
        items.append({
            "task_id": row["task_id"],
            "event_id": int(row["event_seq"]) if row["event_seq"] else None,
            "kind": row["kind"],
            "objective": row["task_objective"],
            "text": row["body"] if row["event_seq"] else row["objective"],
            "reference": row["reference"] or None,
            "status": row["status"],
            "updated_utc": row["updated_utc"],
            "verification": "agent_supplied_unverified",
        })
    result = {"query": query, "state": "FOUND" if items else "NOT_FOUND",
              "backend": "fts5" if fts else "lexical_fallback",
              "matches": items, "omitted": max(0, len(hits) - len(items)),
              "omission_count_complete": len(hits) <= limit,
              "verification": "agent_supplied_unverified"}
    def length():
        return len(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    while length() > max_chars and result["matches"]:
        result["matches"].pop()
        result["omitted"] += 1
    if not result["matches"] and hits:
        result["state"] = "BUDGET_TOO_SMALL"
    if length() > max_chars:
        raise ValueError("Search metadata exceeds max_chars")
    return result
