"""Token-conscious evidence presentation with fail-closed source verification.

Avoid structured JSON overhead for tiny projects; use exact source bytes if
that is cheaper. For large projects use minimal source citations and optional
implementation bodies. Cost is explicitly measured in UTF-8 bytes/chars, not
claimed provider tokens.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from pie.retrieval.intelligence import smart_context
from pie.storage.database import connect


def adaptive_context(root: Path, query: str, *, max_chars: int = 12000,
                     limit: int = 8, mode: str = "navigation",
                     full_source_path: str | None = None) -> dict[str, object]:
    """Select smallest *sufficient available* presentation, never stale bytes.

    'navigation' supplies symbol map, 'edit' supplies code bodies.
    A caller can nominate the conventional full-source comparison path;
    it is selected only if shorter than the compact candidate and indexed-current.
    """
    if mode not in ("navigation", "edit"):
        raise ValueError("mode must be navigation or edit")
    if not 500 <= max_chars <= 200000 or not 1 <= limit <= 100:
        raise ValueError("invalid context limits")
    root = Path(root).resolve()
    indexed = smart_context(root, query, max_chars=max_chars, limit=limit,
                            include_body=(mode == "edit"))
    candidates = indexed["evidence"]
    # Keep citations and required implementation bodies, remove duplicated
    # scores, descriptions, range metadata and verification chatter.
    fragments = []
    for item in candidates:
        citation = f'{item["path"]}:{item["start_line"]} [{item["symbol"]}]'
        if mode == "edit":
            fragments.append(citation + "\n" + item.get("content", ""))
        else:
            fragments.append(citation + " " + item["signature"])
    compact = "\n\n".join(fragments)
    chosen = "compact"
    payload = compact
    if full_source_path is not None:
        candidate = (root / full_source_path).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file() or candidate.is_symlink():
            raise ValueError("full_source_path is not a regular project file")
        db = root / ".pie" / "index.sqlite3"
        conn = connect(db)
        try:
            row = conn.execute("SELECT sha256 FROM files WHERE path=?", (
                candidate.relative_to(root).as_posix(),)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise ValueError("full source is not indexed")
        raw = candidate.read_bytes()
        if sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("full source changed after indexing; run pie index")
        # Preserve raw bytes for SHA-256 verification, but present normalized text.
        # This matches Path.read_text() and smart_context() on Windows.
        full = raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        if len(full) <= max_chars and (not compact or len(full) <= len(compact)):
            chosen, payload = "full_source", full
    if not payload and indexed["context_state"] == "CURRENT":
        status = "NO_MATCH"
    else:
        status = indexed["context_state"]
    # Budget source bytes by exactly the same metric as the field below.
    # Never truncate code mid-function. Remove low-ranked fragments instead.
    if chosen == "compact":
        while len(payload) > max_chars and fragments:
            fragments.pop()
            payload = "\n\n".join(fragments)
            if status == "CURRENT":
                status = "PARTIAL"
    return {
        "query": query,
        "mode": mode,
        "representation": chosen,
        "context_state": status,
        "content": payload,
        "context_characters": len(payload),
        "candidate_count": len(candidates),
        "note": "Character budget, not measured tokens; context is hash-verified",
    }
