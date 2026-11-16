"""Read-only MCP projection for the persistent Context Runtime state.

This module intentionally exposes metadata and graph structure only. It does
not compile prompts, execute registered operations, restore state, or accept a
filesystem path from the caller.
"""
from __future__ import annotations

from pathlib import Path
import re

from pie.runtime.multi_agent_memory import MultiAgentMemory
from pie.runtime.task_graph import TaskGraphStore


GRAPH_PATH = Path(".pie") / "context-runtime-graph.sqlite3"
_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
RUNTIME_OPERATIONS = (
    "graph_snapshot",
    "graph_order",
    "agent_references",
    "agents",
)
_OPERATIONS = frozenset(RUNTIME_OPERATIONS)


def _id(value: object, name: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a bounded opaque identifier")
    return value


def _limit(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 100:
        raise ValueError("limit must be an integer from 1 to 100")
    return value


def _graph_path(root: Path) -> Path:
    resolved = Path(root).expanduser().resolve(strict=True)
    base = resolved / GRAPH_PATH.parent
    path = base / GRAPH_PATH.name
    if base.is_symlink():
        raise ValueError("Invalid runtime graph location")
    if base.is_dir() and path.resolve(strict=False).parent != base.resolve(strict=True):
        raise ValueError("Invalid runtime graph location")
    return path.resolve(strict=False)


def query_runtime(
    root: Path,
    operation: str,
    task_id: str,
    *,
    agent_id: str | None = None,
    limit: int = 100,
) -> dict[str, object]:
    """Return a bounded, read-only view of runtime state.

    Missing runtime state is explicit and is never treated as an empty or
    successful graph. The graph database is never created by this function.
    """
    if operation not in _OPERATIONS:
        raise ValueError("Runtime operation is not allowlisted")
    task_id = _id(task_id, "task_id")
    if agent_id is not None:
        agent_id = _id(agent_id, "agent_id")
    limit = _limit(limit)

    if operation in ("graph_snapshot", "graph_order"):
        path = _graph_path(root)
        if path.is_symlink() or not path.is_file():
            return {
                "state": "NOT_CONFIGURED",
                "operation": operation,
                "task_id": task_id,
            }
        try:
            graph = TaskGraphStore(path, read_only=True)
            try:
                result = (
                    graph.get_graph(task_id, limit)
                    if operation == "graph_snapshot"
                    else graph.topological_order(task_id)
                )
            finally:
                graph.close()
            result["operation"] = operation
            return result
        except Exception:
            return {
                "state": "ERROR",
                "operation": operation,
                "task_id": task_id,
                "error_code": "RUNTIME_GRAPH_UNAVAILABLE",
            }

    try:
        memory = MultiAgentMemory(root)
        if operation == "agent_references":
            return memory.references(task_id, agent_id, limit)
        if agent_id is not None:
            raise ValueError("agent_id is not valid for agents")
        return memory.agents(task_id, limit)
    except ValueError:
        raise
    except Exception:
        return {
            "state": "ERROR",
            "operation": operation,
            "task_id": task_id,
            "error_code": "RUNTIME_MEMORY_UNAVAILABLE",
        }


__all__ = ["GRAPH_PATH", "RUNTIME_OPERATIONS", "query_runtime"]
