"""Queries over the stored symbol intelligence: definitions, references, consumers.

Both directions are first-class because they answer different questions:
``definition of X`` is a forward lookup on ``definitions``, ``who uses X`` is a
reverse lookup on ``usages.target_binding_key``.  Neither walks the AST, so a
query costs one indexed SQL statement regardless of project size.
"""
from __future__ import annotations

import json
from pathlib import Path

from pie.storage.database import connect

MAX_RESULTS = 500


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


def find_definitions(root: Path, name: str, limit: int = 100) -> dict[str, object]:
    """Every definition site of ``name`` (exact name, exact qualified name or suffix)."""
    if not name.strip():
        raise ValueError("name cannot be empty")
    if not 1 <= limit <= MAX_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_RESULTS}")
    connection = connect(Path(root).resolve() / ".pie" / "index.sqlite3")
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
        return {"query": name, "definitions": [_definition_row(row) for row in rows]}
    finally:
        connection.close()


def find_references(root: Path, name: str, limit: int = 100) -> dict[str, object]:
    """Consumers of ``name``: every usage whose target is one of its definitions.

    This is the reverse query.  It answers "if I change this, what reads it",
    which is impossible from an outgoing-only graph.
    """
    if not name.strip():
        raise ValueError("name cannot be empty")
    if not 1 <= limit <= MAX_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_RESULTS}")
    connection = connect(Path(root).resolve() / ".pie" / "index.sqlite3")
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
            "SELECT u.name, u.qualified_name, u.scope_key, u.context, u.line, u.col, u.origin_symbol, "
            "u.resolution, u.evidence, u.target_binding_key, u.target_path, u.target_line, u.via_binding_key, "
            "f.path "
            "FROM usages u JOIN files f ON f.id = u.file_id "
            f"WHERE u.target_binding_key IN ({placeholders}) "
            "ORDER BY f.path, u.line, u.col LIMIT ?",
            (*keys, limit),
        ).fetchall()
        return {
            "query": name,
            "definitions": [_definition_row(row) for row in targets],
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
                for row in rows
            ],
            "count": len(rows),
        }
    finally:
        connection.close()


def describe_binding(root: Path, binding_key: str, limit: int = 100) -> dict[str, object]:
    """Full report for one binding: sites, readers and writers, grouped by file."""
    connection = connect(Path(root).resolve() / ".pie" / "index.sqlite3")
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
            "SELECT u.name, u.qualified_name, u.context, u.scope_key, u.line, u.col, u.origin_symbol, "
            "u.resolution, u.evidence, u.via_binding_key, f.path "
            "FROM usages u JOIN files f ON f.id = u.file_id "
            "WHERE u.target_binding_key = ? ORDER BY f.path, u.line, u.col LIMIT ?",
            (binding_key, limit),
        ).fetchall()
        consumers = sorted({row["path"] for row in rows})
        symbols = sorted({row["origin_symbol"] for row in rows if row["origin_symbol"]})
        return {
            "binding": binding_key,
            "definitions": [_definition_row(row) for row in definitions],
            "references": [dict(row) for row in rows],
            "consumers": {"files": consumers, "symbols": symbols},
            "unresolved_references": sum(1 for row in rows if row["resolution"] == "unresolved"),
        }
    finally:
        connection.close()


def analysis_summary(root: Path) -> dict[str, object]:
    """Counts by kind and resolution, for a quick integrity check."""
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
        return {
            "definitions": sum(kinds.values()),
            "references": sum(resolutions.values()),
            "definitions_by_kind": kinds,
            "references_by_resolution": resolutions,
            "references_by_context": contexts,
            "dangling_targets": orphans,
        }
    finally:
        connection.close()


def dumps(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)