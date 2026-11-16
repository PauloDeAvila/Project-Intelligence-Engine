"""Allowlisted deterministic local execution.

Timeouts are cooperative: handlers are never killed by threads or processes.
Handlers that can run longer than their deadline must inspect the supplied
context and stop themselves. The engine never persists arguments or results.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import inspect
import json
import math
import re
import time
from typing import Any, Callable

from pie.runtime.replay import ExecutionJournal

_OPERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SENSITIVE = (
    "prompt", "answer", "cookie", "password", "secret", "credential",
    "token", "api_key", "authorization",
)
_MAX_DEPTH = 8
_MAX_ITEMS = 64
_MAX_ARGS_BYTES = 16 * 1024
_MAX_RESULT_BYTES = 64 * 1024


@dataclass(frozen=True)
class OperationSpec:
    name: str
    handler: Callable[..., Any]
    read_only: bool = True
    max_duration_ms: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _OPERATION_ID.fullmatch(self.name):
            raise ValueError("invalid operation name")
        if not callable(self.handler):
            raise TypeError("handler must be callable")
        if not isinstance(self.read_only, bool):
            raise TypeError("read_only must be a bool")
        if self.max_duration_ms is not None and (
            type(self.max_duration_ms) is not int or self.max_duration_ms <= 0
        ):
            raise ValueError("max_duration_ms must be a positive integer")


class ExecutionContext:
    def __init__(self, deadline_ns: int | None = None) -> None:
        self._deadline_ns = deadline_ns

    @classmethod
    def with_timeout_ms(cls, timeout_ms: int) -> "ExecutionContext":
        if type(timeout_ms) is not int or timeout_ms <= 0:
            raise ValueError("timeout_ms must be a positive integer")
        return cls(time.monotonic_ns() + timeout_ms * 1_000_000)

    def expired(self) -> bool:
        return self._deadline_ns is not None and time.monotonic_ns() >= self._deadline_ns

    def remaining_ms(self) -> int | None:
        if self._deadline_ns is None:
            return None
        return max(0, (self._deadline_ns - time.monotonic_ns()) // 1_000_000)


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _validate_value(
    value: object, depth: int = 0, *, reject_sensitive: bool = True
) -> str | None:
    if depth > _MAX_DEPTH:
        return "invalid_arguments"
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return None
    if isinstance(value, float):
        return None if math.isfinite(value) else "invalid_arguments"
    if isinstance(value, str):
        return "invalid_arguments" if "\x00" in value else None
    if isinstance(value, dict):
        if len(value) > _MAX_ITEMS:
            return "invalid_arguments"
        for key, item in value.items():
            if not isinstance(key, str):
                return "invalid_arguments"
            if "\x00" in key:
                return "blocked_argument"
            if reject_sensitive and any(fragment in key.lower() for fragment in _SENSITIVE):
                return "blocked_argument"
            error = _validate_value(item, depth + 1, reject_sensitive=reject_sensitive)
            if error:
                return error
        return None
    if isinstance(value, list):
        if len(value) > _MAX_ITEMS:
            return "invalid_arguments"
        for item in value:
            error = _validate_value(item, depth + 1, reject_sensitive=reject_sensitive)
            if error:
                return error
        return None
    return "invalid_arguments"


def _validated_args(args: object | None) -> tuple[dict[str, object] | None, str | None]:
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return None, "invalid_arguments"
    error = _validate_value(args)
    if error:
        return None, error
    try:
        encoded = _canonical(args).encode("utf-8")
    except (TypeError, ValueError):
        return None, "invalid_arguments"
    if len(encoded) > _MAX_ARGS_BYTES:
        return None, "invalid_arguments"
    return json.loads(encoded), None


def _validated_result(value: object) -> tuple[object | None, bool]:
    try:
        encoded = _canonical(value).encode("utf-8")
        if len(encoded) > _MAX_RESULT_BYTES or _validate_value(value, reject_sensitive=False) is not None:
            return None, False
        return json.loads(encoded), True
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, False


def _envelope(status: str, name: str, started_ns: int, *, result: object = None, error_code: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": status,
        "operation_name": name,
        "duration_ms": (time.monotonic_ns() - started_ns) // 1_000_000,
    }
    if status == "SUCCESS":
        payload["result"] = result
    elif error_code is not None:
        payload["error_code"] = error_code
    return payload


class LocalExecutionEngine:
    """Execute only registered handlers and optionally journal them once."""

    def __init__(self, journal: ExecutionJournal | None = None) -> None:
        self._journal = journal
        self._operations: dict[str, OperationSpec] = {}

    def register(self, spec: OperationSpec) -> None:
        if spec.name in self._operations:
            raise ValueError("operation already registered")
        self._operations[spec.name] = spec

    def registered_operations(self) -> tuple[str, ...]:
        return tuple(sorted(self._operations))

    @staticmethod
    def _takes_context(handler: Callable[..., Any]) -> bool:
        try:
            parameters = inspect.signature(handler).parameters.values()
        except (TypeError, ValueError):
            return False
        positional = [
            item for item in parameters
            if item.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        return len(positional) >= 2

    def _run(self, spec: OperationSpec, args: dict[str, object], context: ExecutionContext, started_ns: int) -> dict[str, object]:
        deadline = context._deadline_ns
        if spec.max_duration_ms is not None:
            candidate = started_ns + spec.max_duration_ms * 1_000_000
            deadline = candidate if deadline is None else min(deadline, candidate)
            context._deadline_ns = deadline
        if context.expired():
            return _envelope("TIMEOUT", spec.name, started_ns, error_code="deadline_expired")
        try:
            if self._takes_context(spec.handler):
                value = spec.handler(args, context)
            else:
                value = spec.handler(args)
        except Exception:
            return _envelope("ERROR", spec.name, started_ns, error_code="handler_error")
        if context.expired():
            return _envelope("TIMEOUT", spec.name, started_ns, error_code="timeout")
        safe_value, valid = _validated_result(value)
        if not valid:
            return _envelope("ERROR", spec.name, started_ns, error_code="result_not_serializable")
        return _envelope("SUCCESS", spec.name, started_ns, result=safe_value)

    def execute(
        self, name: str, args: dict[str, object] | None = None,
        operation_id: str | None = None, context: ExecutionContext | None = None,
    ) -> dict[str, object]:
        started_ns = time.monotonic_ns()
        spec = self._operations.get(name)
        if spec is None:
            return _envelope("ERROR", str(name)[:128], started_ns, error_code="operation_not_registered")
        safe_args, error = _validated_args(args)
        if error:
            status = "BLOCKED" if error == "blocked_argument" else "ERROR"
            return _envelope(status, name, started_ns, error_code=error)
        assert safe_args is not None
        context = context or ExecutionContext()
        if context.expired():
            return _envelope("TIMEOUT", name, started_ns, error_code="deadline_expired")
        args_hash = hashlib.sha256(_canonical(safe_args).encode("utf-8")).hexdigest()
        resolved_id = operation_id or f"op-{hashlib.sha256((name + args_hash).encode('ascii')).hexdigest()[:32]}"
        if not _OPERATION_ID.fullmatch(resolved_id):
            return _envelope("ERROR", name, started_ns, error_code="invalid_arguments")
        if self._journal is None:
            return self._run(spec, safe_args, context, started_ns)
        captured: dict[str, object] = {}
        def run() -> dict[str, object]:
            captured["envelope"] = self._run(spec, safe_args, context, started_ns)
            return captured["envelope"]  # type: ignore[return-value]
        try:
            outcome = self._journal.execute_once(
                resolved_id,
                {"operation_name": name, "args_sha256": args_hash, "read_only": spec.read_only, "max_duration_ms": spec.max_duration_ms},
                run,
            )
        except Exception:
            return _envelope("FAILED", name, started_ns, error_code="journal_failed")
        status = outcome.get("status") if isinstance(outcome, dict) else None
        if status == "EXECUTED":
            return captured.get("envelope", _envelope("FAILED", name, started_ns, error_code="journal_failed"))  # type: ignore[return-value]
        if status == "REPLAYED":
            return _envelope("REPLAYED", name, started_ns)
        if status == "REQUIRES_RECONCILIATION":
            return _envelope("REQUIRES_RECONCILIATION", name, started_ns, error_code="reconciliation_required")
        return _envelope("FAILED", name, started_ns, error_code="journal_failed")


__all__ = ["ExecutionContext", "LocalExecutionEngine", "OperationSpec"]
