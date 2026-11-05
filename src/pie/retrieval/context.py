"""Evidence-oriented context retrieval; bounded, deterministic and offline."""
from __future__ import annotations

from pathlib import Path
import json

from pie.storage.database import connect
from pie.graph.relationships import get_relationships


def build_context(root: Path, query: str, max_chars: int = 12000, limit: int = 12,
                  *, strategy: str = "exact", include_body: bool = False) -> dict[str, object]:
    if strategy == "smart":
        from pie.retrieval.intelligence import smart_context
        return smart_context(root, query, max_chars=max_chars, limit=limit,
                             include_body=include_body)
    if strategy != "exact":
        raise ValueError("Unknown context retrieval strategy")
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
        diagnostics = []
        from hashlib import sha256
        for row in rows:
            p = root / row['path']
            try:
                resolved = p.resolve()
                if not resolved.is_relative_to(root) or p.is_symlink():
                    omitted += 1
                    diagnostics.append({'code': 'source_path_outside_root', 'path': row['path']})
                    continue
                data = resolved.read_bytes()
            except OSError:
                omitted += 1
                diagnostics.append({'code': 'file_unreadable', 'path': row['path']})
                continue
            if sha256(data).hexdigest() != row['sha256']:
                omitted += 1
                diagnostics.append({'code': 'source_hash_mismatch', 'path': row['path']})
                continue
            text = data.decode('utf-8-sig', errors='replace').splitlines()
            snippet = '\n'.join(text[max(0,row['start_line']-1):row['end_line']])
            if used + len(snippet) > max_chars:
                omitted += 1
                diagnostics.append({'code': 'budget_exceeded', 'path': row['path']})
                continue
            snippets.append({'symbol': row['qualified_name'], 'kind': row['kind'], 'path':row['path'],
                'start_line':row['start_line'], 'end_line':row['end_line'],
                'sha256':row['sha256'], 'content':snippet})
            used += len(snippet)
        context_state = 'STALE' if any(d['code'] in ('source_hash_mismatch','file_unreadable') for d in diagnostics) else ('PARTIAL' if omitted else meta.get('index_state','UNINDEXED'))
        rels = []
        if context_state == 'CURRENT':
            for item in snippets:
                response = get_relationships(root, item['symbol'], limit=30)
                if response.get('relations_state') != 'CURRENT':
                    context_state = 'STALE'
                    rels = []
                    break
                rels.extend(response.get('relations', []))
        result = {'query':query, 'index_state':meta.get('index_state','UNINDEXED'),
            'context_state':context_state, 'source_ranges':snippets, 'relationships':rels[:100],
            'omitted':omitted, 'diagnostics':diagnostics,
            'source_characters':used,
            'note':'CALLS edges are syntactic and unresolved; source ranges hash-verified'}
        # Budget counts the entire serialized response, not just code excerpts.
        while len(json.dumps(result, ensure_ascii=False)) > max_chars:
            if result['relationships']:
                result['relationships'].pop()
            elif result['source_ranges']:
                result['source_ranges'].pop()
                result['omitted'] += 1
                result['context_state'] = 'PARTIAL'
            elif result['diagnostics']:
                result['diagnostics'].pop()
            else:
                # Metadata alone can exceed tiny budgets for giant queries.
                raise ValueError('Response metadata exceeds context budget')
        return result
    finally:
        conn.close()
