import argparse
import json
from pathlib import Path

from pie import __version__
from pie.core.errors import ProjectNotInitializedError
from pie.indexing.indexer import index_project
from pie.retrieval.symbols import analysis_summary, find_definitions, find_references
from pie.storage.database import connect


def project_root(value: str | None) -> Path:
    return Path(value or ".").resolve()


def require_initialized(root: Path) -> Path:
    path = root / ".pie" / "index.sqlite3"
    if not path.exists():
        raise ProjectNotInitializedError(f"Project is not initialized: {root}")
    return path


def command_init(root: Path) -> dict[str, str]:
    path = root / ".pie" / "index.sqlite3"
    connection = connect(path)
    connection.close()
    config = root / ".pie" / "config.toml"
    if not config.exists():
        config.write_text("root = \".\"\n", encoding="utf-8")
    return {"project": str(root), "database": str(path), "status": "initialized"}


def command_status(root: Path) -> dict[str, object]:
    path = require_initialized(root)
    connection = connect(path)
    try:
        metadata = {row["key"]: row["value"] for row in connection.execute("SELECT key, value FROM metadata")}
        return {
            "project": str(root),
            "files": connection.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            "symbols": connection.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
            "imports": connection.execute("SELECT COUNT(*) FROM imports").fetchone()[0],
            "index_state": metadata.get("index_state", "UNINDEXED"),
            "diagnostics": json.loads(metadata.get("index_diagnostics", "[]")),
        }
    finally:
        connection.close()


def command_search(root: Path, query: str) -> list[dict[str, object]]:
    path = require_initialized(root)
    connection = connect(path)
    try:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = connection.execute("SELECT symbols.qualified_name, symbols.name, symbols.kind, files.path, symbols.start_line, symbols.end_line FROM symbols JOIN files ON files.id = symbols.file_id WHERE symbols.name LIKE ? ESCAPE '\\' OR symbols.qualified_name LIKE ? ESCAPE '\\' ORDER BY symbols.qualified_name", (f"%{escaped}%", f"%{escaped}%")).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def command_symbol(root: Path, name: str) -> list[dict[str, object]]:
    path = require_initialized(root)
    connection = connect(path)
    try:
        rows = connection.execute("SELECT symbols.qualified_name, symbols.name, symbols.kind, files.path, symbols.start_line, symbols.end_line, symbols.start_col, symbols.end_col FROM symbols JOIN files ON files.id = symbols.file_id WHERE symbols.qualified_name = ? OR symbols.name = ? ORDER BY files.path, symbols.start_line", (name, name)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def command_definitions(root: Path, name: str) -> dict[str, object]:
    require_initialized(root)
    return find_definitions(root, name)

def command_references(root: Path, name: str) -> dict[str, object]:
    require_initialized(root)
    return find_references(root, name)

def command_analysis(root: Path) -> dict[str, object]:
    require_initialized(root)
    return analysis_summary(root)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pie", description="Local Project Intelligence Engine")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "index", "status"):
        command = subparsers.add_parser(name)
        command.add_argument("--root", default=".")
    for name in ("search", "symbol"):
        command = subparsers.add_parser(name)
        command.add_argument("query" if name == "search" else "name")
        command.add_argument("--root", default=".")
    for name in ("definitions", "references"):
        command = subparsers.add_parser(name)
        command.add_argument("name")
        command.add_argument("--root", default=".")
    subparsers.add_parser("analysis").add_argument("--root", default=".")
    args = parser.parse_args(argv)
    root = project_root(args.root)
    try:
        if args.command == "init": result = command_init(root)
        elif args.command == "index": result = index_project(root) if (root / ".pie" / "index.sqlite3").exists() else command_init(root) | index_project(root)
        elif args.command == "status": result = command_status(root)
        elif args.command == "search": result = command_search(root, args.query)
        elif args.command == "definitions": result = command_definitions(root, args.name)
        elif args.command == "references": result = command_references(root, args.name)
        elif args.command == "analysis": result = command_analysis(root)
        else: result = command_symbol(root, args.name)
    except ProjectNotInitializedError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

