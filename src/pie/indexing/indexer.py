from pathlib import Path

from pie.indexing.python_ast import parse_python
from pie.scanning.discovery import discover_files
from pie.storage.database import connect


def index_project(root: Path) -> dict[str, int | str]:
    db_path = root / ".pie" / "index.sqlite3"
    records = discover_files(root)
    connection = connect(db_path)
    try:
        with connection:
            seen = {str(record.path) for record in records}
            if seen:
                placeholders = ",".join("?" for _ in seen)
                connection.execute(f"DELETE FROM files WHERE path NOT IN ({placeholders})", tuple(seen))
            else:
                connection.execute("DELETE FROM files")
            for record in records:
                relative = str(record.path).replace("\\", "/")
                row = connection.execute("SELECT id, sha256 FROM files WHERE path = ?", (relative,)).fetchone()
                if row and row["sha256"] == record.sha256:
                    continue
                if row:
                    connection.execute("DELETE FROM files WHERE id = ?", (row["id"],))
                symbols, imports, parse_error = parse_python(root / record.path, relative)
                cursor = connection.execute("INSERT INTO files(path, sha256, size, language, parse_status) VALUES (?, ?, ?, ?, ?)", (relative, record.sha256, record.size, record.language, "error:" + parse_error if parse_error else "parsed"))
                for symbol in symbols:
                    connection.execute("INSERT INTO symbols(file_id, qualified_name, name, kind, start_line, end_line, start_col, end_col) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (cursor.lastrowid, symbol.qualified_name, symbol.name, symbol.kind, symbol.start_line, symbol.end_line, symbol.start_col, symbol.end_col))
                for item in imports:
                    connection.execute("INSERT INTO imports(file_id, module, imported_name, alias, line) VALUES (?, ?, ?, ?, ?)", (cursor.lastrowid, item.module, item.imported_name, item.alias, item.line))
            connection.execute("INSERT INTO metadata(key, value) VALUES('root', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(root.resolve()),))
    finally:
        connection.close()
    connection = connect(db_path)
    try:
        return {"files": connection.execute("SELECT COUNT(*) FROM files").fetchone()[0], "symbols": connection.execute("SELECT COUNT(*) FROM symbols").fetchone()[0], "imports": connection.execute("SELECT COUNT(*) FROM imports").fetchone()[0], "database": str(db_path)}
    finally:
        connection.close()

