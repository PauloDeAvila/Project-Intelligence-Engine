"""Optional RTK invocation, never silently retry a mutating command."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

# Supported syntax is intentionally conservative. Unknown commands use PIE's
# fallback capture rather than guessing an RTK rewrite.
RTK_CANDIDATES = frozenset({"git", "cargo", "pytest", "npm", "go", "docker", "kubectl"})


def rtk_available() -> bool:
    return shutil.which("rtk") is not None


def wrap_command(command: list[str], mode: str = "auto") -> tuple[list[str], bool]:
    if mode not in ("off", "auto", "required"):
        raise ValueError("Unknown RTK mode")
    if not command or not all(isinstance(v, str) and v for v in command):
        raise ValueError("Command argument array cannot be empty")
    if mode == "off" or Path(command[0]).stem.lower() == "rtk":
        return list(command), False
    name = Path(command[0]).stem.lower()
    supported = name in RTK_CANDIDATES and command[0].lower() in (
        name, name + ".exe")
    installed = rtk_available()
    if mode == "required" and not (supported and installed):
        raise RuntimeError("RTK cannot handle this command; nothing was executed")
    if supported and installed:
        return [shutil.which("rtk"), *command], True
    return list(command), False


def rtk_version() -> str | None:
    binary = shutil.which("rtk")
    if not binary:
        return None
    try:
        p = subprocess.run([binary, "--version"], timeout=8, capture_output=True,
                           text=True, check=False)
        return (p.stdout or p.stderr).strip()[:200] if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def install_rtk_codex_hook(*, accept_config_change: bool = False) -> dict:
    """Explicit operator action; never run automatically during PIE startup."""
    binary = shutil.which("rtk")
    if not binary:
        raise RuntimeError("RTK not installed. Install from the official rtk-ai/rtk release")
    if not accept_config_change:
        return {"state": "DRY_RUN", "command": [binary, "init", "-g", "--codex"]}
    result = subprocess.run([binary, "init", "-g", "--codex"], timeout=30,
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("RTK hook setup failed: " + (result.stderr or "")[:500])
    return {"state": "INSTALLED_BY_RTK", "tool": "codex",
            "note": "RTK installer controls hook configuration; inspect changes"}
