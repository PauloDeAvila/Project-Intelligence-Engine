"""Persistence and incremental refresh of the symbol analysis layer (Etapa C).

Analysis rows are *derived* data: the source file is authoritative, so a file
whose hash changed always has its rows replaced.  Cross-module references are the
only part that can go stale while their own file is untouched, therefore every
dependent of a changed module is recomputed with it and a final sweep demotes any
reference whose target no longer exists.

Everything runs inside the indexer transaction: a failed refresh can never leave
half the graph rewritten.
"""
from __future__ import annotations

import ast
import json
import sqlite3
from pathlib import Path

from pie.analysis.definitions import Definition
from pie.analysis.resolver import (
    FILE_SCOPE,
    ModuleAnalysis,
    ModuleFacts,
    Reference,
    Resolver,
    analyze_module,
    dotted_module_names,
)
from pie.analysis.scopes import UNRESOLVED
from pie.storage.database import ANALYSIS_VERSION

#: Evidence written when a stored reference lost its target between two indexes.
STALE_TARGET = "target definition is no longer indexed"

DEFINITION_COLUMNS = (
    "binding_key", "name", "qualified_name", "scope_key", "scope_kind", "kind",
    "declared_by", "start_line", "start_col", "end_line", "end_col",
    "inferred_type", "source_module", "source_name", "alias", "body_scope_key",
)


def definition_to_row(definition: Definition) -> tuple:
    return (
        definition.binding_key, definition.name, definition.qualified_name, definition.scope_key,
        definition.scope_kind, definition.kind, definition.declared_by, definition.line, definition.col,
        definition.end_line, definition.end_col, definition.inferred_type, definition.source_module,
        definition.source_name, definition.alias, definition.body_scope_key,
    )


def row_to_definition(row: sqlite3.Row) -> Definition:
    return Definition(
        binding_key=row["binding_key"],
        path=row["file_path"],
        name=row["name"],
        qualified_name=row["qualified_name"],
        scope_key=row["scope_key"],
        scope_kind=row["scope_kind"],
        kind=row["kind"],
        declared_by=row["declared_by"],
        line=row["start_line"],
        col=row["start_col"],
        end_line=row["end_line"],
        end_col=row["end_col"],
        inferred_type=row["inferred_type"],
        source_module=row["source_module"],
        source_name=row["source_name"],
        alias=row["alias"],
        body_scope_key=row["body_scope_key"],
    )


#: Metadata key holding diagnostics produced while building the analysis layer.
DIAGNOSTICS_KEY = "analysis_diagnostics"


def _record_diagnostic(connection: sqlite3.Connection, diagnostic: dict[str, str]) -> None:
    """Append one analysis diagnostic without losing earlier entries.

    The indexer owns ``index_diagnostics``; keeping the analysis failures in their
    own key means a later scan can report them even when the file list changes.
    """
    row = connection.execute("SELECT value FROM metadata WHERE key = ?", (DIAGNOSTICS_KEY,)).fetchone()
    try:
        existing = json.loads(row[0]) if row else []
    except (ValueError, TypeError):
        existing = []
    if not isinstance(existing, list):
        existing = []
    if diagnostic not in existing:
        existing.append(diagnostic)
    existing.sort(key=lambda item: (item.get("path", ""), item.get("code", "")))
    connection.execute(
        "INSERT INTO metadata(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (DIAGNOSTICS_KEY, json.dumps(existing, ensure_ascii=False, sort_keys=True)),
    )


