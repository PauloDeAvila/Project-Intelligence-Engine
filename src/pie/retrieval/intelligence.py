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
    """Rank responsibilities using names, file paths, signatures and docstrings.

    Every returned source range is verified against the indexed SHA-256.
    Entire JSON output is bounded by max_chars; no stale snippets are emitted.
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
        rows = conn.execute("""SELECT s.name,s.qualified_name,s.kind,s.start_line,s.end_line,
                                      f.path,f.sha256
                               FROM symbols s JOIN files f ON s.file_id=f.id
                               ORDER BY f.path,s.start_line""").fetchall()
        query_words = _query_terms(query)
        candidates = []
        diagnostics = []
        cached: dict[str, tuple[list[str], str] | None] = {}
        descriptions: dict[tuple[str,int], str] = {}
        for row in rows:
            path = row["path"]
            if path not in cached:
                try:
                    data = (root / path).read_bytes()
                    if sha256(data).hexdigest() != row["sha256"]:
                        raise ValueError("source_hash_mismatch")
                    decoded = data.decode("utf-8-sig", errors="replace")
                    cached[path] = (decoded.splitlines(), decoded)
                    try:
                        tree = ast.parse(decoded)
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                                descriptions[(path,node.lineno)] = (ast.get_docstring(node) or "").split("\n",1)[0][:400]
                    except SyntaxError:
                        pass
                except (OSError, ValueError) as exc:
                    cached[path] = None
                    diagnostics.append({"path":path,"code":"source_hash_mismatch" if isinstance(exc, ValueError) else "file_unreadable"})
            entry = cached[path]
            if entry is None:
                continue
            lines, source = entry
            if row["start_line"] < 1 or row["end_line"] > len(lines):
                continue
            name_words = _terms(row["qualified_name"])
            path_words = _terms(path.replace("/", " "))
            # Only parse docstrings for name/path candidates OR queries which otherwise
            # have no lexical candidates; computing all docstrings is a bounded local cost.
            description = descriptions.get((path,row["start_line"]), "")
            desc_words = _terms(description)
            score = 8 * len(query_words & name_words) + 4 * len(query_words & path_words) + 3 * len(query_words & desc_words)
            if row["name"].lower() == query.strip().lower():
                score += 25
            if score <= 0:
                continue
            start, end = row["start_line"], row["end_line"]
            signature = lines[start - 1].strip()
            candidate = {"symbol":row["qualified_name"],"path":path,"start_line":start,
                         "end_line":end,"kind":row["kind"],"score":score,
                         "signature":signature[:250],"description":description}
            if include_body:
                candidate["content"] = "\n".join(lines[start - 1:end])
            candidates.append(candidate)
        candidates.sort(key=lambda r:(-r["score"],r["path"],r["start_line"]))
        selected = candidates[:limit]
        result = {"query":query,"index_state":index_state,"context_state":index_state,
                  "evidence":selected,"omitted":max(0,len(candidates)-len(selected)),
                  "diagnostics":diagnostics,
                  "method":"deterministic_lexical_docstring_v1",
                  "note":"Ranking is heuristic; no semantic correctness guarantee."}
        if diagnostics and result["context_state"] == "CURRENT":
            result["context_state"] = "STALE"
        while len(json.dumps(result,ensure_ascii=False)) > max_chars:
            if result["evidence"]:
                result["evidence"].pop()
                result["omitted"] += 1
                if result["context_state"] == "CURRENT":
                    result["context_state"] = "PARTIAL"
            elif result["diagnostics"]:
                result["diagnostics"].pop()
            else:
                raise ValueError("Metadata exceeds max_chars")
        return result
    finally:
        conn.close()

def impact(root: Path, name: str, *, limit: int = 100) -> dict[str, object]:
    """Reverse consumer evidence, never guessing unresolved edges."""
    from pie.retrieval.symbols import find_references
    result = find_references(Path(root), name, limit=limit)
    refs = result.get("references", [])
    result["affected_files"] = sorted({item["path"] for item in refs})
    result["verified_references"] = sum(item.get("resolution") == "verified" for item in refs)
    result["unresolved_references"] = len(refs) - result["verified_references"]
    result["note"] = "Potential impact, not proof of runtime effect; dynamic calls may be absent"
    return result
