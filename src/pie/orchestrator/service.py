from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .models import Task, TaskStatus
from .store import TaskStore


@dataclass(frozen=True)
class ProjectPolicy:
    project_id: str
    root: Path
    models: frozenset[str]
    task_types: frozenset[str] = frozenset({"read_only_review"})


@dataclass(frozen=True)
class Execution:
    session_id: str | None
    result: dict[str, Any]
    metrics: dict[str, Any] | None


class Adapter(Protocol):
    def execute(self, task: Task, project: ProjectPolicy, prompt: str) -> Execution: ...
    def cancel(self, session_id: str) -> None: ...


class Freshness(Protocol):
    def validate(self, project: ProjectPolicy) -> dict[str, Any]: ...


class Orchestrator:
    """Single-worker controller. Payloads select policy IDs, never commands or paths."""
    def __init__(self, store: TaskStore, projects: dict[str, ProjectPolicy], adapter: Adapter, freshness: Freshness):
        self.store, self.projects, self.adapter, self.freshness = store, projects, adapter, freshness
        self.store.recover_interrupted()

    def submit(self, source: str, body: dict[str, Any]) -> tuple[Task, bool]:
        allowed = {"project_id", "task_type", "model", "idempotency_key", "priority", "timeout_seconds", "token_limit", "cost_limit"}
        if set(body) - allowed or not isinstance(body.get("idempotency_key"), str): raise ValueError("Invalid task payload")
        project = self.projects.get(body.get("project_id"))
        if project is None or not project.root.is_absolute() or project.root.resolve() != project.root: raise PermissionError("Project is not authorized")
        if body.get("task_type") not in project.task_types or body.get("model") not in project.models: raise PermissionError("Task type or model is not authorized")
        return self.store.create(source=source, key=body["idempotency_key"], project_id=project.project_id, task_type=body["task_type"], model=body["model"], priority=int(body.get("priority", 0)), timeout_seconds=int(body.get("timeout_seconds", 600)), token_limit=body.get("token_limit"), cost_limit=body.get("cost_limit"))

    def cancel(self, task_id: str) -> Task:
        task = self.store.get(task_id)
        if task is None: raise KeyError(task_id)
        if task.status == TaskStatus.RUNNING and task.session_id: self.adapter.cancel(task.session_id)
        return self.store.transition(task_id, TaskStatus.CANCELLED, data={"requested": True}) if task.status not in {TaskStatus.CANCELLED, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.BLOCKED} else task

    def run(self, task_id: str) -> Task:
        task = self.store.get(task_id)
        if task is None: raise KeyError(task_id)
        if task.status == TaskStatus.PENDING: task = self.store.transition(task_id, TaskStatus.VALIDATING)
        if task.status != TaskStatus.VALIDATING: return task
        try:
            evidence = self.freshness.validate(self.projects[task.project_id])
            task = self.store.transition(task_id, TaskStatus.QUEUED, data={"pie": evidence})
            task = self.store.transition(task_id, TaskStatus.RUNNING)
            execution = self.adapter.execute(task, self.projects[task.project_id], "Execute the server-defined read-only review. Do not alter files or invoke network/shell tools.")
            self.store.record_execution(task_id, session_id=execution.session_id, result=execution.result, metrics=execution.metrics)
            self.store.transition(task_id, TaskStatus.VERIFYING)
            return self.store.transition(task_id, TaskStatus.COMPLETED)
        except Exception as exc:
            return self.store.transition(task_id, TaskStatus.FAILED, error=str(exc))
