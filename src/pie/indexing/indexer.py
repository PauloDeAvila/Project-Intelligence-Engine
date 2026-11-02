import ast
import json
from pathlib import Path

from pie.indexing.python_ast import parse_python_content
from pie.scanning.discovery import iter_files
from pie.storage import analysis as symbol_store
from pie.storage.database import connect


def _store_scan_result(connection, state: str, diagnostics: list[dict[str, str | int]]) -> None:
    values = {
        "index_state": state,
        "index_diagnostics": json.dumps(diagnostics, ensure_ascii=False, sort_keys=True),
    }
    connection.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        values.items(),
    )



def _refresh_symbol_documents(connection, file_id: int, content: bytes) -> None:
    """Persist bounded AST descriptions for symbols of one file.

    Called for changed sources and for old databases lacking the summary index.
    Everything is derived from the same source snapshot as the symbol index.
    """
    try:
        source = content.decode("utf-8-sig")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return
    lines = source.splitlines()
    descriptions = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            descriptions[node.lineno] = (ast.get_docstring(node) or "").split("\n", 1)[0][:400]
    symbols = connection.execute(
        "SELECT id,start_line FROM symbols WHERE file_id = ?", (file_id,)
    ).fetchall()
    connection.executemany(
        "INSERT OR REPLACE INTO symbol_docs(symbol_id, summary, signature) VALUES (?,?,?)",
        ((row["id"], descriptions.get(row["start_line"], ""),
          lines[row["start_line"]-1].strip()[:250] if 1 <= row["start_line"] <= len(lines) else "")
         for row in symbols)
    )

