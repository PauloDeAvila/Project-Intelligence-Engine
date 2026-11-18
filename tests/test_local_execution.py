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


# ---------------------------------------------------------------------------
# Hard timeout tests. Handlers must be module-level so they are picklable
# under the spawn context on Windows.
# ---------------------------------------------------------------------------
import multiprocessing  # noqa: E402
import time  # noqa: E402


def _hard_ok_handler(_args):
    return {"value": 42}


def _hard_error_handler(_args):
    raise RuntimeError("boom")


def _hard_slow_handler(args):
    marker = args.get("marker")
    if isinstance(marker, str):
        try:
            with open(marker, "w", encoding="utf-8") as handle:
                handle.write("child-ran")
        except OSError:
            pass
    time.sleep(5)
    return {"never": True}


def _hard_context_handler(_args, context):
    return {"remaining": context.remaining_ms()}


def _hard_args_handler(args):
    return {"received": args["value"]}


def test_hard_timeout_success_and_exception():
    engine = LocalExecutionEngine()
    engine.register(OperationSpec("hard_ok", _hard_ok_handler, hard_timeout=True))
    result = engine.execute("hard_ok", {})
    assert result["status"] == "SUCCESS"
    assert result["result"] == {"value": 42}

    engine.register(OperationSpec("hard_err", _hard_error_handler, hard_timeout=True))
    result = engine.execute("hard_err", {})
    assert result["status"] == "ERROR"
    assert result["error_code"] == "handler_error"


def test_hard_timeout_exceeded_kills_child_and_marks_marker(tmp_path):
    marker = tmp_path / "child_marker.txt"
    engine = LocalExecutionEngine()
    # Startup cost of the spawn-based child (interpreter + module import)
    # can approach the deadline on slow machines; give the child enough
    # headroom to actually run the handler before the hard timeout fires.
    engine.register(OperationSpec("slow", _hard_slow_handler, max_duration_ms=5_000, hard_timeout=True))
    result = engine.execute("slow", {"marker": str(marker)})
    assert result["status"] == "TIMEOUT"
    assert result["error_code"] == "hard_timeout_exceeded"
    deadline = time.monotonic() + 10.0
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert marker.read_text(encoding="utf-8") == "child-ran"
    assert multiprocessing.active_children() == []


def test_hard_timeout_rejects_non_pickleable_handler():
    engine = LocalExecutionEngine()
    engine.register(OperationSpec("lambda_op", lambda _args: {"ok": True}, hard_timeout=True))
    result = engine.execute("lambda_op", {})
    assert result["status"] == "ERROR"
    assert result["error_code"] == "hard_timeout_unavailable"


def test_hard_timeout_respects_smaller_of_deadlines():
    engine = LocalExecutionEngine()
    engine.register(OperationSpec("hard_ctx", _hard_context_handler, max_duration_ms=10_000, hard_timeout=True))
    context = ExecutionContext.with_timeout_ms(5_000)
    result = engine.execute("hard_ctx", {}, context=context)
    assert result["status"] == "SUCCESS"
    assert result["result"]["remaining"] <= 5_000

    # max_duration_ms smaller than the context deadline wins.
    engine.register(OperationSpec("hard_args", _hard_args_handler, max_duration_ms=10_000, hard_timeout=True))
    result = engine.execute("hard_args", {"value": 9})
    assert result["status"] == "SUCCESS"
    assert result["result"] == {"received": 9}


def test_hard_timeout_journal_replay_compatibility(tmp_path):
    journal = ExecutionJournal(tmp_path / "journal.sqlite3")
    engine = LocalExecutionEngine(journal)
    engine.register(OperationSpec("hard_ok", _hard_ok_handler, hard_timeout=True))
    try:
        first = engine.execute("hard_ok", {"id": "x"})
        second = engine.execute("hard_ok", {"id": "x"})
        assert first["status"] == "SUCCESS"
        assert first["result"] == {"value": 42}
        assert second["status"] == "REPLAYED"
    finally:
        journal.close()
