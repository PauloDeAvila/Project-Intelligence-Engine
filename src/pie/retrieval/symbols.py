"""Queries over the stored symbol intelligence: definitions, references, consumers.

Both directions are first-class because they answer different questions:
``definition of X`` is a forward lookup on ``definitions``, ``who uses X`` is a
reverse lookup on ``usages.target_binding_key``.  Neither walks the AST, so a
query costs one indexed SQL statement regardless of project size.

Analysis rows are *derived* data.  Once a source file changes, the stored line
numbers and resolution verdicts describe bytes that no longer exist.  Every row is
therefore hash-verified against the file on disk before it is returned, and rows
whose source drifted are excluded and reported.  A caller can never read a stale
``verified`` as fact: it either gets evidence that still matches the source, or an
explicit ``STALE`` state telling it to re-index.
"""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from pie.storage.analysis import analysis_version_matches
from pie.storage.database import connect

MAX_RESULTS = 500

#: The answer still matches the bytes on disk.
CURRENT = "CURRENT"
#: At least one source behind the answer changed, or the stored rules are older.
STALE = "STALE"


def _require_analysis(connection) -> str | None:
    """Return a warning when the analysis layer was never built."""
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='definitions'"
    ).fetchone()
    if row is None:
        return "Run pie index first: the symbol analysis layer does not exist"
    count = connection.execute("SELECT COUNT(*) FROM definitions").fetchone()[0]
    if not count:
        return "The analysis layer is empty; run pie index"
    return None


def _drifted_sources(connection, root: Path, paths: set[str]) -> dict[str, str]:
    """Map each path whose current bytes differ from the index to the reason why.

    Only files that actually back the answer are read, so verification stays
    proportional to the result size instead of the repository size.
    """
    if not paths:
        return {}
    ordered = sorted(paths)
    placeholders = ", ".join("?" * len(ordered))
    expected = {
        row["path"]: row["sha256"]
        for row in connection.execute(
            f"SELECT path, sha256 FROM files WHERE path IN ({placeholders})", tuple(ordered)
        )
    }
    drift: dict[str, str] = {}
    for path in ordered:
        digest = expected.get(path)
        if digest is None:
            drift[path] = "missing_from_index"
            continue
        try:
            content = (root / path).read_bytes()
        except OSError:
            drift[path] = "file_unreadable"
            continue
        if sha256(content).hexdigest() != digest:
            drift[path] = "source_hash_mismatch"
    return drift


def _verification(
    connection,
    checked: int,
    drift: dict[str, str],
    incomplete: bool = False,
) -> dict[str, object]:
    """How far this answer can be trusted *right now*, independent of its content.

    ``incomplete`` covers the case where no single file is drifted but some Python
    files were never analysed at all: the answer is a subset of the project, so it
    is not ``CURRENT`` even though every returned row is hash-valid.
    """
    index_state = connection.execute(
        "SELECT value FROM metadata WHERE key = 'index_state'"
    ).fetchone()
    rules_current = analysis_version_matches(connection)
    state = CURRENT if rules_current and not drift and not incomplete and index_state is not None and index_state[0] == CURRENT else STALE
    payload: dict[str, object] = {
        "state": state,
        "index_state": index_state[0] if index_state else "UNINDEXED",
        "checked_sources": checked,
        "drifted_sources": [{"path": path, "reason": reason} for path, reason in sorted(drift.items())],
    }
    if not rules_current:
        payload["warning"] = (
            "the stored analysis was built by different rules; run pie index to rebuild it"
        )
    elif drift:
        payload["warning"] = (
            "sources changed after indexing; their rows were excluded from this answer, run pie index"
        )
    elif incomplete:
        payload["warning"] = (
            "some Python files were never analysed; run pie index to cover the whole project"
        )
    if state != CURRENT and "warning" not in payload:
        payload["warning"] = "project index is not CURRENT; results may be incomplete; run pie index"
    return payload


def _excluded(drift: dict[str, str]) -> list[dict[str, str]]:
    return [{"path": path, "reason": reason} for path, reason in sorted(drift.items())]


def _definition_row(row) -> dict[str, object]:
    return {
        "binding": row["binding_key"],
        "name": row["name"],
        "qualified_name": row["qualified_name"],
        "kind": row["kind"],
        "declared_by": row["declared_by"],
        "scope": row["scope_key"],
        "scope_kind": row["scope_kind"],
        "path": row["path"],
        "line": row["start_line"],
        "column": row["start_col"],
        "end_line": row["end_line"],
        "inferred_type": row["inferred_type"],
        "imported_from": row["source_module"],
        "imported_name": row["source_name"],
        "alias": row["alias"],
    }


