from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from pie.retrieval.task_memory import (
    checkpoint_task,
    checkpoint_agent_state,
    list_agent_checkpoints,
    record_task,
    restore_state,
    start_task,
)
from pie.storage.database import connect


@pytest.fixture
def root(tmp_path):
    storage = tmp_path / ".pie"
    storage.mkdir()
    connection = connect(storage / "index.sqlite3")
    connection.close()
    return tmp_path


def _task(root, objective="internal objective"):
    return start_task(root, objective)["task_id"]


def _rows(root, task_id):
    connection = sqlite3.connect(root / ".pie" / "index.sqlite3")
    try:
        return connection.execute(
            "SELECT task_id,seq,schema_version,state_json,state_hash,"
            "provenance_json,provenance_hash FROM pie_task_checkpoints "
            "WHERE task_id=? ORDER BY seq",
            (task_id,),
        ).fetchall()
    finally:
        connection.close()


def test_checkpoint_round_trip_latest_and_explicit(root):
    task_id = _task(root)
    first = checkpoint_task(root, task_id, {"phase": 1})
    second = checkpoint_task(
        root, task_id, {"phase": 2, "text": "a: , b"}, {"source": "fixture"}
    )

    assert first["seq"] == 1
    assert second["seq"] == 2
    assert restore_state(root, task_id)["state_value"]["phase"] == 2
    assert restore_state(root, task_id, first["seq"])["state_value"] == {"phase": 1}
    assert restore_state(root, task_id, second["seq"])["provenance"] == {
        "source": "fixture"
    }


def test_provenance_is_bounded_scalar_metadata(root):
    task_id = _task(root)
    checkpoint = checkpoint_task(
        root,
        task_id,
        {"phase": 1},
        {"attempt": 2, "verified": True, "note": "local"},
    )
    assert restore_state(root, task_id, checkpoint["seq"])["provenance"] == {
        "attempt": 2,
        "verified": True,
        "note": "local",
    }
    with pytest.raises(ValueError):
        checkpoint_task(root, task_id, {"phase": 2}, {"nested": {"x": 1}})
    with pytest.raises(ValueError):
        checkpoint_task(root, task_id, {"phase": 3}, {"items": [1, 2]})


@pytest.mark.parametrize(
    "payload",
    [
        {"api_token": "x"},
        {"nested": {"password_value": "x"}},
        {"nested": [{"secret": "x"}]},
        {"credential_hint": "x"},
        {"value": "contains\x00nul"},
        {"value": float("nan")},
        {"value": float("inf")},
        {"value": b"bytes"},
        {"value": {1: "non-string key"}},
    ],
)
def test_checkpoint_rejects_unsafe_payloads(root, payload):
    with pytest.raises(ValueError):
        checkpoint_task(root, _task(root), payload)


def test_checkpoint_rejects_structural_limits(root):
    task_id = _task(root)
    deep = "leaf"
    for _ in range(7):
        deep = {"nested": deep}
    with pytest.raises(ValueError):
        checkpoint_task(root, task_id, {"value": deep})
    with pytest.raises(ValueError):
        checkpoint_task(root, task_id, {f"key_{i}": i for i in range(65)})
    with pytest.raises(ValueError):
        checkpoint_task(root, task_id, {"items": list(range(129))})
    with pytest.raises(ValueError):
        checkpoint_task(root, task_id, {"value": "x" * 513})
    with pytest.raises(ValueError):
        checkpoint_task(
            root,
            task_id,
            {f"key_{i}": "x" * 512 for i in range(64)},
        )


def test_checkpoint_hash_tampering_fails_closed(root):
    task_id = _task(root)
    checkpoint = checkpoint_task(root, task_id, {"phase": "original"})
    connection = sqlite3.connect(root / ".pie" / "index.sqlite3")
    try:
        connection.execute(
            "UPDATE pie_task_checkpoints SET state_json=? WHERE task_id=? AND seq=?",
            ('{"phase":"tampered"}', task_id, checkpoint["seq"]),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ValueError):
        restore_state(root, task_id)


def test_completed_task_is_immutable(root):
    task_id = _task(root)
    record_task(root, task_id, "result", "finished", status="completed")
    with pytest.raises(ValueError):
        checkpoint_task(root, task_id, {"phase": "late"})
    with pytest.raises(ValueError):
        record_task(root, task_id, "note", "late")


def test_not_found_and_invalid_sequence_are_explicit(root):
    task_id = _task(root)
    assert restore_state(root, task_id) == {
        "state": "NOT_FOUND",
        "task_id": task_id,
        "seq": None,
    }
    assert restore_state(root, task_id, seq=1) == {
        "state": "NOT_FOUND",
        "task_id": task_id,
        "seq": None,
    }
    assert restore_state(root, "missing")["state"] == "NOT_FOUND"
    for invalid in (0, -1, "1", True):
        with pytest.raises(ValueError):
            restore_state(root, task_id, seq=invalid)


def test_checkpoint_does_not_copy_objective_or_event_text(root):
    objective = "OBJECTIVE-MUST-NOT-LEAK"
    event_text = "EVENT-TEXT-MUST-NOT-LEAK"
    task_id = _task(root, objective)
    record_task(root, task_id, "note", event_text)
    checkpoint_task(root, task_id, {"progress": "explicit-only"})
    serialized = json.dumps(_rows(root, task_id), ensure_ascii=False)
    assert objective not in serialized
    assert event_text not in serialized


def test_agent_checkpoint_is_explicit_and_filterable(root):
    task_id = _task(root, "agent memory objective")
    checkpoint_agent_state(
        root,
        task_id,
        "agent-a",
        {"progress": 1},
        {"source": "local"},
    )
    checkpoint_agent_state(root, task_id, "agent-b", {"progress": 2})
    all_checkpoints = list_agent_checkpoints(root, task_id)
    agent_a = list_agent_checkpoints(root, task_id, agent_id="agent-a")
    assert all_checkpoints["state"] == "FOUND"
    assert len(all_checkpoints["checkpoints"]) == 2
    assert [item["provenance"]["agent_id"] for item in agent_a["checkpoints"]] == ["agent-a"]
    assert "state_json" not in json.dumps(all_checkpoints)
    with pytest.raises(ValueError):
        checkpoint_agent_state(root, task_id, "agent-a", {"progress": 3}, {"agent_id": "agent-b"})


def test_agent_checkpoint_missing_filter_is_explicit(root):
    task_id = _task(root)
    checkpoint_agent_state(root, task_id, "agent-a", {"progress": 1})
    result = list_agent_checkpoints(root, task_id, agent_id="agent-missing")
    assert result["state"] == "NOT_FOUND"


def test_concurrent_checkpoints_get_unique_sequences(root):
    task_id = _task(root)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda i: checkpoint_task(root, task_id, {"index": i}),
                range(8),
            )
        )
    assert sorted(result["seq"] for result in results) == list(range(1, 9))
    assert restore_state(root, task_id)["state"] == "FOUND"
