"""Fail-closed OpenCode runtime preflight for the isolated PIE MCP workspace.

No inference, session creation, file edits or remote gateway calls.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


def check_contract(config: Any, status: Any, sessions: Any, tools: Any,
                   expected_root: Path) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ValueError("OpenCode /config did not return an object")
    mcp = config.get("mcp")
    pie = mcp.get("pie") if isinstance(mcp, dict) else None
    expected = ["-m", "pie.interfaces.mcp_server", "--root", str(expected_root)]
    if (not isinstance(pie, dict) or pie.get("enabled") is not True
            or pie.get("type") != "local"
            or not isinstance(pie.get("command"), list)
            or pie["command"][1:] != expected):
        raise ValueError("Effective PIE MCP command/root mismatch")
    if (not isinstance(status, dict)
            or not isinstance(status.get("pie"), dict)
            or status["pie"].get("status") != "connected"):
        raise ValueError("PIE MCP is not connected")
    if not isinstance(sessions, dict):
        raise ValueError("OpenCode /session/status contract mismatch")
    if not isinstance(tools, list) or not any(
            name in {"pie_project_status", "pie_pie_project_status",
                     "mcp__pie__pie_project_status"}
            for name in tools if isinstance(name, str)):
        raise ValueError("PIE status tool is not available in effective runtime")
    permissions = config.get("permission", {})
    if (not isinstance(permissions, dict)
            or any(permissions.get(name) != "deny" for name in
                   ("bash", "edit", "webfetch", "external_directory"))):
        raise ValueError("Effective OpenCode read-only permission policy missing")
    return {"pie_mcp": "connected", "root": str(expected_root),
            "status_tool": "available", "session_api": "compatible",
            "permissions": "configured"}


def probe(base_url: str, password: str, root: Path) -> dict[str, Any]:
    url = urlparse(base_url)
    if (url.scheme != "http" or url.hostname not in
            ("127.0.0.1", "::1", "localhost") or
            url.path not in ("", "/") or url.username or url.password
            or url.query or url.fragment):
        raise ValueError("Preflight requires HTTP loopback URL")
    if not password:
        raise ValueError("OpenCode server password required")
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("Existing absolute PIE root required")
    root = root.resolve(strict=True)
    token = base64.b64encode(("opencode:" + password).encode()).decode("ascii")
    headers = {"Authorization": "Basic " + token,
               "X-OpenCode-Directory": quote(str(root), safe="")}
    def get(path: str) -> Any:
        req = Request(base_url.rstrip("/") + path, headers=headers)
        with urlopen(req, timeout=10) as response:
            return json.load(response)
    return check_contract(get("/config"), get("/mcp"), get("/session/status"),
                          get("/experimental/tool/ids"), root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:4097")
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    password = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
    try:
        result = probe(args.url, password, args.root)
    except Exception as exc:
        print(json.dumps({"ready": False, "error": type(exc).__name__,
                          "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ready": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
