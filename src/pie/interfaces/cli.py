import argparse
import json
import time
from pathlib import Path

from pie import __version__
from pie.core.errors import ProjectNotInitializedError
from pie.indexing.indexer import index_project
from pie.retrieval.symbols import analysis_summary, find_definitions, find_references
from pie.storage.database import connect
from pie.retrieval.intelligence import smart_context, impact
from pie.retrieval.glossary import remember, recall


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
    smart = subparsers.add_parser("context")
    smart.add_argument("query")
    smart.add_argument("--root", default=".")
    smart.add_argument("--max-chars", type=int, default=12000)
    smart.add_argument("--limit", type=int, default=8)
    smart.add_argument("--include-body", action="store_true")
    watch_cmd = subparsers.add_parser("watch")
    watch_cmd.add_argument("--root", default=".")
    watch_cmd.add_argument("--interval", type=float, default=5.0)
    watch_cmd.add_argument("--iterations", type=int, default=0,
                           help="0 means run until Ctrl+C")
    impacts = subparsers.add_parser("impact")
    impacts.add_argument("name")
    impacts.add_argument("--root", default=".")
    memory = subparsers.add_parser("remember")
    memory.add_argument("key")
    memory.add_argument("description")
    memory.add_argument("--source", required=True)
    memory.add_argument("--root", default=".")
    recall_cmd = subparsers.add_parser("recall")
    recall_cmd.add_argument("query", nargs="?", default="")
    recall_cmd.add_argument("--root", default=".")
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
        elif args.command == "context": result = smart_context(root, args.query, max_chars=args.max_chars, limit=args.limit, include_body=args.include_body)
        elif args.command == "watch":
            if args.interval < 0.1 or args.iterations < 0:
                parser.error("watch interval must be >=0.1 and iterations >=0")
            checks=0
            try:
                while not args.iterations or checks < args.iterations:
                    update=index_project(root)
                    if checks == 0 or update.get("changed_files") or update.get("removed_files") or update["index_state"] != "CURRENT":
                        print(json.dumps({"event":"index_update","iteration":checks,**update},
                                         ensure_ascii=False),flush=True)
                    checks += 1
                    if not args.iterations or checks < args.iterations:
                        time.sleep(args.interval)
            except KeyboardInterrupt:
                pass
            return 0
        elif args.command == "impact": result = impact(root, args.name)
        elif args.command == "remember": result = remember(root, args.key, args.description, args.source)
        elif args.command == "recall": result = recall(root, args.query)
        else: result = command_symbol(root, args.name)
    except ProjectNotInitializedError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