DEFINITION_SELECT = """
SELECT d.binding_key, d.name, d.qualified_name, d.kind, d.declared_by, d.scope_key, d.scope_kind,
       d.start_line, d.start_col, d.end_line, d.inferred_type, d.source_module, d.source_name, d.alias,
       f.path
FROM definitions d JOIN files f ON f.id = d.file_id
"""

USAGE_SELECT = """
SELECT u.name, u.qualified_name, u.scope_key, u.context, u.line, u.col, u.origin_symbol,
       u.resolution, u.evidence, u.target_binding_key, u.target_path, u.target_line, u.via_binding_key,
       f.path
FROM usages u JOIN files f ON f.id = u.file_id
"""


def find_definitions(root: Path, name: str, limit: int = 100) -> dict[str, object]:
    """Every definition site of ``name`` (exact name, exact qualified name or suffix)."""
    if not name.strip():
        raise ValueError("name cannot be empty")
    if not 1 <= limit <= MAX_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_RESULTS}")
    root = Path(root).resolve()
    connection = connect(root / ".pie" / "index.sqlite3")
    try:
        warning = _require_analysis(connection)
        if warning:
            return {"query": name, "definitions": [], "warning": warning}
        escaped = name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = connection.execute(
            DEFINITION_SELECT
            + """ WHERE d.name = ? OR d.qualified_name = ?
                  OR d.qualified_name LIKE ? ESCAPE '\\'
                  ORDER BY CASE WHEN d.qualified_name = ? THEN 0
                                WHEN d.name = ? THEN 1 ELSE 2 END,
                           f.path, d.start_line, d.start_col
                  LIMIT ?""",
            (name, name, f"%.{escaped}", name, name, limit),
        ).fetchall()
        drift = _drifted_sources(connection, root, {row["path"] for row in rows})
        kept = [row for row in rows if row["path"] not in drift]
        result: dict[str, object] = {
            "query": name,
            "definitions": [_definition_row(row) for row in kept],
        }
        if drift:
            result["excluded_stale"] = _excluded(drift)
        result.update(_verification(connection, len({row["path"] for row in rows}), drift))
        return result
    finally:
        connection.close()


def find_references(root: Path, name: str, limit: int = 100) -> dict[str, object]:
    """Consumers of ``name``: every usage whose target is one of its definitions.

    This is the reverse query.  It answers "if I change this, what reads it",
    which is impossible from an outgoing-only graph.  A reference is kept only while
    *both* sides still match the index: a consumer whose file changed, or a target
    whose definition file changed, has its evidence dropped rather than re-labelled.
    """
    if not name.strip():
        raise ValueError("name cannot be empty")
    if not 1 <= limit <= MAX_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_RESULTS}")
    root = Path(root).resolve()
    connection = connect(root / ".pie" / "index.sqlite3")
    try:
        warning = _require_analysis(connection)
        if warning:
            return {"query": name, "references": [], "warning": warning}
        escaped = name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        targets = connection.execute(
            DEFINITION_SELECT + """ WHERE d.name = ? OR d.qualified_name = ?
                                    OR d.qualified_name LIKE ? ESCAPE '\\'""",
            (name, name, f"%.{escaped}"),
        ).fetchall()
        keys = [row["binding_key"] for row in targets]
        if not keys:
            return {"query": name, "references": [], "definitions": []}
        placeholders = ", ".join("?" * len(keys))
        rows = connection.execute(
            USAGE_SELECT + f" WHERE u.target_binding_key IN ({placeholders}) "
            "ORDER BY f.path, u.line, u.col LIMIT ?",
            (*keys, limit),
        ).fetchall()
        drift = _drifted_sources(
            connection,
            root,
            {row["path"] for row in targets} | {row["path"] for row in rows},
        )
        live_keys = {row["binding_key"] for row in targets if row["path"] not in drift}
        kept_targets = [row for row in targets if row["path"] not in drift]
        kept_rows = [
            row
            for row in rows
            if row["path"] not in drift and row["target_binding_key"] in live_keys
        ]
        result: dict[str, object] = {
            "query": name,
            "definitions": [_definition_row(row) for row in kept_targets],
            "references": [
                {
                    "path": row["path"],
                    "line": row["line"],
                    "column": row["col"],
                    "name": row["name"],
                    "context": row["context"],
                    "consumer_scope": row["scope_key"],
                    "consumer_symbol": row["origin_symbol"],
                    "resolution": row["resolution"],
                    "evidence": row["evidence"],
                    "target": row["target_binding_key"],
                    "via_import": row["via_binding_key"],
                }
                for row in kept_rows
            ],
            "count": len(kept_rows),
        }
        if drift:
            result["excluded_stale"] = _excluded(drift)
        result.update(
            _verification(
                connection,
                len({row["path"] for row in targets} | {row["path"] for row in rows}),
                drift,
            )
        )
        return result
    finally:
        connection.close()


