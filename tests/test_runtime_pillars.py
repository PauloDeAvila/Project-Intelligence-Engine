from __future__ import annotations

from pie.certification.regression import RunEvidence
from pie.retrieval.adaptive_runtime import MeasuredCandidate
from pie.runtime.local_execution import OperationSpec
from pie.runtime.pillars import (
    AdaptiveRuntime,
    ContextCompiler,
    ContinuousCertification,
    LocalExecutionEngine,
    MultiAgentMemory,
    StateEngine,
)
from pie.runtime import (
    AdaptiveRuntime as ExportedAdaptiveRuntime,
    ContextCompiler as ExportedContextCompiler,
    ContinuousCertification as ExportedContinuousCertification,
    StateEngine as ExportedStateEngine,
    CompiledContext,
    MeasuredCandidate,
    RunEvidence,
)
from pie.storage.database import connect


def test_named_pillars_delegate_to_existing_contracts(tmp_path):
    assert ExportedAdaptiveRuntime is AdaptiveRuntime
    assert ExportedContextCompiler is ContextCompiler
    assert ExportedContinuousCertification is ContinuousCertification
    assert ExportedStateEngine is StateEngine
    assert CompiledContext.__name__ == "CompiledContext"
    assert MeasuredCandidate.__name__ == "MeasuredCandidate"
    assert RunEvidence.__name__ == "RunEvidence"
    storage = tmp_path / ".pie"
    storage.mkdir()
    connect(storage / "index.sqlite3").close()
    state = StateEngine(tmp_path)
    task = state.start("explicit task")
    state.checkpoint(task["task_id"], {"fact": {"value": 3}})
    compiled = ContextCompiler.compile_checkpoint(tmp_path, task["task_id"], [["fact", "value"]])
    assert compiled.data == {"fact": {"value": 3}}
    assert AdaptiveRuntime.choose([
        MeasuredCandidate("a", "available", 10, 0, 2, 2.0),
        MeasuredCandidate("b", "available", 5, 0, 2, 3.0),
    ])["representation"] == "b"


def test_continuous_certification_remains_fail_closed():
    def evidence(condition: str) -> RunEvidence:
        return RunEvidence(
            pair_id="pair", scenario_id="scenario", application="web", condition=condition,
            model="model", prompt_sha256="prompt", configuration_sha256="config",
            provider_usage_status="available", input_tokens=10, cached_input_tokens=2,
            output_tokens=2, latency_ms=1.0, mcp_calls=1, oracle_pass=True,
            route_verified=True,
        )

    assert ContinuousCertification.pair(evidence("baseline"), evidence("optimized"))["status"] == "CERTIFIED_PAIR"
    assert ContinuousCertification.suite([])["status"] == "NOT_CERTIFIED"


def test_pillars_reexport_existing_symbols_without_wrappers():
    from pie.runtime.local_execution import LocalExecutionEngine as DirectLocalExecutionEngine
    from pie.runtime.multi_agent_memory import MultiAgentMemory as DirectMultiAgentMemory

    assert LocalExecutionEngine is DirectLocalExecutionEngine
    assert MultiAgentMemory is DirectMultiAgentMemory
    import pie.runtime.pillars as pillars

    assert "LocalExecutionEngine" in pillars.__all__
    assert "MultiAgentMemory" in pillars.__all__


def test_pillars_local_operation_and_memory_checkpoint_work(tmp_path):
    storage = tmp_path / ".pie"
    connect(storage / "index.sqlite3").close()

    engine = LocalExecutionEngine()
    engine.register(OperationSpec("sum", lambda args: {"value": args["a"] + args["b"]}))
    result = engine.execute("sum", {"a": 2, "b": 3})
    assert result["status"] == "SUCCESS"
    assert result["result"] == {"value": 5}

    state = StateEngine(tmp_path)
    task = state.start("multi agent task")

    memory = MultiAgentMemory(tmp_path)
    recorded = memory.checkpoint(task["task_id"], "agent-1", {"fact": {"value": 3}})
    assert isinstance(recorded, dict) and recorded["state_hash"]
    restored = memory.restore(task["task_id"], "agent-1")
    assert restored["state"] == "FOUND"
    assert restored["checkpoint"]["state_value"] == {"fact": {"value": 3}}
    assert restored["checkpoint"]["provenance"]["agent_id"] == "agent-1"
