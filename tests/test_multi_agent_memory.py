from __future__ import annotations

import pytest

from pie.runtime.multi_agent_memory import MultiAgentMemory
from pie.retrieval.task_memory import start_task
from pie.storage.database import connect


def test_multi_agent_memory_shares_verified_references(tmp_path):
    storage = tmp_path / ".pie"
    storage.mkdir()
    connect(storage / "index.sqlite3").close()
    task = start_task(tmp_path, "agent coordination")
    memory = MultiAgentMemory(tmp_path)
    saved = memory.checkpoint(
        task["task_id"], "agent-a", {"selected": "scene"}, {"role": "reader"}
    )
    assert saved["state_hash"]
    assert memory.agents(task["task_id"])["agents"] == ["agent-a"]
    restored = memory.restore(task["task_id"], "agent-a")
    assert restored["state"] == "FOUND"
    assert restored["checkpoint"]["state_value"] == {"selected": "scene"}


def test_multi_agent_memory_does_not_restore_another_agent_checkpoint(tmp_path):
    storage = tmp_path / ".pie"
    storage.mkdir()
    connect(storage / "index.sqlite3").close()
    task = start_task(tmp_path, "agent coordination")
    memory = MultiAgentMemory(tmp_path)
    memory.checkpoint(task["task_id"], "agent-a", {"value": 1})
    assert memory.restore(task["task_id"], "agent-b")["state"] == "NOT_FOUND"


def test_multi_agent_memory_can_restore_an_old_explicit_sequence(tmp_path):
    storage = tmp_path / ".pie"
    storage.mkdir()
    connect(storage / "index.sqlite3").close()
    task = start_task(tmp_path, "agent coordination")
    memory = MultiAgentMemory(tmp_path)
    for value in range(101):
        memory.checkpoint(task["task_id"], "agent-a", {"value": value})
    restored = memory.restore(task["task_id"], "agent-a", seq=1)
    assert restored["state"] == "FOUND"
    assert restored["checkpoint"]["state_value"] == {"value": 0}


def _setup(tmp_path):
    storage = tmp_path / ".pie"
    storage.mkdir()
    connect(storage / "index.sqlite3").close()
    return start_task(tmp_path, "agent coordination")


def test_multi_agent_memory_restore_unknown_sequence_is_not_found(tmp_path):
    task = _setup(tmp_path)
    memory = MultiAgentMemory(tmp_path)
    memory.checkpoint(task["task_id"], "agent-a", {"value": 1})
    restored = memory.restore(task["task_id"], "agent-a", seq=999)
    assert restored == {
        "state": "NOT_FOUND",
        "task_id": task["task_id"],
        "agent_id": "agent-a",
        "checkpoint": None,
    }


def test_multi_agent_memory_restore_explicit_sequence_of_other_agent_is_not_found(
    tmp_path,
):
    task = _setup(tmp_path)
    memory = MultiAgentMemory(tmp_path)
    saved = memory.checkpoint(task["task_id"], "agent-a", {"value": 1})
    restored = memory.restore(task["task_id"], "agent-b", seq=saved["seq"])
    assert restored == {
        "state": "NOT_FOUND",
        "task_id": task["task_id"],
        "agent_id": "agent-b",
        "checkpoint": None,
    }


def test_multi_agent_memory_agents_on_task_without_checkpoints_is_not_found(
    tmp_path,
):
    task = _setup(tmp_path)
    memory = MultiAgentMemory(tmp_path)
    assert memory.agents(task["task_id"]) == {
        "state": "NOT_FOUND",
        "task_id": task["task_id"],
        "agents": [],
    }


def test_multi_agent_memory_agents_rejects_invalid_limit(tmp_path):
    task = _setup(tmp_path)
    memory = MultiAgentMemory(tmp_path)
    for limit in (0, 101, "5", None):
        with pytest.raises(ValueError):
            memory.agents(task["task_id"], limit=limit)


def test_multi_agent_memory_references_filter_agent_and_limit(tmp_path):
    task = _setup(tmp_path)
    memory = MultiAgentMemory(tmp_path)
    first = memory.checkpoint(task["task_id"], "agent-a", {"value": 1})
    memory.checkpoint(task["task_id"], "agent-b", {"value": 2})
    memory.checkpoint(task["task_id"], "agent-a", {"value": 3})
    references = memory.references(task["task_id"], "agent-a")
    assert references["state"] == "FOUND"
    assert [item["seq"] for item in references["checkpoints"]] == [
        first["seq"] + 2,
        first["seq"],
    ]
    bounded = memory.references(task["task_id"], "agent-a", limit=1)
    assert [item["seq"] for item in bounded["checkpoints"]] == [first["seq"] + 2]
    assert memory.references(task["task_id"], "agent-c")["state"] == "NOT_FOUND"


def test_multi_agent_memory_requires_existing_root(tmp_path):
    with pytest.raises(ValueError):
        MultiAgentMemory(tmp_path / "missing")


def test_multi_agent_memory_rejects_conflicting_provenance_agent_id(tmp_path):
    task = _setup(tmp_path)
    memory = MultiAgentMemory(tmp_path)
    with pytest.raises(ValueError):
        memory.checkpoint(
            task["task_id"], "agent-a", {"value": 1}, {"agent_id": "agent-b"}
        )


def test_multi_agent_memory_restore_without_sequence_returns_not_found_for_unknown_task(
    tmp_path,
):
    _setup(tmp_path)
    memory = MultiAgentMemory(tmp_path)
    restored = memory.restore("nonexistent-task", "agent-a")
    assert restored == {
        "state": "NOT_FOUND",
        "task_id": "nonexistent-task",
        "agent_id": "agent-a",
        "checkpoint": None,
    }


def test_multi_agent_memory_handoff_survives_agent_boundary(tmp_path):
    task = _setup(tmp_path)
    memory = MultiAgentMemory(tmp_path)
    source = memory.checkpoint(
        task["task_id"], "codex", {"decision": "use_verified_context"}
    )
    transferred = memory.handoff(task["task_id"], "codex", "deepseek")

    assert transferred["state"] == "HANDOFF_CREATED"
    assert transferred["source_seq"] == source["seq"]
    resumed = memory.restore(task["task_id"], "deepseek")
    assert resumed["state"] == "FOUND"
    assert resumed["checkpoint"]["state_value"] == {
        "decision": "use_verified_context"
    }
    assert resumed["checkpoint"]["provenance"]["handoff_from"] == "codex"


def test_multi_agent_memory_handoff_rejects_unknown_source(tmp_path):
    task = _setup(tmp_path)
    memory = MultiAgentMemory(tmp_path)
    assert memory.handoff(task["task_id"], "codex", "deepseek")["state"] == "NOT_FOUND"


def test_multi_agent_memory_handoff_requires_distinct_agents(tmp_path):
    task = _setup(tmp_path)
    memory = MultiAgentMemory(tmp_path)
    with pytest.raises(ValueError):
        memory.handoff(task["task_id"], "codex", "codex")
