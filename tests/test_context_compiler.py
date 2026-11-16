from __future__ import annotations

import json
import sqlite3

import pytest

from pie.retrieval.context_compiler import (
    CompiledContext,
    ContextCompilationError,
    compile_task_checkpoint,
)
from pie.retrieval.task_memory import checkpoint_task, start_task
from pie.storage.database import connect


@pytest.fixture
def root(tmp_path):
    storage = tmp_path / ".pie"
    storage.mkdir()
    connection = connect(storage / "index.sqlite3")
    connection.close()
    return tmp_path


def test_compile_task_checkpoint_projects_verified_state(root):
    task = start_task(root, "reconcile ledger")
    checkpoint = checkpoint_task(
        root,
        task["task_id"],
        {"plan": {"stage": "verify"}, "counts": [1, 2, 3]},
        {"source": "fixture"},
    )
    compiled = compile_task_checkpoint(
        root,
        task["task_id"],
        required_paths=[["plan", "stage"], ["counts", 0]],
    )

    assert isinstance(compiled, CompiledContext)
    assert compiled.schema == "pie-task-context-compiler-v1"
    assert compiled.source_sha256 == checkpoint["state_hash"]
    assert compiled.selected_paths == (("plan", "stage"), ("counts", 0))
    assert compiled.recovery_available is True
    payload = compiled.model_payload()
    assert json.loads(payload) == {"counts": [1], "plan": {"stage": "verify"}}
    assert "state_hash" not in payload
    assert "provenance" not in payload
    assert "objective" not in payload


def test_compile_task_checkpoint_requires_existing_checkpoint(root):
    task = start_task(root, "audit exports")
    with pytest.raises(ContextCompilationError):
        compile_task_checkpoint(root, task["task_id"], required_paths=[["plan"]])


def test_compile_task_checkpoint_rejects_missing_required_path(root):
    task = start_task(root, "index corpus")
    checkpoint_task(root, task["task_id"], {"plan": {"stage": "verify"}})
    with pytest.raises(ContextCompilationError):
        compile_task_checkpoint(
            root,
            task["task_id"],
            required_paths=[["missing", "path"]],
        )


def test_compile_task_checkpoint_fails_closed_on_tampered_state(root):
    task = start_task(root, "tamper check")
    checkpoint = checkpoint_task(root, task["task_id"], {"plan": {"stage": "verify"}})
    connection = sqlite3.connect(root / ".pie" / "index.sqlite3")
    try:
        connection.execute(
            "UPDATE pie_task_checkpoints SET state_json=? WHERE task_id=? AND seq=?",
            ('{"plan":{"stage":"tampered"}}', task["task_id"], checkpoint["seq"]),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ContextCompilationError):
        compile_task_checkpoint(root, task["task_id"], required_paths=[["plan"]])
