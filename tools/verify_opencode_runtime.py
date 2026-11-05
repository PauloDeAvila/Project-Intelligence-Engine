"""Read-only OpenCode 2.x preflight. Never creates a session or triggers inference."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from pie.orchestrator.opencode_v2 import OpenCodeV2Adapter


def check_contract(
    config: Any, info: Any, mcp: Any, active: Any, root: Path
) -> dict[str, str]:
    if not isinstance(config, dict):
        raise ValueError("Expected local OpenCode v2 config object")
    servers = config.get("mcp", {}).get("servers", {})
    entry = servers.get("pie") if isinstance(servers, dict) else None
    expected = ["-m", "pie.interfaces.mcp_server", "--root", str(root)]
    if (not isinstance(entry, dict) or entry.get("type") != "local"
            or not isinstance(entry.get("command"), list)
            or entry["command"][1:] != expected
            or entry.get("codemode") is not False):
        raise ValueError("PIE MCP v2 command/root mismatch")
    permissions = config.get("permissions", [])
    def denied(action: str) -> bool:
        return isinstance(permissions, list) and any(
            isinstance(rule, dict) and rule.get("action") == action
            and rule.get("resource") == "*" and rule.get("effect") == "deny"
            for rule in permissions
        )
    if not all(denied(x) for x in
               ("shell", "edit", "subagent", "webfetch",
                "websearch", "external_directory", "execute")):
        raise ValueError("OpenCode v2 safety permissions not configured")
    if not isinstance(info, dict):
        raise ValueError("OpenCode /api/info invalid")
    if (not isinstance(mcp, dict)
            or not OpenCodeV2Adapter._location_matches(mcp, root)):
        raise ValueError("PIE MCP response points to another directory")
    servers_response = OpenCodeV2Adapter._data(mcp)
    if (not isinstance(servers_response, list) or
            not any(isinstance(s, dict) and s.get("name") == "pie"
                    and s.get("status") == "connected"
                    for s in servers_response)):
        raise ValueError("PIE MCP not connected in OpenCode v2")
    data = OpenCodeV2Adapter._data(active)
    if not isinstance(data, dict):
        raise ValueError("OpenCode v2 active session contract invalid")
    return {"pie_mcp": "connected", "root": str(root),
            "session_api": "v2", "permissions": "configured"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path,
                        default=os.environ.get("OPENCODE_CONFIG"))
    parser.add_argument("--url", default="http://127.0.0.1:4097")
    args = parser.parse_args(argv)
    try:
        if args.config is None:
            raise ValueError("Explicit isolated config file required")
        root = args.root.resolve(strict=True)
        config = json.loads(args.config.read_text(encoding="utf-8"))
        password = os.environ["OPENCODE_PASSWORD"]
        adapter = OpenCodeV2Adapter(args.url, password)
        result = check_contract(
            config, adapter._request("GET", "/info"),
            adapter._request("GET", "/mcp"),
            adapter._request("GET", "/session/active"), root
        )
        print(json.dumps({"ready": True, **result}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ready": False, "error": type(exc).__name__,
                          "reason": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
