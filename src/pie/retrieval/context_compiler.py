"""Deterministic, source-grounded context projection for model delivery.

The compiler never invents values and never truncates a required field. A
caller must declare the fields needed by its task; the complete source remains
available to the caller for validation or recovery.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from pie.retrieval import task_memory


class ContextCompilationError(ValueError):
    """The requested projection cannot be delivered without losing evidence.

    ``state`` makes the failure explicit instead of a silent degradation:
    ``INSUFFICIENT_CONTEXT`` when the requested evidence cannot be restored or
    located, ``UNSATISFIED`` when the request itself is invalid or out of
    budget. ``reason`` is a stable, verifiable machine-readable reason code.
    """

    def __init__(self, message: str, *,
                 state: str = "UNSATISFIED",
                 reason: str = "context_compilation_error") -> None:
        super().__init__(message)
        self.state = state
        self.reason = reason


PathPart = str | int
Path = tuple[PathPart, ...]


@dataclass(frozen=True)
class CompiledContext:
    schema: str
    source_sha256: str
    data: Any
    selected_paths: tuple[Path, ...]
    omitted_paths: tuple[Path, ...]
    recovery_available: bool

    def model_payload(self) -> str:
        """Return only the source-grounded projection intended for the model."""
        return json.dumps(self.data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def as_record(self) -> dict[str, Any]:
        """Return an auditable envelope for local telemetry, not model context."""
        return {
            "schema": self.schema,
            "source_sha256": self.source_sha256,
            "data": self.data,
            "selected_paths": [list(path) for path in self.selected_paths],
            "omitted_paths": [list(path) for path in self.omitted_paths],
            "recovery_available": self.recovery_available,
        }


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContextCompilationError(
            "source is not finite JSON data",
            state="UNSATISFIED", reason="source_not_finite_json") from exc


def _validate_paths(paths: Sequence[Sequence[PathPart]]) -> tuple[Path, ...]:
    if not isinstance(paths, (list, tuple)) or not paths or len(paths) > 128:
        raise ContextCompilationError(
            "at least one required source path is required",
            state="UNSATISFIED", reason="required_paths_invalid")
    normalized: list[Path] = []
    for path in paths:
        if not isinstance(path, (list, tuple)) or not path or len(path) > 32:
            raise ContextCompilationError(
                "invalid required source path",
                state="UNSATISFIED", reason="required_paths_invalid")
        if any(not isinstance(part, (str, int)) or isinstance(part, bool) for part in path):
            raise ContextCompilationError(
                "invalid source path component",
                state="UNSATISFIED", reason="required_paths_invalid")
        normalized.append(tuple(path))
    if len(set(normalized)) != len(normalized):
        raise ContextCompilationError(
            "duplicate required source path",
            state="UNSATISFIED", reason="required_paths_invalid")
    return tuple(normalized)


def _read(value: Any, path: Path) -> Any:
    current = value
    for part in path:
        if isinstance(current, dict) and isinstance(part, str) and part in current:
            current = current[part]
        elif isinstance(current, list) and isinstance(part, int) and 0 <= part < len(current):
            current = current[part]
        else:
            raise ContextCompilationError(
                "required source path is unavailable",
                state="INSUFFICIENT_CONTEXT", reason="required_path_unavailable")
    return current


def _insert(target: Any, path: Path, value: Any) -> Any:
    if len(path) == 1:
        if isinstance(target, dict) and isinstance(path[0], str):
            target[path[0]] = value
            return target
        if isinstance(target, list) and isinstance(path[0], int):
            while len(target) <= path[0]:
                target.append(None)
            target[path[0]] = value
            return target
        raise ContextCompilationError(
            "incompatible source projection",
            state="UNSATISFIED", reason="incompatible_projection")
    head, tail = path[0], path[1:]
    if isinstance(head, str):
        if not isinstance(target, dict):
            raise ContextCompilationError(
                "incompatible source projection",
                state="UNSATISFIED", reason="incompatible_projection")
        child = target.setdefault(head, {} if isinstance(tail[0], str) else [])
        _insert(child, tail, value)
        return target
    if not isinstance(target, list) or head < 0:
        raise ContextCompilationError(
            "incompatible source projection",
            state="UNSATISFIED", reason="incompatible_projection")
    while len(target) <= head:
        target.append(None)
    if target[head] is None:
        target[head] = {} if isinstance(tail[0], str) else []
    _insert(target[head], tail, value)
    return target


def compile_context(
    source: Any,
    *,
    required_paths: Sequence[Sequence[PathPart]],
    max_chars: int = 4096,
    recovery_available: bool = True,
) -> CompiledContext:
    """Project explicit source fields without estimating or fabricating tokens."""
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or not 1 <= max_chars <= 1_000_000:
        raise ContextCompilationError(
            "max_chars is outside the safe bound",
            state="UNSATISFIED", reason="max_chars_invalid")
    canonical = _canonical(source)
    if len(canonical) > 2_000_000:
        raise ContextCompilationError(
            "source exceeds the safe compilation bound",
            state="UNSATISFIED", reason="source_too_large")
    paths = _validate_paths(required_paths)
    resolved = [(path, _read(source, path)) for path in paths]
    projected: Any = {} if isinstance(paths[0][0], str) else []
    for path, value in resolved:
        _insert(projected, path, value)
    payload = json.dumps(projected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(payload) > max_chars:
        raise ContextCompilationError(
            "required evidence exceeds the context budget",
            state="UNSATISFIED", reason="evidence_exceeds_budget")
    return CompiledContext(
        "pie-context-compiler-v1",
        hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        projected,
        paths,
        tuple(),
        bool(recovery_available),
    )


def compile_task_checkpoint(
    root: Path,
    task_id: str,
    required_paths: Sequence[Sequence[PathPart]],
    max_chars: int = 4096,
) -> CompiledContext:
    """Project only selected fields from a verified task checkpoint."""
    try:
        restored = task_memory.restore_state(root, task_id)
    except ValueError as exc:
        raise ContextCompilationError(
            f"checkpoint restore failed: {exc}",
            state="INSUFFICIENT_CONTEXT", reason="checkpoint_restore_failed") from exc
    if restored.get("state") == "NOT_FOUND":
        raise ContextCompilationError(
            "no checkpoint found for the requested task",
            state="INSUFFICIENT_CONTEXT", reason="checkpoint_not_found")
    if (
        restored.get("state") != "FOUND"
        or "state_value" not in restored
        or not isinstance(restored.get("state_hash"), str)
        or not restored["state_hash"]
    ):
        raise ContextCompilationError(
            "invalid checkpoint shape returned by restore_state",
            state="INSUFFICIENT_CONTEXT", reason="checkpoint_invalid_shape")
    try:
        compiled = compile_context(
            restored["state_value"],
            required_paths=required_paths,
            max_chars=max_chars,
            recovery_available=True,
        )
    except ContextCompilationError:
        raise
    except ValueError as exc:
        raise ContextCompilationError(
            f"checkpoint compilation failed: {exc}",
            state="UNSATISFIED", reason="checkpoint_compilation_failed") from exc
    return CompiledContext(
        "pie-task-context-compiler-v1",
        restored["state_hash"],
        compiled.data,
        compiled.selected_paths,
        compiled.omitted_paths,
        compiled.recovery_available,
    )


__all__ = [
    "CompiledContext",
    "ContextCompilationError",
    "compile_context",
    "compile_task_checkpoint",
]
