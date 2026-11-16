from __future__ import annotations

import json
import sqlite3

import pytest

from pie.retrieval.context_compiler import (
    CompiledContext,
    ContextCompilationError,
    compile_context,
    compile_task_checkpoint,
)
from pie.retrieval import task_memory
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


def test_compile_context_error_state_and_reason():
    with pytest.raises(ContextCompilationError) as excinfo:
        compile_context({"a": 1}, required_paths=[["missing"]])
    assert excinfo.value.state == "INSUFFICIENT_CONTEXT"
    assert excinfo.value.reason == "required_path_unavailable"


def test_compile_context_error_state_unsatisfied_budget():
    big = {"a": "x" * 5000}
    with pytest.raises(ContextCompilationError) as excinfo:
        compile_context(big, required_paths=[["a"]], max_chars=100)
    assert excinfo.value.state == "UNSATISFIED"
    assert excinfo.value.reason == "evidence_exceeds_budget"


def test_compile_context_error_state_unsatisfied_max_chars():
    for bad in (0, -1, True, "4096", 2_000_001):
        with pytest.raises(ContextCompilationError) as excinfo:
            compile_context({"a": 1}, required_paths=[["a"]], max_chars=bad)
        assert excinfo.value.state == "UNSATISFIED"
        assert excinfo.value.reason == "max_chars_invalid"


def test_compile_context_error_state_unsatisfied_paths_invalid():
    for bad in ([], [[]], [["a", None]], [["a"], ["a"]], "not-a-list"):
        with pytest.raises(ContextCompilationError) as excinfo:
            compile_context({"a": 1}, required_paths=bad)
        assert excinfo.value.state == "UNSATISFIED"
        assert excinfo.value.reason == "required_paths_invalid"


def test_compile_context_error_state_unsatisfied_incompatible_projection():
    from pie.retrieval.context_compiler import _insert
    # Shape conflict: a dict-level key already holds a list, so inserting a
    # string-tailed path into it is an incompatible projection.
    with pytest.raises(ContextCompilationError) as excinfo:
        _insert({"a": [1]}, ("a", "b"), 1)
    assert excinfo.value.state == "UNSATISFIED"
    assert excinfo.value.reason == "incompatible_projection"


def test_compile_context_error_state_unsatisfied_source_not_finite_json():
    with pytest.raises(ContextCompilationError) as excinfo:
        compile_context(float("nan"), required_paths=[["a"]])
    assert excinfo.value.state == "UNSATISFIED"
    assert excinfo.value.reason == "source_not_finite_json"


def test_compile_task_checkpoint_not_found_state(root):
    task = start_task(root, "missing checkpoint")
    with pytest.raises(ContextCompilationError) as excinfo:
        compile_task_checkpoint(root, task["task_id"], required_paths=[["plan"]])
    assert excinfo.value.state == "INSUFFICIENT_CONTEXT"
    assert excinfo.value.reason == "checkpoint_not_found"


def test_compile_task_checkpoint_tampered_state_reason(root):
    task = start_task(root, "tamper reason")
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
    with pytest.raises(ContextCompilationError) as excinfo:
        compile_task_checkpoint(root, task["task_id"], required_paths=[["plan"]])
    assert excinfo.value.state == "INSUFFICIENT_CONTEXT"
    assert excinfo.value.reason == "checkpoint_restore_failed"


def test_compile_task_checkpoint_invalid_shape_reason(root, monkeypatch):
    task = start_task(root, "invalid shape")
    checkpoint_task(root, task["task_id"], {"plan": {"stage": "verify"}})

    def bogus_restore(root, task_id):
        return {"state": "WEIRD"}

    monkeypatch.setattr(task_memory, "restore_state", bogus_restore)
    with pytest.raises(ContextCompilationError) as excinfo:
        compile_task_checkpoint(root, task["task_id"], required_paths=[["plan"]])
    assert excinfo.value.state == "INSUFFICIENT_CONTEXT"
    assert excinfo.value.reason == "checkpoint_invalid_shape"


def test_context_compilation_error_remains_value_error():
    error = ContextCompilationError("boom")
    assert isinstance(error, ValueError)
    assert error.state == "UNSATISFIED"
    assert error.reason == "context_compilation_error"
    with pytest.raises(ValueError):
        compile_context({"a": 1}, required_paths=[["missing"]])


