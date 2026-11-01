"""Register PIE's first-run MCP server in a project's Codex config."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    project = args.project.resolve()
    if not project.is_dir():
        parser.error("Project directory not found: " + str(project))
    runner = Path(__file__).resolve().with_name("pie_mcp_bootstrap.py")
    config = project / ".codex" / "config.toml"
    if config.exists():
        current = config.read_text(encoding="utf-8")
        if "[mcp_servers.pie]" in current:
            print("PIE already registered in " + str(config))
            return 0
    else:
        current = ""
    section = (
        "\n[mcp_servers.pie]\n"
        + "command = " + json.dumps(str(args.python.resolve())) + "\n"
        + "args = [" + ", ".join(json.dumps(v) for v in (str(runner), "--root", str(project))) + "]\n"
        + "startup_timeout_sec = 120\n"
    )
    config.parent.mkdir(parents=True, exist_ok=True)
    with config.open("a", encoding="utf-8") as file:
        file.write(section)
    print("PIE MCP registered: " + str(config))
    print("Restart the Codex session to load the MCP server.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
