from __future__ import annotations

import pytest
import time

from pie.certification.task_telemetry import record_task, report as task_report
from pie.gateway.metrics import record, report as gateway_report
from pie.gateway.mcp_stdio import MCPStdioGateway, _event_id, _id


def test_gateway_event_id_is_stable_and_content_free():
    first = _event_id({"id": 7}, "resp")
    second = _event_id({"id": 7}, "resp")
    assert first == second
    assert first != _event_id({"id": 7}, "resp", 1.0)
    assert first.startswith("resp-")
    assert len(first) < 80
    assert "secret-response-body" not in _event_id("secret-response-body", "resp")


def test_gateway_metrics_and_task_telemetry_ignore_duplicate_event(root_tmp_path):
    event_id = "resp-duplicate-1"
    for _ in range(2):
        record(
            root_tmp_path,
            surface="mcp",
            tool="browser_snapshot",
            state="COMPACTED",
            source_chars=100,
            returned_chars=20,
            elapsed_ms=4.0,
            source_event_id=event_id,
        )
    gateway = gateway_report(root_tmp_path)
    task = task_report(root_tmp_path, app="web")
    assert gateway["events"] == 1
    assert sum(group["events"] for group in task["apps"]) == 1


def test_direct_task_telemetry_duplicate_is_ignored(root_tmp_path):
    kwargs = dict(
        surface="mcp",
        tool="get_scene_info",
        state="PASSTHROUGH",
        source_chars=10,
        returned_chars=10,
        elapsed_ms=1.0,
        app="blender",
        task_id="task-1",
        run_id="run-1",
        pair_id="pair-1",
        condition="observed",
        source_event_id="resp-telemetry-1",
    )
    record_task(root_tmp_path, **kwargs)
    record_task(root_tmp_path, **kwargs)
    result = task_report(root_tmp_path, app="blender", task_id="task-1")
    assert sum(group["events"] for group in result["apps"]) == 1


def test_event_id_validation_fails_closed(root_tmp_path):
    with pytest.raises(ValueError):
        record(
            root_tmp_path,
            surface="mcp",
            tool="x",
            state="S",
            source_chars=0,
            returned_chars=0,
            elapsed_ms=0,
            source_event_id="contains spaces",
        )


def test_mcp_transform_records_response_and_allows_reused_request_id(root_tmp_path):
    gateway = MCPStdioGateway(root_tmp_path, ["python", "-c", "pass"])
    gateway._listed_tools.add("get_scene_info")
    response = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": [{"type": "text", "text": "small observation"}]},
    }
    gateway._pending[_id(1)] = ("tools/call", "get_scene_info", time.perf_counter(), None)
    assert gateway._transform(response) == response
    time.sleep(0.001)
    gateway._pending[_id(1)] = ("tools/call", "get_scene_info", time.perf_counter(), None)
    assert gateway._transform(response) == response
    assert gateway_report(root_tmp_path)["events"] == 2


@pytest.fixture
def root_tmp_path(tmp_path):
    # Give tmp_path its own workspace marker so detect_workspace(tmp_path)
    # resolves to tmp_path itself instead of walking up into the repo (or
    # wherever --basetemp points), which would share storage across tests.
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    return tmp_path


def test_record_and_report_agree_on_child_root_under_workspace(tmp_path):
    # A root that sits inside a detectable workspace (marker at the parent)
    # must canonicalize to the workspace root for both record and report, so
    # the gateway never splits metrics across two storage locations.
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    child = tmp_path / "child"
    child.mkdir()
    record(
        child,
        surface="mcp",
        tool="browser_snapshot",
        state="PASSTHROUGH",
        source_chars=50,
        returned_chars=10,
        elapsed_ms=1.0,
    )
    assert gateway_report(child)["events"] == 1
    assert gateway_report(tmp_path)["events"] == 1