def describe_binding(root: Path, binding_key: str, limit: int = 100) -> dict[str, object]:
    """Full report for one binding: sites, readers and writers, grouped by file."""
    root = Path(root).resolve()
    connection = connect(root / ".pie" / "index.sqlite3")
    try:
        warning = _require_analysis(connection)
        if warning:
            return {"binding": binding_key, "warning": warning}
        definitions = connection.execute(
            DEFINITION_SELECT + " WHERE d.binding_key = ? ORDER BY d.start_line",
            (binding_key,),
        ).fetchall()
        if not definitions:
            return {"binding": binding_key, "definitions": [], "references": []}
        rows = connection.execute(
            USAGE_SELECT + " WHERE u.target_binding_key = ? ORDER BY f.path, u.line, u.col LIMIT ?",
            (binding_key, limit),
        ).fetchall()
        drift = _drifted_sources(
            connection,
            root,
            {row["path"] for row in definitions} | {row["path"] for row in rows},
        )
        kept_definitions = [row for row in definitions if row["path"] not in drift]
        kept_rows = [row for row in rows if row["path"] not in drift]
        consumers = sorted({row["path"] for row in kept_rows})
        symbols = sorted({row["origin_symbol"] for row in kept_rows if row["origin_symbol"]})
        result: dict[str, object] = {
            "binding": binding_key,
            "definitions": [_definition_row(row) for row in kept_definitions],
            "references": [dict(row) for row in kept_rows],
            "consumers": {"files": consumers, "symbols": symbols},
            "unresolved_references": sum(1 for row in kept_rows if row["resolution"] == "unresolved"),
        }
        if drift:
            result["excluded_stale"] = _excluded(drift)
        result.update(
            _verification(
                connection,
                len({row["path"] for row in definitions} | {row["path"] for row in rows}),
                drift,
            )
        )
        return result
    finally:
        connection.close()


def analysis_summary(root: Path) -> dict[str, object]:
    """Counts by kind and resolution, for a quick integrity check.

    The counts are aggregate, so they are not hash-verified file by file.  The
    stored rules and the index state are checked instead: both say whether the
    numbers describe the current analysis at all.
    """
    connection = connect(Path(root).resolve() / ".pie" / "index.sqlite3")
    try:
        warning = _require_analysis(connection)
        if warning:
            return {"warning": warning}
        kinds = {
            row["kind"]: row["count"]
            for row in connection.execute(
                "SELECT kind, COUNT(*) AS count FROM definitions GROUP BY kind ORDER BY kind"
            )
        }
        resolutions = {
            row["resolution"]: row["count"]
            for row in connection.execute(
                "SELECT resolution, COUNT(*) AS count FROM usages GROUP BY resolution ORDER BY resolution"
            )
        }
        contexts = {
            row["context"]: row["count"]
            for row in connection.execute(
                "SELECT context, COUNT(*) AS count FROM usages GROUP BY context ORDER BY context"
            )
        }
        orphans = connection.execute(
            "SELECT COUNT(*) FROM usages WHERE target_binding_key IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM definitions d WHERE d.binding_key = usages.target_binding_key)"
        ).fetchone()[0]
        unanalysed = connection.execute(
            "SELECT COUNT(*) FROM files f LEFT JOIN analysis_state a ON a.file_id = f.id "
            "WHERE a.file_id IS NULL AND f.language = 'python'"
        ).fetchone()[0]
        result: dict[str, object] = {
            "definitions": sum(kinds.values()),
            "references": sum(resolutions.values()),
            "definitions_by_kind": kinds,
            "references_by_resolution": resolutions,
            "references_by_context": contexts,
            "dangling_targets": orphans,
            "files_without_analysis": unanalysed,
        }
        result.update(_verification(connection, 0, {}, incomplete=unanalysed > 0))
        return result
    finally:
        connection.close()


def dumps(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)
