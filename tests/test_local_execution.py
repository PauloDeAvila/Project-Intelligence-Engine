from __future__ import annotations

from pie.runtime.local_execution import ExecutionContext, LocalExecutionEngine, OperationSpec
from pie.runtime.replay import ExecutionJournal


def test_local_execution_is_allowlisted_and_sanitizes_failures():
    engine = LocalExecutionEngine()
    engine.register(OperationSpec("sum", lambda args: {"value": args["a"] + args["b"]}))
    assert engine.registered_operations() == ("sum",)
    assert engine.execute("sum", {"a": 2, "b": 3})["result"] == {"value": 5}
    assert engine.execute("missing", {})["error_code"] == "operation_not_registered"
    assert engine.execute("sum", {"password": "hidden"})["status"] == "BLOCKED"
    assert "hidden" not in str(engine.execute("sum", {"password": "hidden"}))


def test_local_execution_rejects_duplicate_and_non_serializable_results():
    engine = LocalExecutionEngine()
    engine.register(OperationSpec("bad", lambda _args: object()))
    assert engine.execute("bad", {})["error_code"] == "result_not_serializable"
    try:
        engine.register(OperationSpec("bad", lambda _args: None))
    except ValueError:
        pass
    else:  # pragma: no cover - assertion guard
        raise AssertionError("duplicate operation was accepted")


def test_local_execution_allows_non_secret_metric_field_names_in_results():
    engine = LocalExecutionEngine()
    engine.register(OperationSpec("metrics", lambda _args: {"input_tokens": 12}))
    result = engine.execute("metrics", {})
    assert result["status"] == "SUCCESS"
    assert result["result"] == {"input_tokens": 12}


def test_local_execution_supports_cooperative_timeout_and_context():
    seen = []

    def handler(_args, context):
        seen.append(context.remaining_ms())
        return {"ok": True}

    engine = LocalExecutionEngine()
    engine.register(OperationSpec("read", handler, max_duration_ms=1000))
    result = engine.execute("read", {}, context=ExecutionContext.with_timeout_ms(1000))
    assert result["status"] == "SUCCESS"
    assert seen and seen[0] is not None

    expired = ExecutionContext.with_timeout_ms(1)
    expired._deadline_ns = 0
    assert engine.execute("read", {}, context=expired)["error_code"] == "deadline_expired"


def test_local_execution_supports_keyword_only_context_without_mutating_caller():
    seen = []

    def handler(_args, *, context):
        seen.append(context.remaining_ms())
        return {"ok": True}

    engine = LocalExecutionEngine()
    engine.register(OperationSpec("read", handler, max_duration_ms=1000))
    context = ExecutionContext.with_timeout_ms(5000)
    assert engine.execute("read", {}, context=context)["status"] == "SUCCESS"
    assert seen and seen[0] <= 1000
    assert context.remaining_ms() > 1000


def test_local_execution_does_not_misclassify_single_argument_named_context():
    engine = LocalExecutionEngine()

    def handler(context):
        return {"received": context["value"]}

    engine.register(OperationSpec("read", handler))
    assert engine.execute("read", {"value": 8})["result"] == {"received": 8}


def test_local_execution_rejects_empty_explicit_operation_id():
    engine = LocalExecutionEngine()
    engine.register(OperationSpec("read", lambda _args: {"ok": True}))
    assert engine.execute("read", {}, operation_id="")["error_code"] == "invalid_arguments"


def test_local_execution_uses_real_journal_without_double_execution(tmp_path):
    calls = 0

    def handler(_args):
        nonlocal calls
        calls += 1
        return {"value": 7}

    journal = ExecutionJournal(tmp_path / "journal.sqlite3")
    engine = LocalExecutionEngine(journal)
    engine.register(OperationSpec("read", handler))
    first = engine.execute("read", {"id": "x"})
    second = engine.execute("read", {"id": "x"})
    try:
        assert first["status"] == "SUCCESS"
        assert first["result"] == {"value": 7}
        assert second["status"] == "REPLAYED"
        assert calls == 1
    finally:
        journal.close()
