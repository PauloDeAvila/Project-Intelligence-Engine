"""Local retrieval over indexed Python symbols with source-verified ranking.

No model calls. Scores are heuristic; relationships are facts only when
the analysis layer marks the resolution verified.
"""
from __future__ import annotations

import ast
from hashlib import sha256
from pathlib import Path
import re

from pie.storage.database import connect
from pie.retrieval.fts import search_fts

_STOP = frozenset("the and for from with into this that those these function method class code find where which what does how can you uma para qual como onde que uma dos das por com sobre localizar função classe método arquivo".split())
_ALIASES = {
    "cache": ("cache", "cached", "caching", "memo", "memoize", "store"),
    "save": ("save", "write", "persist", "serialize", "store"),
    "load": ("load", "read", "parse", "deserialize", "open"),
    "validate": ("validate", "verify", "check", "assert"),
    "error": ("error", "exception", "fail", "raise"),
    "search": ("search", "find", "lookup", "query", "retrieve"),
    "render": ("render", "display", "draw", "paint"),
    "update": ("update", "refresh", "change", "modify"),
    "network": ("network", "http", "request", "response", "client"),
}
def _terms(value: str) -> set[str]:
    # Split snake_case, CamelCase and dotted qualified symbols.
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    words = set(re.findall(r"[a-z][a-z0-9]{2,}", value.lower()))
    return words - _STOP

def _query_terms(query: str) -> set[str]:
    terms = _terms(query)
    expanded = set(terms)
    for variants in _ALIASES.values():
        if terms.intersection(variants):
            expanded.update(variants)
    return expanded

def _description(source: str, start: int) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.lineno == start:
            return (ast.get_docstring(node) or "").split("\n", 1)[0][:400]
    return ""

