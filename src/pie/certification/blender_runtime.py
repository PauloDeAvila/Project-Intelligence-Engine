"""Bounded local Blender process/endpoint recovery for live read-only runners."""
from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path


def _endpoint(environment: dict[str, str] | None = None) -> tuple[str, int] | None:
    env = environment if isinstance(environment, dict) else os.environ
    host = str(env.get("BLENDER_MCP_HOST") or env.get("MCP_FOR_BLENDER_HOST") or "127.0.0.1")
    raw_port = env.get("BLENDER_MCP_PORT") or env.get("MCP_FOR_BLENDER_PORT") or "9876"
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        return None
    return (host, port) if 1 <= port <= 65535 else None


def _endpoint_ready(endpoint: tuple[str, int]) -> bool:
    try:
        with socket.create_connection(endpoint, timeout=0.75):
            return True
    except (OSError, ValueError):
        return False


def _known_executable(environment: dict[str, str] | None = None) -> Path | None:
    env = environment if isinstance(environment, dict) else os.environ
    configured = env.get("BLENDER_EXECUTABLE") or env.get("BLENDER_PATH")
    if configured:
        return Path(configured).expanduser()
    program_files = env.get("ProgramFiles", r"C:\Program Files")
    # shortcut: known Blender 5.3 install only; configure BLENDER_EXECUTABLE for another install.
    return Path(program_files) / "Blender Foundation" / "Blender 5.3" / "blender.exe"


def ensure_blender_mcp(*, executable: str | Path | None = None,
                       environment: dict[str, str] | None = None,
                       timeout_s: float = 15.0) -> dict:
    """Return readiness, starting only the configured/known Blender executable if needed."""
    endpoint = _endpoint(environment)
    if endpoint is None:
        return {"state": "FAIL", "reason": "INVALID_ENDPOINT"}
    host, port = endpoint
    if _endpoint_ready(endpoint):
        return {"state": "PASS", "host": host, "port": port, "started": False}

    candidate = Path(executable).expanduser() if executable else _known_executable(environment)
    if candidate is None or not candidate.is_file():
        return {
            "state": "FAIL",
            "host": host,
            "port": port,
            "reason": "BLENDER_EXECUTABLE_UNAVAILABLE",
            "executable": str(candidate) if candidate else None,
        }
    try:
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        process = subprocess.Popen(
            [str(candidate)],
            cwd=str(candidate.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except OSError:
        return {"state": "FAIL", "host": host, "port": port,
                "reason": "BLENDER_START_FAILED", "executable": str(candidate)}

    deadline = time.monotonic() + max(0.0, timeout_s)
    while time.monotonic() < deadline:
        if _endpoint_ready(endpoint):
            return {"state": "PASS", "host": host, "port": port, "started": True,
                    "pid": process.pid, "executable": str(candidate)}
        time.sleep(0.25)
    return {"state": "FAIL", "host": host, "port": port,
            "reason": "BLENDER_MCP_START_TIMEOUT", "pid": process.pid,
            "executable": str(candidate)}
