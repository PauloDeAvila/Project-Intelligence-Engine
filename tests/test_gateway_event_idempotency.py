from __future__ import annotations

import pytest

from pie.certification.task_telemetry import record_task, report as task_report
from pie.gateway.metrics import record, report as gateway_report
from pie.gateway.mcp_stdio import _event_id


def test_gateway_event_id_is_stable_and_content_free():
    first = _event_id({"id": 7}, "resp")
    second = _event_id({"id": 7}, "resp")
    assert first == second
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


@pytest.fixture
def root_tmp_path(tmp_path):
    return tmp_path
