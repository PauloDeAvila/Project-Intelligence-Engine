"""Offline SQLite FTS5/BM25 index for indexed Python symbol responsibilities.

FTS rows are synchronized with symbol_docs via triggers. No external model,
embedding service or dynamic SQL from user text. Falls back to lexical ranking
if SQLite lacks FTS5 support.
"""
from __future__ import annotations

import re
import sqlite3

_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9]{1,}")


def ensure_fts(conn: sqlite3.Connection) -> bool:
    """Install triggers and backfill once; do not rebuild on every query."""
    existed = conn.execute("SELECT 1 FROM sqlite_master WHERE name='symbol_fts'").fetchone() is not None
    try:
        conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS symbol_fts USING fts5(
            name, qualified_name, path, summary, signature, tokenize='unicode61'
        )""")
    except sqlite3.OperationalError as exc:
        if "no such module" in str(exc).lower() or "fts5" in str(exc).lower():
            return False
        raise
    if existed:
        return True
    conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS pie_fts_doc_insert AFTER INSERT ON symbol_docs BEGIN
          INSERT OR REPLACE INTO symbol_fts(rowid,name,qualified_name,path,summary,signature)
          SELECT NEW.symbol_id,s.name,s.qualified_name,f.path,NEW.summary,NEW.signature
          FROM symbols s JOIN files f ON f.id=s.file_id WHERE s.id=NEW.symbol_id;
        END;
        CREATE TRIGGER IF NOT EXISTS pie_fts_doc_update AFTER UPDATE ON symbol_docs BEGIN
          DELETE FROM symbol_fts WHERE rowid=OLD.symbol_id;
          INSERT OR REPLACE INTO symbol_fts(rowid,name,qualified_name,path,summary,signature)
          SELECT NEW.symbol_id,s.name,s.qualified_name,f.path,NEW.summary,NEW.signature
          FROM symbols s JOIN files f ON f.id=s.file_id WHERE s.id=NEW.symbol_id;
        END;
        CREATE TRIGGER IF NOT EXISTS pie_fts_doc_delete AFTER DELETE ON symbol_docs BEGIN
          DELETE FROM symbol_fts WHERE rowid=OLD.symbol_id;
        END;
    """)
    # Repair older databases once and after interrupted migrations.
    conn.execute("""INSERT OR REPLACE INTO symbol_fts(rowid,name,qualified_name,path,summary,signature)
        SELECT s.id,s.name,s.qualified_name,f.path,d.summary,d.signature
        FROM symbol_docs d JOIN symbols s ON s.id=d.symbol_id
        JOIN files f ON f.id=s.file_id
        WHERE NOT EXISTS (SELECT 1 FROM symbol_fts t WHERE t.rowid=s.id)""")
    conn.execute("""DELETE FROM symbol_fts WHERE rowid NOT IN
        (SELECT symbol_id FROM symbol_docs)""")
    return True


def search_fts(conn: sqlite3.Connection, query: str, *, limit: int = 100) -> list[tuple[int, float]]:
    """Return (symbol_id, BM25 score) ordered best first; malformed input is inert."""
    if not 1 <= limit <= 500:
        raise ValueError("invalid FTS limit")
    terms=list(dict.fromkeys(word.lower() for word in _WORD.findall(query)))[:16]
    if not terms:
        return []
    # Quote every token, preventing MATCH operators or column directives.
    match=" OR ".join('"' + word.replace('"','""') + '"' for word in terms)
    try:
        rows=conn.execute("""SELECT rowid, bm25(symbol_fts, 8.0, 6.0, 2.0, 3.0, 1.0) AS rank
                             FROM symbol_fts WHERE symbol_fts MATCH ?
                             ORDER BY rank, rowid LIMIT ?""",(match,limit)).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower() or "fts5" in str(exc).lower():
            return []
        raise
    return [(int(r[0]),float(r[1])) for r in rows]
