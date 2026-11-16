from pathlib import Path

import pytest

from pie.certification.regression import RunEvidence
from pie.retrieval.adaptive_runtime import MeasuredCandidate
from pie.retrieval.task_memory import start_task
from pie.runtime.context_runtime import ContextRuntime
from pie.runtime.local_execution import OperationSpec
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


def test_runtime_composes_state_engine_lifecycle(tmp_path: Path):
    storage = tmp_path / ".pie"
    storage.mkdir()
    connect(storage / "index.sqlite3").close()
    with ContextRuntime(tmp_path) as runtime:
        task = runtime.start("runtime task")
        event = runtime.record(task["task_id"], "note", "started")
        resumed = runtime.resume(task["task_id"], limit=10)
        assert event["task_id"] == task["task_id"]
        assert resumed["task"]["task_id"] == task["task_id"]


def test_runtime_state_engine_rejects_use_after_close(tmp_path: Path):
    runtime = ContextRuntime(tmp_path)
    runtime.close()
    with pytest.raises(RuntimeError, match="closed"):
        runtime.start("should fail")


def test_runtime_rejects_checkpoint_use_after_close(tmp_path: Path):
    runtime = ContextRuntime(tmp_path)
    runtime.close()
    with pytest.raises(RuntimeError, match="closed"):
        runtime.checkpoint("task-1", {"value": 1})
    with pytest.raises(RuntimeError, match="closed"):
        runtime.checkpoint_agent("task-1", "agent-a", {"value": 1})
    with pytest.raises(RuntimeError, match="closed"):
        runtime.list_agent_checkpoints("task-1")


def test_runtime_rejects_restore_after_close(tmp_path: Path):
    runtime = ContextRuntime(tmp_path)
    runtime.close()
    with pytest.raises(RuntimeError, match="closed"):
        runtime.restore_state("task-1")


def test_runtime_memory_is_not_operable_after_close(tmp_path: Path):
    runtime = ContextRuntime(tmp_path)
    runtime.close()
    with pytest.raises(RuntimeError, match="closed"):
        _ = runtime.memory


def test_runtime_close_propagates_first_error_and_cleans_up(tmp_path: Path):
    calls: list[str] = []

    class ExplodingStore:
        def __init__(self, name: str) -> None:
            self._name = name

        def close(self) -> None:
            calls.append(self._name)
            raise RuntimeError(f"{self._name} close failed")

    runtime = ContextRuntime(tmp_path)
    runtime._graph = ExplodingStore("graph")
    runtime._journal = ExplodingStore("journal")
    with pytest.raises(RuntimeError, match="graph close failed"):
        runtime.close()
    assert calls == ["graph", "journal"]  # both resources were attempted
    assert runtime._closed
    assert runtime._graph is None
    assert runtime._journal is None
    runtime.close()  # second call is idempotent even after a failed close
    assert calls == ["graph", "journal"]


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


def test_runtime_composes_local_execution_graph_and_shared_memory(tmp_path: Path):
    storage = tmp_path / ".pie"
    storage.mkdir()
    connect(storage / "index.sqlite3").close()
    task = start_task(tmp_path, "runtime task")
    with ContextRuntime(
        tmp_path,
        journal_path=tmp_path / "runtime.sqlite3",
        graph_path=Path(".pie") / "graph.sqlite3",
    ) as runtime:
        runtime.register_operation(OperationSpec("read", lambda args: {"value": args["x"]}))
        first = runtime.execute_local("read", {"x": 4})
        second = runtime.execute_local("read", {"x": 4})
        assert first["status"] == "SUCCESS"
        assert second["status"] == "REPLAYED"
        runtime.add_graph_node(task["task_id"], "a", "step")
        runtime.add_graph_node(task["task_id"], "b", "step")
        runtime.add_graph_edge(task["task_id"], "a", "b", "depends")
        assert runtime.graph_order(task["task_id"])["order"] == ["a", "b"]
        runtime.memory.checkpoint(task["task_id"], "agent-a", {"value": 4})
        assert runtime.memory.restore(task["task_id"], "agent-a")["state"] == "FOUND"


def test_context_runtime_integrates_all_six_pillars(tmp_path: Path):
    storage = tmp_path / ".pie"
    storage.mkdir()
    connect(storage / "index.sqlite3").close()

    def evidence(condition: str) -> RunEvidence:
        return RunEvidence(
            pair_id="pair-six-pillars",
            scenario_id="scenario-six-pillars",
            application="web",
            condition=condition,
            model="fixture-model",
            prompt_sha256="prompt-sha",
            configuration_sha256="config-sha",
            provider_usage_status="available",
            input_tokens=100 if condition == "baseline" else 80,
            cached_input_tokens=20,
            output_tokens=10,
            latency_ms=5.0,
            mcp_calls=1,
            oracle_pass=True,
            route_verified=True,
        )

    with ContextRuntime(
        tmp_path,
        journal_path=Path(".pie") / "runtime.sqlite3",
        graph_path=Path(".pie") / "context-runtime-graph.sqlite3",
    ) as runtime:
        task = runtime.start("six pillar fixture")
        runtime.record(task["task_id"], "note", "created")
        runtime.checkpoint_agent(task["task_id"], "agent-a", {"fact": {"value": 7}})
        compiled = runtime.compile_checkpoint(task["task_id"], [["fact", "value"]])
        assert compiled.data == {"fact": {"value": 7}}

        selected = runtime.choose([
            MeasuredCandidate("wide", "available", 100, 20, 10, 5.0),
            MeasuredCandidate("compact", "available", 80, 20, 10, 5.0),
        ])
        assert selected["representation"] == "compact"

        runtime.register_operation(OperationSpec("read_value", lambda args: args["value"]))
        assert runtime.execute_local("read_value", {"value": 7})["status"] == "SUCCESS"
        assert runtime.execute_local("read_value", {"value": 7})["status"] == "REPLAYED"

        runtime.add_graph_node(task["task_id"], "observe", "step")
        runtime.add_graph_node(task["task_id"], "verify", "step")
        runtime.add_graph_edge(task["task_id"], "observe", "verify", "depends")
        assert runtime.graph_order(task["task_id"])["order"] == ["observe", "verify"]
        assert runtime.memory.agents(task["task_id"])["agents"] == ["agent-a"]

        certified = runtime.evaluate_suite([(evidence("baseline"), evidence("optimized"))])
        assert certified["status"] == "CERTIFIED"
