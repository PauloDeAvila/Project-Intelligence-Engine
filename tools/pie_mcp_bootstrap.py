"""Start PIE's stdio MCP server with a fresh project index."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        from pie.interfaces.cli import command_init
        from pie.indexing.indexer import index_project
        from pie.interfaces.mcp_server import main as serve
        if not (root / ".pie" / "index.sqlite3").exists():
            command_init(root)
        report = index_project(root)
        if report["index_state"] != "CURRENT":
            print("PIE index is "+str(report["index_state"])+": "+str(report["diagnostics"]), file=sys.stderr)
    except Exception as exc:
        print("PIE startup failed: "+str(exc), file=sys.stderr)
        return 1
    return serve(["--root", str(root)])

if __name__ == "__main__":
    raise SystemExit(main())
