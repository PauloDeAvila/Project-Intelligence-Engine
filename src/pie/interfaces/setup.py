"""Per-project PIE provisioning and MCP client registration.

No remote accounts, shell invocation, or global config modifications.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from pie.indexing.indexer import index_project
from pie.interfaces.cli import command_init


def _project(path: Path) -> Path:
    if path.is_symlink():
        raise ValueError("Project root must not be a symbolic link")
    root = path.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Project root must be a directory")
    return root


def _identifier(root: Path) -> str:
    # Stable per-project identifier; independent indexes remain inside each root.
    return "pie-" + sha256(str(root.resolve()).encode("utf8")).hexdigest()[:10]


def _write_json_config(path: Path, key: str, name: str, entry: dict) -> str:
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf8"))
        if not isinstance(existing, dict):
            raise ValueError(f"Invalid config object: {path}")
    else:
        existing = {}
    servers = existing.setdefault(key, {})
    if not isinstance(servers, dict):
        raise ValueError(f"Invalid {key} field: {path}")
    if name in servers:
        if servers[name] == entry:
            return "unchanged"
        raise ValueError(f"Existing MCP registration conflicts: {path} ({name})")
    servers[name] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    return "created"


def _write_codex(path: Path, name: str, python: Path, root: Path,
                 tool_profile: str = "full") -> str:
    section_name = f"mcp_servers.{name}"
    mcp_args = ["-m", "pie.interfaces.mcp_server", "--root", str(root)]
    if tool_profile == "compact":
        mcp_args += ["--tool-profile", "compact"]
    old = path.read_text(encoding="utf8") if path.exists() else ""
    if re.search(r"(?m)^\s*\[" + re.escape(section_name) + r"\]\s*$", old):
        import tomllib
        data = tomllib.loads(old)
        actual = data.get("mcp_servers", {}).get(name, {})
        expected = {
            "command": str(python),
            "args": mcp_args
        }
        if all(actual.get(k) == v for k, v in expected.items()):
            return "unchanged"
        raise ValueError(f"Existing Codex registration conflicts: {path} ({name})")
    # Parse before modifying: never corrupt unrelated Codex settings.
    if old.strip():
        import tomllib
        tomllib.loads(old)
    section = (
        f"\n[{section_name}]\n"
        + "command = " + json.dumps(str(python)) + "\n"
        + "args = " + json.dumps(mcp_args) + "\n"
        + "startup_timeout_sec = 120\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(old.rstrip("\n") + "\n" + section if old else section.lstrip("\n"), encoding="utf8")
    return "created"


def provision(root: Path, *, python: Path | None = None,
              clients: tuple[str, ...] = ("vscode", "codex", "claude", "cursor"),
              tool_profile: str = "full") -> dict:
    root = _project(root)
    python = (python or Path(sys.executable)).resolve(strict=True)
    if not python.is_file():
        raise ValueError("Python interpreter was not found")
    invalid = set(clients) - {"vscode", "codex", "claude", "cursor"}
    if invalid:
        raise ValueError(f"Unsupported clients: {sorted(invalid)}")
    if tool_profile not in ("full", "compact"):
        raise ValueError("Unsupported MCP tool profile")
    # Initialize and index before touching client configuration.
    if not (root / ".pie" / "index.sqlite3").is_file():
        command_init(root)
    index = index_project(root)
    if index["index_state"] != "CURRENT":
        raise RuntimeError("Cannot provision MCP with incomplete index: " +
                           str(index.get("diagnostics", [])))
    name = _identifier(root)
    args = ["-m", "pie.interfaces.mcp_server", "--root", str(root)]
    if tool_profile == "compact":
        args += ["--tool-profile", "compact"]
    operations: dict[str, dict] = {}
    if "vscode" in clients:
        path = root / ".vscode" / "mcp.json"
        status = _write_json_config(path, "servers", name,
                                    {"type": "stdio", "command": str(python), "args": args})
        operations["vscode"] = {"file": str(path), "status": status}
    if "codex" in clients:
        path = root / ".codex" / "config.toml"
        status = _write_codex(path, name, python, root, tool_profile)
        operations["codex"] = {"file": str(path), "status": status}
    if "claude" in clients:
        # Claude Code project scope, also recognized by portable Copilot configs.
        path = root / ".mcp.json"
        status = _write_json_config(path, "mcpServers", name,
                                    {"command": str(python), "args": args})
        operations["claude"] = {"file": str(path), "status": status}
    if "cursor" in clients:
        path = root / ".cursor" / "mcp.json"
        status = _write_json_config(path, "mcpServers", name,
                                    {"command": str(python), "args": args})
        operations["cursor"] = {"file": str(path), "status": status}
    return {"root": str(root), "server_id": name, "index_state": index["index_state"],
            "database": str(root / ".pie" / "index.sqlite3"), "clients": operations}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize PIE and register project-scoped MCP servers")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--tool-profile", choices=("full", "compact"), default="full")
    parser.add_argument("--clients", nargs="+", choices=("vscode", "codex", "claude", "cursor"),
                        default=["vscode", "codex", "claude", "cursor"])
    args = parser.parse_args(argv)
    try:
        report = provision(args.project, python=args.python, clients=tuple(args.clients),
                           tool_profile=args.tool_profile)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"PIE setup failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
