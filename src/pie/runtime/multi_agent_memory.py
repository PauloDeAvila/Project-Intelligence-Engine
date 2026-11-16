"""Verified shared task memory for cooperating local agents.

This facade reuses the existing checkpoint store. It exposes references and
bounded metadata to coordinators while restoring state only after the store's
hash and provenance checks succeed.
"""
from __future__ import annotations

from pathlib import Path

from pie.retrieval import task_memory


class MultiAgentMemory:
    """Share verified checkpoints without storing prompts or model output."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError("memory root must be an existing directory")

    def checkpoint(
        self,
        task_id: str,
        agent_id: str,
        state: object,
        provenance: object | None = None,
    ) -> dict:
        return task_memory.checkpoint_agent_state(
            self.root, task_id, agent_id, state, provenance
        )

    def references(
        self, task_id: str, agent_id: str | None = None, limit: int = 100
    ) -> dict:
        return task_memory.list_agent_checkpoints(
            self.root, task_id, agent_id, limit
        )

    def restore(
        self, task_id: str, agent_id: str, seq: int | None = None
    ) -> dict:
        if seq is not None:
            restored = task_memory.restore_state(self.root, task_id, seq)
            if restored.get("state") != "FOUND":
                return {
                    "state": "NOT_FOUND", "task_id": task_id,
                    "agent_id": agent_id, "checkpoint": None,
                }
            provenance = restored.get("provenance")
            if not isinstance(provenance, dict) or provenance.get("agent_id") != agent_id:
                return {
                    "state": "NOT_FOUND", "task_id": task_id,
                    "agent_id": agent_id, "checkpoint": None,
                }
            return {
                "state": "FOUND", "task_id": task_id, "agent_id": agent_id,
                "checkpoint": restored,
            }
        references = self.references(task_id, agent_id, 100)
        if references["state"] == "NOT_FOUND":
            return {
                "state": "NOT_FOUND", "task_id": task_id,
                "agent_id": agent_id, "checkpoint": None,
            }
        selected = references["checkpoints"][0]
        restored = task_memory.restore_state(self.root, task_id, selected["seq"])
        if restored.get("state") != "FOUND":
            raise ValueError("agent checkpoint disappeared during restore")
        provenance = restored.get("provenance")
        if not isinstance(provenance, dict) or provenance.get("agent_id") != agent_id:
            raise ValueError("agent checkpoint provenance mismatch")
        return {
            "state": "FOUND", "task_id": task_id, "agent_id": agent_id,
            "checkpoint": restored,
        }

    def agents(self, task_id: str, limit: int = 100) -> dict:
        references = self.references(task_id, None, limit)
        if references["state"] == "NOT_FOUND":
            return {"state": "NOT_FOUND", "task_id": task_id, "agents": []}
        agent_ids = sorted({
            item["provenance"]["agent_id"]
            for item in references["checkpoints"]
            if isinstance(item.get("provenance"), dict)
            and isinstance(item["provenance"].get("agent_id"), str)
        })
        return {"state": "FOUND", "task_id": task_id, "agents": agent_ids}


__all__ = ["MultiAgentMemory"]
