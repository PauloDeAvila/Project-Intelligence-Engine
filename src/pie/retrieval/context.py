"""Evidence-oriented context retrieval; bounded, deterministic and offline."""
from __future__ import annotations

from pathlib import Path

from pie.storage.database import connect
from pie.graph.relationships import get_relationships


def build_context(root: Path, query: str, max_chars: int = 12000, limit: int = 12) -> dict[str, object]:
    if not query.strip():
        raise ValueError('Query cannot be empty')
    if not 500 <= max_chars <= 200000 or not 1 <= limit <= 100:
        raise ValueError('Invalid context limits')
    root = Path(root).resolve()
    db = root / '.pie' / 'index.sqlite3'
    if not db.is_file():
        raise ValueError('Run pie index first')
    conn = connect(db)
    try:
        meta = {r['key']: r['value'] for r in conn.execute('SELECT key,value FROM metadata')}
        escaped = query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        rows = conn.execute("""SELECT s.qualified_name,s.name,s.kind,s.start_line,s.end_line,f.path,f.sha256
            FROM symbols s JOIN files f ON f.id=s.file_id
            WHERE s.qualified_name LIKE ? ESCAPE '\\' OR s.name LIKE ? ESCAPE '\\'
            ORDER BY CASE WHEN s.name=? THEN 0 ELSE 1 END, LENGTH(s.qualified_name),f.path LIMIT ?""",
            (f'%{escaped}%', f'%{escaped}%', query, limit)).fetchall()
        used = 0
        snippets = []
        omitted = 0
        from hashlib import sha256
        for row in rows:
            p = root / row['path']
            try:
                data = p.read_bytes()
            except OSError:
                omitted += 1
                continue
            if sha256(data).hexdigest() != row['sha256']:
                omitted += 1
                continue
            text = data.decode('utf-8-sig', errors='replace').splitlines()
            snippet = '\n'.join(text[max(0,row['start_line']-1):row['end_line']])
            if used + len(snippet) > max_chars:
                omitted += 1
                continue
            snippets.append({'symbol': row['qualified_name'], 'kind': row['kind'], 'path':row['path'],
                'start_line':row['start_line'], 'end_line':row['end_line'], 'content':snippet})
            used += len(snippet)
        rels = []
        for item in snippets:
            rels.extend(get_relationships(root, item['symbol'], limit=30).get('relations', []))
        return {'query':query, 'index_state':meta.get('index_state','UNINDEXED'),
            'source_ranges':snippets, 'relationships':rels[:100], 'omitted':omitted,
            'source_characters':used, 'note':'CALLS edges are syntactic and unresolved; source ranges hash-verified'}
    finally:
        conn.close()
