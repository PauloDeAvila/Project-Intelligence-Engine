"""Ephemeral Codex home containing exactly one selected MCP server."""
from __future__ import annotations

import json
import shutil
import tempfile
import tomllib
from contextlib import contextmanager
from pathlib import Path


def _toml_value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        pairs = []
        for key, item in value.items():
            if isinstance(item, (dict, list)) and isinstance(item, dict):
                continue
            pairs.append(f"{json.dumps(str(key))} = {_toml_value(item)}")
        return "{ " + ", ".join(pairs) + " }"
    raise ValueError("Unsupported Codex configuration value")


def _merge_config(base: dict, overlay: dict) -> dict:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def _server_table(source: Path, profile: str | None, server: str) -> dict:
    base = tomllib.loads((source / "config.toml").read_text(encoding="utf-8"))
    merged = dict(base.get("mcp_servers") or {})
    if profile:
        overlay = tomllib.loads((source / (profile + ".config.toml")).read_text(encoding="utf-8"))
        for name, value in (overlay.get("mcp_servers") or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(name), dict):
                merged[name] = _merge_config(merged[name], value)
            else:
                merged[name] = value
    selected = merged.get(server)
    if not isinstance(selected, dict):
        raise ValueError("Expected MCP server absent from Codex configuration")
    return selected


def _write_config(path: Path, model: str, server: str, selected: dict,
                  runtime_env: dict[str, str], workspace: Path | None,
                  reasoning_effort: str | None) -> None:
    lines = [f"model = {_toml_value(model)}", ""]
    if reasoning_effort is not None:
        lines.insert(1, f"model_reasoning_effort = {_toml_value(reasoning_effort)}")
    lines.append(f"[mcp_servers.{json.dumps(server)}]")
    for key, value in selected.items():
        if key in {"tools", "enabled"}:
            continue
        if key == "env":
            value = dict(value) if isinstance(value, dict) else {}
            value.update(runtime_env)
        if key == "args" and workspace is not None and isinstance(value, list):
            value = list(value)
            if "--workspace" in value:
                index = value.index("--workspace")
                if index + 1 < len(value):
                    value[index + 1] = str(workspace)
        lines.append(f"{key} = {_toml_value(value)}")
    if "env" not in selected and runtime_env:
        lines.append(f"env = {_toml_value(runtime_env)}")
    for tool, tool_config in (selected.get("tools") or {}).items():
        if not isinstance(tool_config, dict):
            continue
        lines.extend(["", f"[mcp_servers.{json.dumps(server)}.tools.{json.dumps(str(tool))}]"])
        for key, value in tool_config.items():
            lines.append(f"{key} = {_toml_value(value)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@contextmanager
def isolated_codex_home(source_home: Path, *, profile: str | None,
                        server: str, model: str,
                        runtime_env: dict[str, str],
                        workspace: Path | None = None):
    """Yield a temporary authenticated CODEX_HOME and remove it on exit."""
    source_home = Path(source_home).expanduser().resolve(strict=True)
    base_config = tomllib.loads((source_home / "config.toml").read_text(encoding="utf-8"))
    reasoning_effort = base_config.get("model_reasoning_effort")
    selected = _server_table(source_home, profile, server)
    with tempfile.TemporaryDirectory(prefix=".pie-codex-isolated-",
                                      dir=str(source_home.parent)) as temporary:
        target = Path(temporary)
        auth = source_home / "auth.json"
        if auth.is_file():
            shutil.copy2(auth, target / "auth.json")
        _write_config(target / "config.toml", model, server, selected, runtime_env,
                      workspace, reasoning_effort)
        yield target
