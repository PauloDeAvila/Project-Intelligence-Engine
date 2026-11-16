"""Explicit composition of the PIE Context Runtime pillars.

The facade owns only resources it creates itself. It delegates validation and
durability to the existing state, compiler, journal, adaptive, and
certification modules instead of maintaining a second implementation.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pie.certification.regression import RunEvidence, evaluate_golden_suite, evaluate_pair
from pie.retrieval import task_memory
from pie.retrieval.adaptive_runtime import MeasuredCandidate, choose_candidate
from pie.retrieval.context_compiler import (
    CompiledContext,
    TokenCounter,
    compile_context,
    compile_task_checkpoint,
)
from pie.runtime.local_execution import ExecutionContext, LocalExecutionEngine, OperationSpec
from pie.runtime.multi_agent_memory import MultiAgentMemory
from pie.runtime.replay import ExecutionJournal
from pie.runtime.task_graph import TaskGraphStore


class ContextRuntime:
    """Coordinate deterministic runtime services with explicit ownership."""

    def __init__(
        self,
        root: Path,
        *,
        journal_path: Path | None = None,
        graph_path: Path | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError("Context runtime root must be an existing directory")
        self._closed = False
        if journal_path is None:
            self._journal = None
        else:
            path = Path(journal_path)
            self._journal = ExecutionJournal(
                path if path.is_absolute() else self.root / path
            )
        try:
            self._graph = None
            if graph_path is not None:
                path = Path(graph_path)
                self._graph = TaskGraphStore(
                    path if path.is_absolute() else self.root / path
                )
            self._execution = LocalExecutionEngine(self._journal)
            self._memory = MultiAgentMemory(self.root)
        except Exception:
            if self._graph is not None:
                self._graph.close()
            if self._journal is not None:
                self._journal.close()
            raise

    @property
    def journal(self) -> ExecutionJournal | None:
        return self._journal

    @property
    def graph(self) -> TaskGraphStore | None:
        return self._graph

    @property
    def memory(self) -> MultiAgentMemory:
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        return self._memory

    @property
    def execution(self) -> LocalExecutionEngine:
        return self._execution

    def start(self, objective: str) -> dict:
        """Start a persistent task through the existing State Engine."""
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        return task_memory.start_task(self.root, objective)

    def record(self, task_id: str, kind: str, text: str, **kwargs: object) -> dict:
        """Append a task event through the existing State Engine."""
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        return task_memory.record_task(self.root, task_id, kind, text, **kwargs)

    def resume(self, task_id: str | None = None, limit: int = 30) -> dict:
        """Resume a task through the existing State Engine."""
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        return task_memory.resume_task(self.root, task_id, limit)

    def checkpoint(self, task_id: str, state: object, provenance: object | None = None) -> dict:
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        return task_memory.checkpoint_task(self.root, task_id, state, provenance)

    def checkpoint_agent(
        self,
        task_id: str,
        agent_id: str,
        state: object,
        provenance: object | None = None,
    ) -> dict:
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        return task_memory.checkpoint_agent_state(
            self.root, task_id, agent_id, state, provenance
        )

    def restore_state(self, task_id: str, seq: int | None = None) -> dict:
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        return task_memory.restore_state(self.root, task_id, seq)

    def list_agent_checkpoints(
        self, task_id: str, agent_id: str | None = None, limit: int = 100
    ) -> dict:
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        return task_memory.list_agent_checkpoints(self.root, task_id, agent_id, limit)

    def handoff(
        self,
        task_id: str,
        from_agent_id: str,
        to_agent_id: str,
        seq: int | None = None,
    ) -> dict:
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        return self._memory.handoff(task_id, from_agent_id, to_agent_id, seq)

    def compile_checkpoint(
        self,
        task_id: str,
        required_paths: Sequence[Sequence[str | int]],
        max_chars: int = 4096,
        token_budget: int | None = None,
        token_counter: TokenCounter | None = None,
    ) -> CompiledContext:
        return compile_task_checkpoint(
            self.root, task_id, required_paths, max_chars,
            token_budget=token_budget, token_counter=token_counter,
        )

    @staticmethod
    def compile(
        source: Any,
        *,
        required_paths: Sequence[Sequence[str | int]],
        max_chars: int = 4096,
        recovery_available: bool = True,
        token_budget: int | None = None,
        token_counter: TokenCounter | None = None,
    ) -> CompiledContext:
        return compile_context(
            source,
            required_paths=required_paths,
            max_chars=max_chars,
            recovery_available=recovery_available,
            token_budget=token_budget,
            token_counter=token_counter,
        )

    @staticmethod
    def choose(
        candidates: list[MeasuredCandidate],
        *,
        objective: str = "tokens",
        require_quality: bool = True,
    ) -> dict[str, object]:
        return choose_candidate(
            candidates, objective=objective, require_quality=require_quality
        )

    def execute_once(
        self,
        operation_id: str,
        payload: object,
        executor: Callable[[], object],
        result_metadata: Callable[[object], object] | None = None,
    ) -> dict[str, object]:
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        if self._journal is None:
            raise RuntimeError("journal_path was not provided")
        return self._journal.execute_once(
            operation_id, payload, executor, result_metadata=result_metadata
        )

    def register_operation(self, spec: OperationSpec) -> None:
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        self._execution.register(spec)

    def execute_local(
        self,
        name: str,
        args: dict[str, object] | None = None,
        *,
        operation_id: str | None = None,
        context: ExecutionContext | None = None,
    ) -> dict[str, object]:
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        return self._execution.execute(name, args, operation_id, context)

    def add_graph_node(
        self,
        task_id: str,
        node_id: str,
        kind: str,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        if self._graph is None:
            raise RuntimeError("graph_path was not provided")
        return self._graph.add_node(task_id, node_id, kind, metadata)

    def add_graph_edge(
        self, task_id: str, from_node: str, to_node: str, relation: str
    ) -> dict[str, object]:
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        if self._graph is None:
            raise RuntimeError("graph_path was not provided")
        return self._graph.add_edge(task_id, from_node, to_node, relation)

    def graph_snapshot(self, task_id: str, limit: int = 100) -> dict[str, object]:
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        if self._graph is None:
            raise RuntimeError("graph_path was not provided")
        return self._graph.get_graph(task_id, limit)

    def graph_order(self, task_id: str) -> dict[str, object]:
        if self._closed:
            raise RuntimeError("Context runtime is closed")
        if self._graph is None:
            raise RuntimeError("graph_path was not provided")
        return self._graph.topological_order(task_id)

    @staticmethod
    def evaluate_pair(baseline: RunEvidence, optimized: RunEvidence) -> dict[str, object]:
        return evaluate_pair(baseline, optimized)

    @staticmethod
    def evaluate_suite(
        pairs: list[tuple[RunEvidence, RunEvidence]],
    ) -> dict[str, object]:
        return evaluate_golden_suite(pairs)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        first_error: BaseException | None = None
        for resource in (self._graph, self._journal):
            if resource is None:
                continue
            try:
                resource.close()
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        self._graph = None
        self._journal = None
        self._memory = None
        if first_error is not None:
            raise first_error

    def __enter__(self) -> ContextRuntime:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


__all__ = ["ContextRuntime"]
