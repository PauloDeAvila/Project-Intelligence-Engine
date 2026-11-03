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
CREATE TABLE IF NOT EXISTS symbol_docs (
    symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
    summary TEXT NOT NULL DEFAULT '',
    signature TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    module TEXT NOT NULL, imported_name TEXT, alias TEXT, line INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_qualified_name ON symbols(qualified_name);
CREATE TABLE IF NOT EXISTS definitions (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    binding_key TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    scope_kind TEXT NOT NULL,
    kind TEXT NOT NULL,
    declared_by TEXT NOT NULL,
    start_line INTEGER NOT NULL, start_col INTEGER NOT NULL,
    end_line INTEGER NOT NULL, end_col INTEGER NOT NULL,
    inferred_type TEXT, source_module TEXT, source_name TEXT, alias TEXT,
    body_scope_key TEXT,
    UNIQUE(file_id, binding_key, start_line, start_col)
);
CREATE TABLE IF NOT EXISTS usages (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    context TEXT NOT NULL,
    line INTEGER NOT NULL, col INTEGER NOT NULL,
    origin_symbol TEXT,
    resolution TEXT NOT NULL,
    evidence TEXT NOT NULL,
    target_binding_key TEXT,
    target_path TEXT, target_name TEXT, target_line INTEGER,
    via_binding_key TEXT,
    UNIQUE(file_id, scope_key, name, context, line, col, qualified_name)
);
CREATE TABLE IF NOT EXISTS star_imports (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    module TEXT NOT NULL,
    UNIQUE(file_id, module)
);
CREATE TABLE IF NOT EXISTS analysis_state (
    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    sha256 TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_definitions_name ON definitions(name);
CREATE INDEX IF NOT EXISTS idx_definitions_binding ON definitions(binding_key);
CREATE INDEX IF NOT EXISTS idx_definitions_qualified ON definitions(qualified_name);
CREATE INDEX IF NOT EXISTS idx_definitions_scope ON definitions(file_id, scope_key, name);
CREATE INDEX IF NOT EXISTS idx_usages_target ON usages(target_binding_key);
CREATE INDEX IF NOT EXISTS idx_usages_target_path ON usages(target_path);
CREATE INDEX IF NOT EXISTS idx_usages_origin ON usages(origin_symbol);
CREATE INDEX IF NOT EXISTS idx_usages_name ON usages(name);
CREATE INDEX IF NOT EXISTS idx_usages_via ON usages(via_binding_key);
CREATE INDEX IF NOT EXISTS idx_star_imports_module ON star_imports(module);
"""

#: Bumped when the analysis layer must be rebuilt from source.
ANALYSIS_VERSION = 3


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
    from pie.retrieval.fts import ensure_fts
    ensure_fts(connection)
    return connection

