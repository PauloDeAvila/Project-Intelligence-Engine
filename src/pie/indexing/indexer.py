from pathlib import Path

from pie.indexing.python_ast import parse_python_content
from pie.scanning.discovery import iter_files
from pie.storage.database import connect


def index_project(root: Path) -> dict[str, int | str]:
    db_path = root / ".pie" / "index.sqlite3"
    unreadable_paths: set[Path] = set()
    unreadable_directories: set[Path] = set()
    records = iter_files(root, unreadable_paths=unreadable_paths, unreadable_directories=unreadable_directories)
    connection = connect(db_path)
    try:
        with connection:
            seen: set[str] = set()
            for record in records:
                relative = str(record.path).replace("\\", "/")
                seen.add(relative)
                row = connection.execute("SELECT id, sha256 FROM files WHERE path = ?", (relative,)).fetchone()
                if row and row["sha256"] == record.sha256:
                    continue
                if row:
                    connection.execute("DELETE FROM files WHERE id = ?", (row["id"],))
                symbols, imports, parse_error = parse_python_content(record.content, relative)
                cursor = connection.execute("INSERT INTO files(path, sha256, size, language, parse_status) VALUES (?, ?, ?, ?, ?)", (relative, record.sha256, record.size, record.language, "error:" + parse_error if parse_error else "parsed"))
                for symbol in symbols:
                    connection.execute("INSERT INTO symbols(file_id, qualified_name, name, kind, start_line, end_line, start_col, end_col) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (cursor.lastrowid, symbol.qualified_name, symbol.name, symbol.kind, symbol.start_line, symbol.end_line, symbol.start_col, symbol.end_col))
                for item in imports:
                    connection.execute("INSERT INTO imports(file_id, module, imported_name, alias, line) VALUES (?, ?, ?, ?, ?)", (cursor.lastrowid, item.module, item.imported_name, item.alias, item.line))
            preserved = unreadable_paths
            root_scan_failed = Path(".") in unreadable_directories
            existing_paths = connection.execute("SELECT path FROM files").fetchall()
            for existing in existing_paths:
                old_path = existing["path"]
                if root_scan_failed or old_path in seen or any(
                    old_path == directory.as_posix() or old_path.startswith(directory.as_posix().rstrip("/") + "/")
                    for directory in unreadable_directories
                ) or any(old_path == path.as_posix() for path in preserved):
                    continue
                connection.execute("DELETE FROM files WHERE path = ?", (old_path,))
            connection.execute("INSERT INTO metadata(key, value) VALUES('root', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(root.resolve()),))
    finally:
        connection.close()
    connection = connect(db_path)
    try:
        return {"files": connection.execute("SELECT COUNT(*) FROM files").fetchone()[0], "symbols": connection.execute("SELECT COUNT(*) FROM symbols").fetchone()[0], "imports": connection.execute("SELECT COUNT(*) FROM imports").fetchone()[0], "database": str(db_path)}
    finally:
        connection.close()

