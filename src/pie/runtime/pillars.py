"""Named facades for the six Context Runtime pillars.

These facades intentionally delegate to the already validated PIE modules;
they do not create a second persistence or certification implementation.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pie.certification.regression import RunEvidence, evaluate_golden_suite, evaluate_pair
from pie.retrieval import task_memory
from pie.retrieval.adaptive_runtime import MeasuredCandidate, choose_candidate
from pie.retrieval.context_compiler import CompiledContext, compile_context, compile_task_checkpoint


class StateEngine:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError("state root must be an existing directory")

    def start(self, objective: str) -> dict:
        return task_memory.start_task(self.root, objective)

    def record(self, task_id: str, kind: str, text: str, **kwargs: object) -> dict:
        return task_memory.record_task(self.root, task_id, kind, text, **kwargs)

    def resume(self, task_id: str | None = None, limit: int = 30) -> dict:
        return task_memory.resume_task(self.root, task_id, limit)

    def checkpoint(self, task_id: str, state: object, provenance: object | None = None) -> dict:
        return task_memory.checkpoint_task(self.root, task_id, state, provenance)

    def restore(self, task_id: str, seq: int | None = None) -> dict:
        return task_memory.restore_state(self.root, task_id, seq)


class ContextCompiler:
    @staticmethod
    def compile(
        source: Any,
        *,
        required_paths: Sequence[Sequence[str | int]],
        max_chars: int = 4096,
        recovery_available: bool = True,
    ) -> CompiledContext:
        return compile_context(
            source,
            required_paths=required_paths,
            max_chars=max_chars,
            recovery_available=recovery_available,
        )

    @staticmethod
    def compile_checkpoint(
        root: Path,
        task_id: str,
        required_paths: Sequence[Sequence[str | int]],
        max_chars: int = 4096,
    ) -> CompiledContext:
        return compile_task_checkpoint(root, task_id, required_paths, max_chars)


class AdaptiveRuntime:
    @staticmethod
    def choose(
        candidates: list[MeasuredCandidate],
        *,
        objective: str = "tokens",
        require_quality: bool = True,
    ) -> dict[str, object]:
        return choose_candidate(candidates, objective=objective, require_quality=require_quality)


class ContinuousCertification:
    @staticmethod
    def pair(baseline: RunEvidence, optimized: RunEvidence) -> dict[str, object]:
        return evaluate_pair(baseline, optimized)

    @staticmethod
    def suite(pairs: list[tuple[RunEvidence, RunEvidence]]) -> dict[str, object]:
        return evaluate_golden_suite(pairs)


__all__ = ["AdaptiveRuntime", "ContextCompiler", "ContinuousCertification", "StateEngine"]
