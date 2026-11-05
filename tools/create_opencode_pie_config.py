"""Generate an isolated OpenCode runtime config (current 2.x schema) for the PIE stdio MCP.

This tool never edits the user's OpenCode global configuration or workspace.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def make_config(root: Path, python: Path) -> dict:
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("PIE root must be an existing absolute directory")
    if not python.is_absolute() or not python.is_file():
        raise ValueError("Python executable must exist at an absolute path")
    root, python = root.resolve(strict=True), python.resolve(strict=True)
    def rule(action: str, effect: str) -> dict[str, str]:
        return {"action": action, "resource": "*", "effect": effect}

    return {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "servers": {
                "pie": {
                    "type": "local",
                    "command": [str(python), "-m", "pie.interfaces.mcp_server", "--root", str(root)],
                    "cwd": str(root),
                    "codemode": False,
                    "protocol": "legacy",
                    "timeout": 120000
                }
            }
        },
        "permissions": [
            rule("shell", "deny"),
            rule("edit", "deny"),
            rule("subagent", "deny"),
            rule("webfetch", "deny"),
            rule("websearch", "deny"),
            rule("external_directory", "deny"),
            rule("execute", "deny"),
            rule("pie_*", "deny"),
            rule("pie_project_status", "allow"),
            rule("pie_pie_project_status", "allow")
        ]
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    config = make_config(args.root, args.python)
    output = args.output.expanduser()
    if output.exists():
        parser.error("Output exists; refuse to replace an existing OpenCode config")
    if output.resolve() == (args.root / "opencode.json").resolve():
        parser.error("Refusing to modify an existing workspace config via this tool")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(config, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Generated private OpenCode config: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
