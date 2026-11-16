from __future__ import annotations

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
