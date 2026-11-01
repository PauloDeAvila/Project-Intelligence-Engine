import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
    size INTEGER NOT NULL, language TEXT, parse_status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    qualified_name TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
    start_line INTEGER NOT NULL, end_line INTEGER NOT NULL, start_col INTEGER NOT NULL, end_col INTEGER NOT NULL,
    UNIQUE(file_id, qualified_name, kind, start_line, start_col)
);
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    module TEXT NOT NULL, imported_name TEXT, alias TEXT, line INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_qualified_name ON symbols(qualified_name);
"""


def _has_legacy_symbol_constraint(connection: sqlite3.Connection) -> bool:
    for index in connection.execute("PRAGMA index_list(symbols)"):
        if not index["unique"]:
            continue
        index_name = index["name"].replace("'", "''")
        columns = [row["name"] for row in connection.execute(f"PRAGMA index_info('{index_name}')")]
        if columns == ["file_id", "qualified_name", "kind"]:
            return True
    return False


def _migrate_symbol_locations(connection: sqlite3.Connection) -> None:
    if not _has_legacy_symbol_constraint(connection):
        return
    connection.execute("BEGIN IMMEDIATE")
    try:
        # Another process may have migrated while this connection waited for the lock.
        if not _has_legacy_symbol_constraint(connection):
            connection.commit()
            return
        connection.execute(
            "CREATE TABLE symbols_v2 ("
            "id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE, "
            "qualified_name TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, "
            "start_line INTEGER NOT NULL, end_line INTEGER NOT NULL, "
            "start_col INTEGER NOT NULL, end_col INTEGER NOT NULL, "
            "UNIQUE(file_id, qualified_name, kind, start_line, start_col))"
        )
        connection.execute(
            "INSERT INTO symbols_v2(id, file_id, qualified_name, name, kind, start_line, end_line, start_col, end_col) "
            "SELECT id, file_id, qualified_name, name, kind, start_line, end_line, start_col, end_col FROM symbols"
        )
        connection.execute("DROP TABLE symbols")
        connection.execute("ALTER TABLE symbols_v2 RENAME TO symbols")
        connection.execute("CREATE INDEX idx_symbols_name ON symbols(name)")
        connection.execute("CREATE INDEX idx_symbols_qualified_name ON symbols(qualified_name)")
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    _migrate_symbol_locations(connection)
    return connection