def smart_context(root: Path, query: str, *, max_chars: int = 12000, limit: int = 8,
                  include_body: bool = False) -> dict[str, object]:
    """Rank symbol responsibility summaries, reading only selected source files.

    Summaries are derived from indexed AST snapshots. Source SHA-256 is verified
    before any selected evidence is returned. The serialized JSON obeys budget.
    """
    import json
    if not query.strip() or not 500 <= max_chars <= 200000 or not 1 <= limit <= 100:
        raise ValueError("Invalid query, budget or limit")
    root = Path(root).resolve()
    db = root / ".pie" / "index.sqlite3"
    if not db.is_file():
        raise ValueError("Run pie index first")
    conn = connect(db)
    try:
        state = conn.execute("SELECT value FROM metadata WHERE key='index_state'").fetchone()
        index_state = state[0] if state else "UNINDEXED"
        rows = conn.execute("""SELECT s.id,s.name,s.qualified_name,s.kind,s.start_line,s.end_line,
                                      f.path,f.sha256,
                                      COALESCE(d.summary,'') AS summary,
                                      COALESCE(d.signature,'') AS signature
                               FROM symbols s JOIN files f ON s.file_id=f.id
                               LEFT JOIN symbol_docs d ON d.symbol_id=s.id""").fetchall()
        fts_hits = search_fts(conn, query, limit=min(500,max(100,limit*12)))
        fts_position = {symbol_id: i for i,(symbol_id,_) in enumerate(fts_hits)}
        verified_counts = {r["target_name"]:r["n"] for r in conn.execute(
            "SELECT target_name, COUNT(*) AS n FROM usages WHERE resolution='verified' AND target_name IS NOT NULL GROUP BY target_name")}
        query_words = _query_terms(query)
        candidates = []
        for row in rows:
            name_words = _terms(row["qualified_name"])
            path_words = _terms(row["path"].replace("/", " "))
            desc_words = _terms(row["summary"])
            score = (8 * len(query_words & name_words)
                     + 4 * len(query_words & path_words)
                     + 3 * len(query_words & desc_words))
            if row["name"].lower() == query.strip().lower():
                score += 25
            rank = fts_position.get(row["id"])
            if rank is not None:
                score += max(2,10-rank//12)
            if score:
                score += min(3,verified_counts.get(row["name"],0))
                candidates.append((score,row))
        candidates.sort(key=lambda item: (-item[0],item[1]["path"],
                                          item[1]["start_line"],item[1]["qualified_name"]))
        selected=[]
        diagnostics=[]
        cached={}
        for score,row in candidates:
            if len(selected)>=limit:
                break
            path=row["path"]
            if path not in cached:
                try:
                    data=(root/path).read_bytes()
                    if sha256(data).hexdigest()!=row["sha256"]:
                        raise ValueError("source_hash_mismatch")
                    cached[path]=data.decode("utf-8-sig",errors="replace").splitlines()
                except (OSError,ValueError) as exc:
                    cached[path]=None
                    diagnostics.append({"path":path,
                        "code":"source_hash_mismatch" if isinstance(exc,ValueError) else "file_unreadable"})
            lines=cached[path]
            if lines is None:
                continue
            start,end=row["start_line"],row["end_line"]
            if start<1 or end>len(lines) or end<start:
                diagnostics.append({"path":path,"code":"invalid_source_range"})
                continue
            candidate={"symbol":row["qualified_name"],"path":path,"start_line":start,
                       "end_line":end,"kind":row["kind"],"score":score,
                       "signature":row["signature"] or lines[start-1].strip()[:250],
                       "description":row["summary"]}
            if include_body:
                candidate["content"]="\n".join(lines[start-1:end])
            selected.append(candidate)
        result={"query":query,"index_state":index_state,"context_state":index_state,
                "evidence":selected,"omitted":max(0,len(candidates)-len(selected)),
                "diagnostics":diagnostics,
                "method":"sqlite_ast_hybrid_fts5_graph_v3" if fts_hits else "sqlite_ast_summary_rank_v2",
                "note":"Local lexical scoring; source ranges hash-verified; unselected files not rechecked"}
        if diagnostics and result["context_state"]=="CURRENT":
            result["context_state"]="STALE"
        while len(json.dumps(result,ensure_ascii=False))>max_chars:
            if result["evidence"]:
                result["evidence"].pop()
                result["omitted"]+=1
                if result["context_state"]=="CURRENT":
                    result["context_state"]="PARTIAL"
            elif result["diagnostics"]:
                result["diagnostics"].pop()
            else:
                raise ValueError("Response metadata exceeds max_chars")
        return result
    finally:
        conn.close()


def impact(root: Path, name: str, *, limit: int = 100, depth: int = 2) -> dict[str, object]:
    """Bounded reverse-impact traversal through *verified* binding references.

    Direct matches and transitive *potential* consumers are deliberately separate.
    Ambiguous definitions are not traversed. Dynamic dispatch is not inferred.
    """
    from collections import deque
    from pie.retrieval.symbols import find_references, find_definitions
    if not 1 <= limit <= 500 or not 0 <= depth <= 5:
        raise ValueError("Invalid impact limit/depth")
    root=Path(root).resolve()
    result=find_references(root,name,limit=limit)
    direct=result.get("references",[])
    result["verified_references"]=sum(r.get("resolution")=="verified" for r in direct)
    result["unresolved_references"]=len(direct)-result["verified_references"]
    result["direct_affected_files"]=sorted({r["path"] for r in direct})
    expanded=[]
    ambiguous=[]
    visited=set()
    frontier=deque((r.get("consumer_symbol"),r["path"],1)
                   for r in direct if r.get("resolution")=="verified" and r.get("consumer_symbol"))
    while frontier and depth and len(expanded)<limit:
        symbol,path,level=frontier.popleft()
        if level>depth or (symbol,path) in visited:
            continue
        visited.add((symbol,path))
        lookup=find_definitions(root,symbol,limit=20)
        definitions=[d for d in lookup.get("definitions",[])
                     if d.get("qualified_name")==symbol and d.get("path")==path]
        if lookup.get("state")!="CURRENT" or len(definitions)!=1:
            ambiguous.append({"path":path,"symbol":symbol,"reason":"ambiguous_or_stale_definition"})
            continue
        consumers=find_references(root,symbol,limit=limit)
        if consumers.get("state")!="CURRENT":
            ambiguous.append({"path":path,"symbol":symbol,"reason":"stale_references"})
            continue
        for ref in consumers.get("references",[]):
            if ref.get("resolution")!="verified":
                continue
            item={"path":ref["path"],"line":ref["line"],
                  "consumer_symbol":ref.get("consumer_symbol"),
                  "via_symbol":symbol,"depth":level,
                  "resolution":"verified","impact_confidence":"potential"}
            if item not in expanded:
                expanded.append(item)
            if len(expanded)>=limit:
                break
            if level<depth and ref.get("consumer_symbol"):
                frontier.append((ref["consumer_symbol"],ref["path"],level+1))
    result["transitive_consumers"]=expanded
    result["ambiguous_traversal"]=ambiguous
    result["traversal_truncated"]=bool(frontier)
    result["affected_files"]=sorted(set(result["direct_affected_files"]) |
                                    {x["path"] for x in expanded})
    result["note"]="Impact is potential, not proof of runtime effect. Only uniquely bound verified references propagate; dynamic dispatch is not inferred."
    return result
