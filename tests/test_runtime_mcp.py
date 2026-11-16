from __future__ import annotations

import json

import pytest

from pie.interfaces.mcp_server import dispatch
from pie.runtime.context_runtime import ContextRuntime


def _call(root, arguments):
    return dispatch({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "pie_context_runtime", "arguments": arguments},
    }, root)


def _text(response):
    return json.loads(response["result"]["content"][0]["text"])


def test_runtime_tool_is_read_only_and_not_in_compact_profile(tmp_path):
    full = dispatch({"id": 1, "method": "tools/list"}, tmp_path)
    compact = dispatch({"id": 2, "method": "tools/list"}, tmp_path, tool_profile="compact")
    assert "pie_context_runtime" in {item["name"] for item in full["result"]["tools"]}
    assert "pie_context_runtime" not in {item["name"] for item in compact["result"]["tools"]}


def test_runtime_tool_does_not_create_graph_and_reports_missing_state(tmp_path):
    result = _text(_call(tmp_path, {"operation": "graph_snapshot", "task_id": "task-1"}))
    assert result["state"] == "NOT_CONFIGURED"
    assert not (tmp_path / ".pie" / "context-runtime-graph.sqlite3").exists()


def test_runtime_tool_reads_graph_and_agent_metadata_without_state_payload(tmp_path):
    (tmp_path / ".pie").mkdir()
    with ContextRuntime(tmp_path, graph_path=".pie/context-runtime-graph.sqlite3") as runtime:
        runtime.add_graph_node("task-1", "source", "source", {"path": "src/app.py"})
        runtime.add_graph_node("task-1", "check", "check", {"status": "ok"})
        runtime.add_graph_edge("task-1", "source", "check", "feeds")
    graph = _text(_call(tmp_path, {"operation": "graph_snapshot", "task_id": "task-1", "limit": 10}))
    assert graph["state"] == "FOUND"
    assert [node["node_id"] for node in graph["nodes"]] == ["check", "source"]
    order = _text(_call(tmp_path, {"operation": "graph_order", "task_id": "task-1"}))
    assert order["order"] == ["source", "check"]


def test_runtime_tool_rejects_invalid_ids_and_execution_like_operations(tmp_path):
    bad = _call(tmp_path, {"operation": "graph_snapshot", "task_id": "../secret"})
    assert bad["result"]["isError"] is True
    unknown = _call(tmp_path, {"operation": "execute_local", "task_id": "task-1"})
    assert unknown["result"]["isError"] is True