def index_project(root: Path) -> dict[str, object]:
    db_path = root / ".pie" / "index.sqlite3"
    unreadable_paths: set[Path] = set()
    unreadable_directories: set[Path] = set()
    oversized_paths: set[Path] = set()
    records = iter_files(
        root,
        unreadable_paths=unreadable_paths,
        unreadable_directories=unreadable_directories,
        oversized_paths=oversized_paths,
    )
    connection = connect(db_path)
    try:
        with connection:
            existing_paths = {
                row["path"] for row in connection.execute("SELECT path FROM files").fetchall()
            }
            seen: set[str] = set()
            changed: set[str] = set()
            removed: set[str] = set()
            for record in records:
                relative = str(record.path).replace("\\", "/")
                seen.add(relative)
                row = connection.execute("SELECT id, sha256 FROM files WHERE path = ?", (relative,)).fetchone()
                if row and row["sha256"] == record.sha256:
                    missing = connection.execute(
                        "SELECT 1 FROM symbols s LEFT JOIN symbol_docs d ON d.symbol_id=s.id "
                        "WHERE s.file_id=? AND d.symbol_id IS NULL LIMIT 1", (row["id"],)
                    ).fetchone()
                    if missing:
                        _refresh_symbol_documents(connection, row["id"], record.content)
                    continue
                if row:
                    # Deleting the file row cascades to definitions, usages, star
                    # imports and analysis state; nothing stale can survive it.
                    connection.execute("DELETE FROM files WHERE id = ?", (row["id"],))
                changed.add(relative)
                symbols, imports, parse_error = parse_python_content(record.content, relative)
                cursor = connection.execute("INSERT INTO files(path, sha256, size, language, parse_status) VALUES (?, ?, ?, ?, ?)", (relative, record.sha256, record.size, record.language, "error:" + parse_error if parse_error else "parsed"))
                for symbol in symbols:
                    connection.execute("INSERT INTO symbols(file_id, qualified_name, name, kind, start_line, end_line, start_col, end_col) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (cursor.lastrowid, symbol.qualified_name, symbol.name, symbol.kind, symbol.start_line, symbol.end_line, symbol.start_col, symbol.end_col))
                _refresh_symbol_documents(connection, cursor.lastrowid, record.content)
                for item in imports:
                    connection.execute("INSERT INTO imports(file_id, module, imported_name, alias, line) VALUES (?, ?, ?, ?, ?)", (cursor.lastrowid, item.module, item.imported_name, item.alias, item.line))
            failed_paths = unreadable_paths | oversized_paths
            failed_path_strings = {path.as_posix() for path in failed_paths}
            root_scan_failed = Path(".") in unreadable_directories
            stale_paths = {
                old_path
                for old_path in existing_paths
                if old_path in failed_path_strings
                or any(
                    old_path.startswith(directory.as_posix().rstrip("/") + "/")
                    for directory in unreadable_directories
                    if directory != Path(".")
                )
                or root_scan_failed
            }
            for old_path in existing_paths:
                if root_scan_failed or old_path in seen or any(
                    old_path == directory.as_posix() or old_path.startswith(directory.as_posix().rstrip("/") + "/")
                    for directory in unreadable_directories
                ) or old_path in failed_path_strings:
                    continue
                connection.execute("DELETE FROM files WHERE path = ?", (old_path,))
                if old_path.endswith(".py"):
                    removed.add(old_path)
            parse_errors = [
                (row["path"], row["parse_status"].removeprefix("error:"))
                for row in connection.execute(
                    "SELECT path, parse_status FROM files WHERE parse_status LIKE 'error:%' ORDER BY path"
                )
            ]
            omissions = bool(failed_paths or unreadable_directories or parse_errors)
            has_unindexed_omissions = bool(unreadable_directories or parse_errors) or any(
                path.as_posix() not in existing_paths for path in failed_paths
            )
            state = "CURRENT" if not omissions else "PARTIAL" if has_unindexed_omissions else "STALE"
            diagnostics: list[dict[str, str | int]] = []
            diagnostics.extend(
                {"code": "file_unreadable", "path": path.as_posix()}
                for path in sorted(unreadable_paths, key=lambda item: item.as_posix())
            )
            diagnostics.extend(
                {"code": "file_exceeds_size_limit", "path": path.as_posix()}
                for path in sorted(oversized_paths, key=lambda item: item.as_posix())
            )
            if failed_paths:
                diagnostics.append({"code": "files_not_processed", "count": len(failed_paths)})
            diagnostics.extend(
                {"code": "directory_unreadable", "path": path.as_posix()}
                for path in sorted(unreadable_directories, key=lambda item: item.as_posix())
            )
            diagnostics.extend(
                {"code": "parse_error", "path": path, "error": error}
                for path, error in parse_errors
            )
            if stale_paths:
                diagnostics.append({"code": "preserved_stale_files", "count": len(stale_paths)})
            analysis_report = symbol_store.refresh(connection, changed, removed, root)
            analysis_failures = analysis_report.get("unreadable") or []
            if analysis_failures:
                diagnostics.extend(
                    {"code": "analysis_source_unreadable", "path": path}
                    for path in sorted(analysis_failures)
                )
                # The symbol layer is incomplete even when every file was scanned:
                # its rows were dropped, so a query must not read as a clean index.
                if state == "CURRENT":
                    state = "PARTIAL"
            _store_scan_result(connection, state, diagnostics)
            connection.execute("INSERT INTO metadata(key, value) VALUES('root', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(root.resolve()),))
    except Exception as exc:
        try:
            with connection:
                _store_scan_result(
                    connection,
                    "ERROR",
                    [{"code": "indexing_failed", "message": f"{type(exc).__name__}: {exc}"}],
                )
        except Exception as status_error:
            exc.add_note(f"Could not persist ERROR index state: {type(status_error).__name__}: {status_error}")
        raise
    finally:
        connection.close()
    connection = connect(db_path)
    try:
        metadata = {row["key"]: row["value"] for row in connection.execute("SELECT key, value FROM metadata")}
        return {
            "files": connection.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            "symbols": connection.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
            "imports": connection.execute("SELECT COUNT(*) FROM imports").fetchone()[0],
            "definitions": connection.execute("SELECT COUNT(*) FROM definitions").fetchone()[0],
            "references": connection.execute("SELECT COUNT(*) FROM usages").fetchone()[0],
            "database": str(db_path),
            "index_state": metadata.get("index_state", "UNINDEXED"),
            "diagnostics": json.loads(metadata.get("index_diagnostics", "[]")),
        }
    finally:
        connection.close()