def test_compile_context_token_budget_without_counter_fails_closed():
    with pytest.raises(ContextCompilationError) as excinfo:
        compile_context(
            {"a": 1}, required_paths=[["a"]], token_budget=100
        )
    assert excinfo.value.state == "UNSATISFIED"
    assert excinfo.value.reason == "token_counter_unavailable"


def test_compile_context_token_budget_invalid():
    with pytest.raises(ContextCompilationError) as excinfo:
        compile_context(
            {"a": 1},
            required_paths=[["a"]],
            token_budget=0,
            token_counter=lambda text: 1,
        )
    assert excinfo.value.state == "UNSATISFIED"
    assert excinfo.value.reason == "token_budget_invalid"


def test_compile_context_token_budget_exceeded():
    calls = []

    def counter(text: str) -> int:
        calls.append(text)
        return 10_000

    with pytest.raises(ContextCompilationError) as excinfo:
        compile_context(
            {"a": 1},
            required_paths=[["a"]],
            token_budget=100,
            token_counter=counter,
        )
    assert excinfo.value.state == "UNSATISFIED"
    assert excinfo.value.reason == "evidence_exceeds_token_budget"
    assert len(calls) == 1


def test_compile_context_token_budget_accepted():
    def counter(text: str) -> int:
        return len(text)

    compiled = compile_context(
        {"a": 1},
        required_paths=[["a"]],
        token_budget=1000,
        token_counter=counter,
    )
    assert isinstance(compiled, CompiledContext)
    assert json.loads(compiled.model_payload()) == {"a": 1}


def test_compile_context_broken_counter_fails_closed():
    def raising_counter(text: str) -> int:
        raise RuntimeError("counter exploded")

    with pytest.raises(ContextCompilationError) as excinfo:
        compile_context(
            {"a": 1},
            required_paths=[["a"]],
            token_budget=100,
            token_counter=raising_counter,
        )
    assert excinfo.value.state == "UNSATISFIED"
    assert excinfo.value.reason == "token_counter_unavailable"

    with pytest.raises(ContextCompilationError) as excinfo:
        compile_context(
            {"a": 1},
            required_paths=[["a"]],
            token_budget=100,
            token_counter=lambda text: "not-an-int",
        )
    assert excinfo.value.reason == "token_counter_unavailable"


def test_compile_task_checkpoint_token_budget(root):
    task = start_task(root, "budgeted checkpoint")
    checkpoint_task(root, task["task_id"], {"plan": {"stage": "verify"}})

    compiled = compile_task_checkpoint(
        root,
        task["task_id"],
        required_paths=[["plan", "stage"]],
        token_budget=10_000,
        token_counter=lambda text: len(text),
    )
    assert isinstance(compiled, CompiledContext)

    with pytest.raises(ContextCompilationError) as excinfo:
        compile_task_checkpoint(
            root,
            task["task_id"],
            required_paths=[["plan", "stage"]],
            token_budget=1,
            token_counter=lambda text: len(text),
        )
    assert excinfo.value.state == "UNSATISFIED"
    assert excinfo.value.reason == "evidence_exceeds_token_budget"


def test_compile_task_checkpoint_token_counter_not_callable_fails_closed(root):
    task = start_task(root, "non-callable counter")
    checkpoint_task(root, task["task_id"], {"plan": {"stage": "verify"}})

    with pytest.raises(ContextCompilationError) as excinfo:
        compile_task_checkpoint(
            root,
            task["task_id"],
            required_paths=[["plan", "stage"]],
            token_budget=100,
            token_counter=1000,
        )
    assert excinfo.value.state == "UNSATISFIED"
    assert excinfo.value.reason == "token_counter_unavailable"


def test_compile_task_checkpoint_invalid_counter_measurement_fails_closed(root):
    task = start_task(root, "invalid measurement")
    checkpoint_task(root, task["task_id"], {"plan": {"stage": "verify"}})

    for invalid in (True, "many", -1):
        with pytest.raises(ContextCompilationError) as excinfo:
            compile_task_checkpoint(
                root,
                task["task_id"],
                required_paths=[["plan", "stage"]],
                token_budget=100,
                token_counter=lambda text, value=invalid: value,
            )
        assert excinfo.value.state == "UNSATISFIED"
        assert excinfo.value.reason == "token_counter_unavailable"


def test_compile_context_without_budget_regression():
    compiled = compile_context({"a": 1}, required_paths=[["a"]])
    assert isinstance(compiled, CompiledContext)
    assert json.loads(compiled.model_payload()) == {"a": 1}