def take_diagnostics(connection: sqlite3.Connection) -> list[dict[str, str]]:
    """Read and clear the pending analysis diagnostics."""
    row = connection.execute("SELECT value FROM metadata WHERE key = ?", (DIAGNOSTICS_KEY,)).fetchone()
    if row is None:
        return []
    connection.execute("DELETE FROM metadata WHERE key = ?", (DIAGNOSTICS_KEY,))
    try:
        parsed = json.loads(row[0])
    except (ValueError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def clear_file(connection: sqlite3.Connection, file_id: int) -> None:
    for table in ("usages", "definitions", "star_imports", "analysis_state"):
        connection.execute(f"DELETE FROM {table} WHERE file_id = ?", (file_id,))


def mark_analyzed(connection: sqlite3.Connection, file_id: int, sha256: str) -> None:
    connection.execute(
        "INSERT INTO analysis_state(file_id, sha256) VALUES (?, ?) "
        "ON CONFLICT(file_id) DO UPDATE SET sha256 = excluded.sha256",
        (file_id, sha256),
    )


def store_analysis(connection: sqlite3.Connection, file_id: int, analysis: ModuleAnalysis, sha256: str) -> None:
    """Replace definitions and star imports for one file."""
    clear_file(connection, file_id)
    for definition in analysis.definitions:
        connection.execute(
            "INSERT OR IGNORE INTO definitions(file_id, " + ", ".join(DEFINITION_COLUMNS) + ") "
            "VALUES (?, " + ", ".join("?" * len(DEFINITION_COLUMNS)) + ")",
            (file_id, *definition_to_row(definition)),
        )
    for module in sorted(analysis.builder.module.star_imports):
        connection.execute("INSERT OR IGNORE INTO star_imports(file_id, module) VALUES (?, ?)", (file_id, module))
    mark_analyzed(connection, file_id, sha256)


def store_references(connection: sqlite3.Connection, file_id: int, references: list[Reference]) -> None:
    """Replace resolved usages for one file."""
    connection.execute("DELETE FROM usages WHERE file_id = ?", (file_id,))
    for reference in references:
        connection.execute(
            "INSERT OR IGNORE INTO usages(file_id, name, qualified_name, scope_key, context, line, col, "
            "origin_symbol, resolution, evidence, target_binding_key, target_path, target_name, target_line, "
            "via_binding_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                file_id, reference.name, reference.qualified_name, reference.scope_key, reference.context,
                reference.line, reference.col, reference.origin_symbol, reference.resolution, reference.evidence,
                reference.target_binding_key, reference.target_path, reference.target_name,
                reference.target_line, reference.via,
            ),
        )


def load_facts(connection: sqlite3.Connection) -> list[ModuleFacts]:
    """Rebuild module facts from stored definitions without re-reading sources."""
    rows = connection.execute(
        "SELECT d.*, f.path AS file_path FROM definitions d JOIN files f ON f.id = d.file_id "
        "ORDER BY f.path, d.start_line, d.start_col"
    ).fetchall()
    grouped: dict[str, list[Definition]] = {}
    for row in rows:
        grouped.setdefault(row["file_path"], []).append(row_to_definition(row))
    facts: list[ModuleFacts] = []
    for path, definitions in grouped.items():
        module = ModuleFacts(path, dotted_module_names(path))
        for definition in definitions:
            if definition.scope_key == FILE_SCOPE:
                module.module_binding = definition
                continue
            module.definitions.setdefault((definition.scope_key, definition.name), []).append(definition)
        facts.append(module)
    return facts


def dependents_of(connection: sqlite3.Connection, paths: set[str]) -> set[str]:
    """Indexed files importing a module that changed, so their references move."""
    if not paths:
        return set()
    wanted: set[str] = set()
    for path in paths:
        wanted.update(dotted_module_names(path))
    placeholders = ", ".join("?" * len(wanted))
    rows = connection.execute(
        "SELECT DISTINCT f.path FROM imports i JOIN files f ON f.id = i.file_id "
        f"WHERE i.module IN ({placeholders})",
        tuple(wanted),
    ).fetchall()
    return {row["path"] for row in rows if row["path"] not in paths}


def files_missing_analysis(connection: sqlite3.Connection) -> set[str]:
    """Python files with no analysis state - the V0.1/V0.2 migration entry point."""
    rows = connection.execute(
        "SELECT f.path FROM files f LEFT JOIN analysis_state a ON a.file_id = f.id "
        "WHERE a.file_id IS NULL AND f.language = 'python' ORDER BY f.path"
    ).fetchall()
    return {row["path"] for row in rows}


def analysis_version_matches(connection: sqlite3.Connection) -> bool:
    row = connection.execute("SELECT value FROM metadata WHERE key = 'analysis_version'").fetchone()
    return row is not None and row[0] == str(ANALYSIS_VERSION)


