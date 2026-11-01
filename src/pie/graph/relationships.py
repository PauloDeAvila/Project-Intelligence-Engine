"""Conservative Python static relationship extraction from an indexed repository.

No speculative call resolution: calls are recorded as syntactic evidence with
status 'unresolved'. Only local import edges are resolved by exact module path.
"""
from __future__ import annotations

import ast
from hashlib import sha256
from pathlib import Path

from pie.storage.database import connect

RELATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY,
    source_file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    source_symbol_id INTEGER REFERENCES symbols(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    target_expression TEXT NOT NULL,
    target_file_id INTEGER REFERENCES files(id) ON DELETE SET NULL,
    line INTEGER NOT NULL,
    resolution_status TEXT NOT NULL DEFAULT 'unresolved',
    UNIQUE(source_file_id, source_symbol_id, relation_type, target_expression, line)
);
CREATE INDEX IF NOT EXISTS idx_rel_source ON relations(source_symbol_id);
CREATE INDEX IF NOT EXISTS idx_rel_target ON relations(target_file_id);
"""


def _expression(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _expression(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _enclosing_symbol(conn, file_id: int, lineno: int):
    return conn.execute(
        "SELECT id FROM symbols WHERE file_id=? AND start_line<=? AND end_line>=? "
        "ORDER BY (end_line-start_line) ASC, start_line DESC LIMIT 1",
        (file_id, lineno, lineno),
    ).fetchone()


def _index_fingerprint(conn) -> str:
    rows = conn.execute('SELECT path,sha256 FROM files ORDER BY path').fetchall()
    return sha256('\n'.join(f"{r['path']}:{r['sha256']}" for r in rows).encode()).hexdigest()


def build_relationships(root: Path) -> dict[str, object]:
    """Rebuild static relations atomically, refusing incomplete indexes."""
    root = Path(root).resolve()
    db = root / '.pie' / 'index.sqlite3'
    if not db.is_file():
        raise ValueError('Run pie index first')
    conn = connect(db)
    try:
        state = conn.execute("SELECT value FROM metadata WHERE key='index_state'").fetchone()
        if not state or state[0] != 'CURRENT':
            raise ValueError('Index must be CURRENT before building relationships')
        conn.executescript(RELATION_SCHEMA)
        files = conn.execute("SELECT id,path,sha256 FROM files ORDER BY path").fetchall()
        module_map = {row['path'][:-3].replace('/', '.'): row['id'] for row in files if row['path'].endswith('.py')}
        count = 0
        with conn:
            conn.execute('DELETE FROM relations')
            for file in files:
                path = root / file['path']
                data = path.read_bytes()
                from hashlib import sha256
                if sha256(data).hexdigest() != file['sha256']:
                    raise ValueError(f'Stale source file: {file["path"]}')
                try:
                    tree = ast.parse(data.decode('utf-8-sig'), filename=file['path'])
                except (SyntaxError, UnicodeDecodeError) as exc:
                    raise ValueError(f'Cannot parse {file["path"]}: {exc}') from exc
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        names = [(a.name, None) for a in node.names] if isinstance(node, ast.Import) else [(node.module or '', node.level) for _ in node.names]
                        for name, level in names:
                            # Relative imports require package semantics and stay unresolved.
                            target = module_map.get(name) if not level else None
                            conn.execute('INSERT OR IGNORE INTO relations(source_file_id, source_symbol_id, relation_type, target_expression, target_file_id, line, resolution_status) VALUES (?,?,?,?,?,?,?)',
                                (file['id'], None, 'IMPORTS', ('.' * (level or 0)) + name, target, node.lineno, 'verified' if target is not None else 'unresolved'))
                            count += 1
                    elif isinstance(node, ast.Call):
                        expr = _expression(node.func)
                        if not expr:
                            continue
                        sym = _enclosing_symbol(conn, file['id'], node.lineno)
                        conn.execute('INSERT OR IGNORE INTO relations(source_file_id, source_symbol_id, relation_type, target_expression, target_file_id, line, resolution_status) VALUES (?,?,?,?,?,?,?)',
                            (file['id'], sym['id'] if sym else None, 'CALLS', expr, None, node.lineno, 'unresolved'))
                        count += 1
            conn.execute("INSERT INTO metadata(key,value) VALUES ('relations_source_state','CURRENT') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
            conn.execute("INSERT INTO metadata(key,value) VALUES ('relations_fingerprint',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (_index_fingerprint(conn),))
        return {'relations_observed': count, 'stored': conn.execute('SELECT COUNT(*) FROM relations').fetchone()[0], 'resolution': 'conservative_static'}
    finally:
        conn.close()


def _drifted_sources(conn, root: Path, paths: set[str]) -> list[str]:
    """Return source paths whose content on disk no longer matches the index.

    `_index_fingerprint` only reflects the stored rows, so it cannot notice a
    file edited after indexing. Relationships carry line numbers and enclosing
    symbols taken from that file, so reporting them as CURRENT while the source
    has drifted would present stale structure as if it were current.
    """
    if not paths:
        return []
    placeholders = ",".join("?" * len(paths))
    drifted = []
    for row in conn.execute(
        f"SELECT path, sha256 FROM files WHERE path IN ({placeholders})", tuple(paths)
    ):
        try:
            content = (root / row["path"]).read_bytes()
        except OSError:
            drifted.append(row["path"])
            continue
        if sha256(content).hexdigest() != row["sha256"]:
            drifted.append(row["path"])
    return sorted(drifted)


def get_relationships(root: Path, name: str, limit: int = 100) -> dict[str, object]:
    if not 1 <= limit <= 500:
        raise ValueError('limit must be between 1 and 500')
    root = Path(root).resolve()
    conn = connect(root / '.pie' / 'index.sqlite3')
    try:
        if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='relations'").fetchone():
            return {'relations': [], 'drifted_sources': [], 'warning': 'Run pie graph-build first'}
        rows = conn.execute('''SELECT r.relation_type,r.target_expression,r.line,r.resolution_status,
            f.path, s.qualified_name AS source_symbol, tf.path AS target_path
            FROM relations r JOIN files f ON f.id=r.source_file_id
            LEFT JOIN symbols s ON s.id=r.source_symbol_id
            LEFT JOIN files tf ON tf.id=r.target_file_id
            WHERE s.qualified_name=? OR f.path=? OR s.name=?
            ORDER BY f.path,r.line LIMIT ?''', (name, name, name, limit)).fetchall()
        state = conn.execute("SELECT value FROM metadata WHERE key='index_state'").fetchone()
        rel_state = conn.execute("SELECT value FROM metadata WHERE key='relations_source_state'").fetchone()
        saved = conn.execute("SELECT value FROM metadata WHERE key='relations_fingerprint'").fetchone()
        involved = {row['path'] for row in rows if row['path']}
        involved |= {row['target_path'] for row in rows if row['target_path']}
        drifted = _drifted_sources(conn, root, involved)
        fresh = bool(state and state[0]=='CURRENT' and saved and saved[0]==_index_fingerprint(conn) and not drifted)
        return {'index_state': state[0] if state else 'UNINDEXED',
                'relations_state': 'CURRENT' if fresh and rel_state and rel_state[0]=='CURRENT' else 'STALE',
                'drifted_sources': drifted,
                'relations': [dict(row) for row in rows]}
    finally:
        conn.close()
