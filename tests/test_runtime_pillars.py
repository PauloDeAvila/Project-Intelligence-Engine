from __future__ import annotations

from pie.certification.regression import RunEvidence
from pie.retrieval.adaptive_runtime import MeasuredCandidate
from pie.runtime.pillars import AdaptiveRuntime, ContextCompiler, ContinuousCertification, StateEngine
from pie.storage.database import connect


def test_named_pillars_delegate_to_existing_contracts(tmp_path):
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
