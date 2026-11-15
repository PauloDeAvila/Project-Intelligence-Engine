"""Measure MCP tools/list overhead without starting Codex or a model."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("PIE_PHASE3_WORKSPACE", str(ROOT))).resolve()
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
UVX = Path(r"C:\Users\phsra\.local\bin\uvx.exe")
NPX = Path(r"C:\Program Files\nodejs\npx.cmd")


def _request(identifier: int, method: str, params: dict) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": identifier, "method": method,
                       "params": params}, separators=(",", ":"))


def _read_response(stream, identifier: int, timeout: float = 45.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = stream.readline()
        if not line:
            break
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("id") == identifier:
            return value
    raise RuntimeError(f"response id {identifier} unavailable")


def _probe(label: str, command: list[str], *, store: Path) -> dict:
    probe_started = time.perf_counter()
    proc = subprocess.Popen(command, cwd=WORKSPACE, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace",
                            bufsize=1)
    try:
        assert proc.stdin is not None and proc.stdout is not None
        initialize_started = time.perf_counter()
        proc.stdin.write(_request(1, "initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "pie-phase3-tool-overhead", "version": "1"},
        }) + "\n")
        proc.stdin.flush()
        _read_response(proc.stdout, 1)
        initialize_ms = round((time.perf_counter() - initialize_started) * 1000, 3)
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized",
                                     "params": {}}, separators=(",", ":")) + "\n")
        tools_list_started = time.perf_counter()
        proc.stdin.write(_request(2, "tools/list", {}) + "\n")
        proc.stdin.flush()
        response = _read_response(proc.stdout, 2)
        tools_list_ms = round((time.perf_counter() - tools_list_started) * 1000, 3)
        tools = response.get("result", {}).get("tools", [])
        if not isinstance(tools, list):
            raise RuntimeError("tools/list result has no tools array")
        encoded = json.dumps(tools, ensure_ascii=False, separators=(",", ":"))
        descriptions = sum(len(str(tool.get("description", "")))
                           for tool in tools if isinstance(tool, dict))
        schemas = sum(len(json.dumps(tool.get("inputSchema", {}),
                                     ensure_ascii=False, separators=(",", ":")))
                      for tool in tools if isinstance(tool, dict))
        return {
            "label": label, "command_executable": Path(command[0]).name,
            "tool_count": len(tools), "tools_list_json_chars": len(encoded),
            "description_chars": descriptions, "input_schema_chars": schemas,
            "initialize_ms": initialize_ms, "tools_list_ms": tools_list_ms,
            "probe_ms": round((time.perf_counter() - probe_started) * 1000, 3),
            "tool_names": [tool.get("name") for tool in tools if isinstance(tool, dict)],
            "store": str(store),
        }
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        proc.kill()
        proc.wait(timeout=10)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pie-phase3-tool-overhead-") as temp:
        temp_root = Path(temp)
        store = temp_root / "store"
        store.mkdir()
        playwright = [str(NPX), "--yes", "@playwright/mcp@0.0.85", "--headless",
                      "--browser", "chrome", "--output-dir", str(temp_root / "web-output")]
        blender = [str(UVX), "mcp-for-blender"]
        commands = [
            ("blender-baseline", blender),
            ("blender-optimized", [str(PYTHON), "-m", "pie.gateway.domain", "serve",
             "--domain", "blender", "--workspace", str(WORKSPACE), "--max-chars", "2400",
             "--expose-tool", "get_scene_info", "--expose-tool", "execute_blender_code",
             "--expose-tool", "pie_blender_expand", "--expose-tool", "pie_gateway_output_get",
             "--store", str(store), "--", *blender]),
            ("web-baseline", playwright),
            ("web-optimized", [str(PYTHON), "-m", "pie.gateway.domain", "serve",
             "--domain", "web", "--workspace", str(WORKSPACE), "--max-chars", "2400",
             "--expose-tool", "browser_navigate", "--expose-tool", "browser_snapshot",
             "--expose-tool", "pie_gateway_output_get",
             "--store", str(store), "--", *playwright]),
        ]
        rows = []
        for label, command in commands:
            try:
                rows.append(_probe(label, command, store=store))
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                rows.append({"label": label, "status": "UNAVAILABLE", "error": str(exc)[:1000]})
        print(json.dumps({"schema": "pie-phase3-tool-overhead-v1", "rows": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