def all_python_paths(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT path FROM files WHERE language = 'python'").fetchall()
    return {row["path"] for row in rows}


def demote_stale_targets(connection: sqlite3.Connection) -> int:
    """Downgrade references whose resolved target disappeared from the index.

    A reference keeps its verdict only while the definition it points at exists.
    This sweep is independent of *why* the target vanished, so it also covers
    files that were never re-analysed because their own bytes are unchanged.
    """
    lost = connection.execute(
        "UPDATE usages SET resolution = ?, evidence = ?, target_binding_key = NULL, target_path = NULL, "
        "target_name = NULL, target_line = NULL "
        "WHERE target_binding_key IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM definitions d WHERE d.binding_key = usages.target_binding_key)",
        (UNRESOLVED, STALE_TARGET),
    )
    lost_via = connection.execute(
        "UPDATE usages SET resolution = ?, evidence = ? "
        "WHERE via_binding_key IS NOT NULL AND resolution <> ? AND NOT EXISTS "
        "(SELECT 1 FROM definitions d WHERE d.binding_key = usages.via_binding_key)",
        (UNRESOLVED, STALE_TARGET, UNRESOLVED),
    )
    return lost.rowcount + lost_via.rowcount


def refresh(
    connection: sqlite3.Connection,
    changed: set[str],
    removed: set[str],
    root: Path,
) -> dict[str, int | list[str]]:
    """Re-analyse changed files plus everything that imports them.

    ``unreadable`` lists sources the analysis could not re-read.  Their derived rows
    are dropped and the caller must report the failure: an incomplete analysis layer
    can never be presented as a clean index.
    """
    unreadable: list[str] = []
    seeds = set(changed) | set(removed)
    targets = set(seeds)
    targets |= dependents_of(connection, seeds)
    if analysis_version_matches(connection):
        targets |= files_missing_analysis(connection)
    else:
        # Legacy V0.1/V0.2 database, or the analysis rules changed: rebuild all.
        targets |= all_python_paths(connection)
    targets = {path for path in targets if path.endswith(".py")}
    if not targets:
        return {"analysed": 0, "resolved": 0, "demoted": 0, "unreadable": unreadable}

    analyses: dict[str, ModuleAnalysis] = {}
    for relative in sorted(targets):
        row = connection.execute("SELECT id, sha256 FROM files WHERE path = ?", (relative,)).fetchone()
        if row is None:
            # File gone: its rows already disappeared with the ``files`` cascade.
            continue
        try:
            content = (root / relative).read_bytes()
        except OSError as exc:
            # Derived rows must not survive a source we could not re-read: they would
            # keep claiming a verdict the current bytes no longer support.  Dropping
            # them makes the next query report "no evidence" instead of stale evidence,
            # and the failure is surfaced to the caller as a diagnostic.
            unreadable.append(relative)
            clear_file(connection, row["id"])
            _record_diagnostic(
                connection,
                {"code": "analysis_source_unreadable", "path": relative, "error": f"{type(exc).__name__}: {exc}"},
            )
            continue
        try:
            tree = ast.parse(content.decode("utf-8"), filename=relative)
        except (SyntaxError, UnicodeDecodeError, ValueError):
            # Recorded by the scanner as a parse error; keep the file marked so the
            # next index does not retry it forever.
            clear_file(connection, row["id"])
            mark_analyzed(connection, row["id"], row["sha256"])
            continue
        module = analyze_module(tree, relative)
        store_analysis(connection, row["id"], module, row["sha256"])
        analyses[relative] = module

    if not analyses:
        return {
            "analysed": 0,
            "resolved": 0,
            "demoted": demote_stale_targets(connection),
            "unreadable": unreadable,
        }

    resolver = Resolver(load_facts(connection))
    for relative, module in analyses.items():
        row = connection.execute("SELECT id FROM files WHERE path = ?", (relative,)).fetchone()
        if row is None:
            continue
        store_references(connection, row["id"], resolver.resolve_module(module))
    connection.execute(
        "INSERT INTO metadata(key, value) VALUES('analysis_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(ANALYSIS_VERSION),),
    )
    return {
        "analysed": len(analyses),
        "resolved": connection.execute("SELECT COUNT(*) FROM usages").fetchone()[0],
        "demoted": demote_stale_targets(connection),
        "unreadable": unreadable,
    }