from __future__ import annotations

import sqlite3
import threading

import pytest

from pie.runtime.replay import ExecutionJournal, ReplayConflict


@pytest.fixture
def journal(tmp_path):
    value = ExecutionJournal(tmp_path / "journal.sqlite3")
    yield value
    value.close()


def test_first_execution_and_duplicate_suppression(journal):
    calls = []

    def execute():
        calls.append(1)
        return {"ok": True}

    first = journal.execute_once("operation-1", {"x": 1}, execute)
    second = journal.execute_once("operation-1", {"x": 1}, execute)
    assert first["status"] == "EXECUTED"
    assert second["status"] == "REPLAYED"
    assert second["result_sha256"] == first["result_sha256"]
    assert calls == [1]


def test_payload_conflict_is_rejected(journal):
    journal.execute_once("operation-2", {"x": 1}, lambda: 1)
    with pytest.raises(ReplayConflict):
        journal.execute_once("operation-2", {"x": 2}, lambda: 2)


def test_started_operation_requires_reconciliation(journal):
    journal.execute_once("operation-3", {"x": 1}, lambda: 1)
    connection = sqlite3.connect(journal._path)
    connection.execute(
        "UPDATE execution_journal SET status='started',finished_utc=NULL"
    )
    connection.commit()
    connection.close()
    calls = []
    result = journal.execute_once("operation-3", {"x": 1}, lambda: calls.append(1))
    assert result["status"] == "REQUIRES_RECONCILIATION"
    assert calls == []


def test_failure_is_recorded_without_leaking_error_text(journal):
    def fail():
        raise RuntimeError("sensitive body")

    result = journal.execute_once("operation-4", {"x": 1}, fail)
    assert result == {
        "status": "FAILED",
        "operation_id": "operation-4",
        "payload_sha256": result["payload_sha256"],
        "error_code": "execution_failed",
    }
    assert "sensitive body" not in str(result)
    assert journal.execute_once("operation-4", {"x": 1}, lambda: 2)["status"] == "EXECUTED"


def test_payload_validation_and_canonical_equivalence(journal):
    with pytest.raises(ValueError):
        journal.execute_once("", {}, lambda: 1)
    with pytest.raises(ValueError):
        journal.execute_once("operation-!", {}, lambda: 1)
    with pytest.raises(ValueError):
        journal.execute_once("operation-5", {"x": float("nan")}, lambda: 1)
    with pytest.raises(ValueError):
        journal.execute_once("operation-6", {"x": float("inf")}, lambda: 1)
    with pytest.raises(ValueError):
        journal.execute_once("operation-7", {"x": "a" * (64 * 1024)}, lambda: 1)
    calls = []
    journal.execute_once("operation-8", {"a": 1, "b": 2}, lambda: calls.append(1))
    assert journal.execute_once("operation-8", {"b": 2, "a": 1}, lambda: calls.append(1))["status"] == "REPLAYED"
    assert calls == [1]


def test_concurrent_duplicate_callers_do_not_duplicate_side_effect(journal):
    calls = []
    calls_lock = threading.Lock()
    barrier = threading.Barrier(4)
    results = []

    def execute():
        with calls_lock:
            calls.append(1)
        return {"done": True}

    def worker():
        barrier.wait()
        results.append(journal.execute_once("operation-9", {"k": "v"}, execute))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(calls) == 1
    statuses = [result["status"] for result in results]
    assert statuses.count("EXECUTED") == 1
    assert all(status in {"REPLAYED", "REQUIRES_RECONCILIATION"} for status in statuses if status != "EXECUTED")
