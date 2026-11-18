from __future__ import annotations

import threading

import pytest

from pie.runtime.task_graph import (
    GraphConflictError,
    GraphValidationError,
    TaskGraphStore,
)


def test_graph_is_persistent_idempotent_and_detects_conflicts(tmp_path):
    path = tmp_path / "graph.sqlite3"
    store = TaskGraphStore(path)
    assert store.add_node("task-1", "a", "step", {"rank": 1})["state"] == "CREATED"
    assert store.add_node("task-1", "a", "step", {"rank": 1})["state"] == "EXISTING"
    with pytest.raises(GraphConflictError):
        store.add_node("task-1", "a", "other", {"rank": 1})
    with pytest.raises(GraphConflictError):
        store.add_node("task-1", "a", "step", {"rank": 2})
    store.close()

    reopened = TaskGraphStore(path)
    try:
        assert reopened.get_graph("task-1")["nodes"][0]["metadata"] == {"rank": 1}
    finally:
        reopened.close()


def test_graph_edges_and_deterministic_topological_order(tmp_path):
    store = TaskGraphStore(tmp_path / "graph.sqlite3")
    try:
        for node in ("c", "a", "b"):
            store.add_node("task-1", node, "step")
        assert store.add_edge("task-1", "a", "b", "depends")["state"] == "CREATED"
        assert store.add_edge("task-1", "b", "c", "depends")["state"] == "CREATED"
        assert store.add_edge("task-1", "a", "b", "depends")["state"] == "EXISTING"
        assert store.topological_order("task-1")["order"] == ["a", "b", "c"]
        with pytest.raises(GraphValidationError):
            store.add_edge("task-1", "a", "a", "depends")
        with pytest.raises(GraphValidationError):
            store.add_edge("task-1", "a", "missing", "depends")
    finally:
        store.close()


def test_graph_cycle_is_reported_and_sensitive_metadata_is_rejected(tmp_path):
    store = TaskGraphStore(tmp_path / "graph.sqlite3")
    try:
        store.add_node("task-1", "a", "step")
        store.add_node("task-1", "b", "step")
        store.add_edge("task-1", "a", "b", "depends")
        store.add_edge("task-1", "b", "a", "depends")
        assert store.topological_order("task-1")["state"] == "CYCLE"
        with pytest.raises(GraphValidationError):
            store.add_node("task-1", "secret", "step", {"token_count": 4})
        with pytest.raises(GraphValidationError):
            store.add_node("task-1", "c", "step", {"nested": {"x": 1}})
    finally:
        store.close()


def test_graph_concurrent_same_node_is_idempotent(tmp_path):
    store = TaskGraphStore(tmp_path / "graph.sqlite3")
    states: list[str] = []
    errors: list[Exception] = []

    def add():
        try:
            states.append(store.add_node("task-1", "shared", "step", {"v": 1})["state"])
        except Exception as exc:  # pragma: no cover - diagnostic guard
            errors.append(exc)

    threads = [threading.Thread(target=add) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    try:
        assert errors == []
        assert sorted(states) == ["CREATED", "EXISTING", "EXISTING", "EXISTING"]
    finally:
        store.close()


def test_graph_reports_truncation_instead_of_silent_partial_results(tmp_path):
    store = TaskGraphStore(tmp_path / "graph.sqlite3")
    try:
        for node in ("a", "b", "c"):
            store.add_node("task-1", node, "step")
        result = store.get_graph("task-1", limit=2)
        assert result["complete"] is False
        assert result["nodes_truncated"] is True
    finally:
        store.close()


def test_read_only_graph_does_not_initialize_or_mutate(tmp_path):
    path = tmp_path / "graph.sqlite3"
    store = TaskGraphStore(path)
    store.add_node("task-1", "n1", "source", {"value": "ok"})
    store.close()
    readonly = TaskGraphStore(path, read_only=True)
    try:
        assert readonly.get_graph("task-1")["state"] == "FOUND"
        with pytest.raises(GraphValidationError, match="read-only"):
            readonly.add_node("task-1", "n2", "source", {})
    finally:
        readonly.close()
