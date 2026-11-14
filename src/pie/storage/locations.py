"""Central PIE storage routing.

Only the opt-in global MCP process sets PIE_GLOBAL_STORAGE_ROOT. All legacy
project-local calls retain their .pie paths, preserving backward compatibility.
A stable hashed canonical workspace path keeps unrelated projects isolated
under one private user-owned global storage directory.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path

ENV_HOME = "PIE_GLOBAL_STORAGE_ROOT"


def global_home() -> Path:
    override = os.environ.get(ENV_HOME)
    return Path(override).expanduser().resolve() if override else (Path.home() / ".pie-global").resolve()


def project_id(root: Path) -> str:
    resolved = Path(root).resolve(strict=True)
    normalized = os.path.normcase(str(resolved))
    return sha256(normalized.encode("utf-8")).hexdigest()[:32]


def workspace_storage(root: Path) -> Path:
    """Return a workspace data directory; global when explicitly enabled."""
    configured = os.environ.get(ENV_HOME)
    if not configured:
        return Path(root) / ".pie"
    base = global_home()
    return base / "projects" / project_id(root)


def workspace_file(root: Path, name: str = "index.sqlite3") -> Path:
    if name not in ("index.sqlite3", "evidence_atoms.sqlite3", "config.toml"):
        raise ValueError("Unsupported workspace storage filename")
    return workspace_storage(root) / name
