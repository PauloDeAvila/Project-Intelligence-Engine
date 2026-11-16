from pathlib import Path

import pytest

from pie.certification.regression import RunEvidence
from pie.retrieval.adaptive_runtime import MeasuredCandidate
from pie.retrieval.task_memory import start_task
from pie.runtime.context_runtime import ContextRuntime
from pie.storage.database import connect


def test_runtime_does_not_create_journal_without_explicit_path(tmp_path: Path):
    runtime = ContextRuntime(tmp_path)
    assert runtime.journal is None
    with pytest.raises(RuntimeError, match="journal_path"):
        runtime.execute_once("runtime-op", {}, lambda: {"ok": True})
    runtime.close()


def test_runtime_resolves_relative_journal_to_workspace_and_rejects_use_after_close(tmp_path: Path):
    with ContextRuntime(tmp_path, journal_path=Path(".pie") / "runtime.sqlite3") as runtime:
        assert runtime.journal is not None
        assert (tmp_path / ".pie" / "runtime.sqlite3").is_file()
    with pytest.raises(RuntimeError, match="closed"):
        runtime.execute_once("runtime-op", {}, lambda: {"ok": True})


def test_runtime_composes_checkpoint_compiler_and_agent_metadata(tmp_path: Path):
    storage = tmp_path / ".pie"
    storage.mkdir()
    connect(storage / "index.sqlite3").close()
    task = start_task(tmp_path, "runtime task")
    runtime = ContextRuntime(tmp_path)
    checkpoint = runtime.checkpoint_agent(
        task["task_id"], "agent-glm", {"plan": {"step": 1}}, {"role": "builder"}
    )
    assert checkpoint["provenance_hash"]
    compiled = runtime.compile_checkpoint(task["task_id"], [["plan", "step"]])
    assert compiled.data == {"plan": {"step": 1}}
    listed = runtime.list_agent_checkpoints(task["task_id"], "agent-glm")
    assert listed["checkpoints"][0]["provenance_hash"] == checkpoint["provenance_hash"]
    runtime.close()


def test_runtime_uses_measured_selection_and_replay(tmp_path: Path):
    runtime = ContextRuntime(tmp_path, journal_path=tmp_path / "runtime.sqlite3")
    selected = runtime.choose(
        [
            MeasuredCandidate("wide", "available", 100, 20, 20, 5.0),
            MeasuredCandidate("compact", "available", 40, 10, 10, 6.0),
        ]
    )
    assert selected["representation"] == "compact"
    first = runtime.execute_once(
        "runtime-op", {"request": 1}, lambda: {"private": "body"},
        result_metadata=lambda result: {"status": "ok"},
    )
    second = runtime.execute_once(
        "runtime-op", {"request": 1}, lambda: {"must_not_run": True},
        result_metadata=lambda result: {"status": "wrong"},
    )
    assert first["status"] == "EXECUTED"
    assert second["status"] == "REPLAYED"
    assert second["result_metadata"] == {"status": "ok"}
    runtime.close()


def test_runtime_delegates_pair_and_suite_evaluation(tmp_path: Path):
    def evidence(condition: str) -> RunEvidence:
        return RunEvidence(
            pair_id="pair-runtime", scenario_id="scenario-runtime", application="web",
            condition=condition, model="model", prompt_sha256="p", configuration_sha256="c",
            provider_usage_status="available", input_tokens=100, cached_input_tokens=20,
            output_tokens=10, latency_ms=5.0, mcp_calls=1, oracle_pass=True, route_verified=True,
        )

    runtime = ContextRuntime(tmp_path)
    pair = runtime.evaluate_pair(evidence("baseline"), evidence("optimized"))
    suite = runtime.evaluate_suite([(evidence("baseline"), evidence("optimized"))])
    assert pair["status"] == "CERTIFIED_PAIR"
    assert suite["status"] == "CERTIFIED"
    runtime.close()
