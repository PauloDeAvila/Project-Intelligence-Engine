from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"


TERMINAL = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.BLOCKED}
TRANSITIONS = {
    TaskStatus.PENDING: {TaskStatus.VALIDATING, TaskStatus.CANCELLED},
    TaskStatus.VALIDATING: {TaskStatus.QUEUED, TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.QUEUED: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.WAITING_APPROVAL},
    TaskStatus.RUNNING: {TaskStatus.VERIFYING, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.BLOCKED},
    TaskStatus.VERIFYING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.BLOCKED},
    TaskStatus.WAITING_APPROVAL: {TaskStatus.QUEUED, TaskStatus.CANCELLED},
}


@dataclass(frozen=True)
class Task:
    id: str
    source: str
    project_id: str
    task_type: str
    model: str
    status: TaskStatus
    priority: int
    created_at: int
    updated_at: int
    timeout_seconds: int
    token_limit: int | None
    cost_limit: float | None
    session_id: str | None
    result: dict[str, Any] | None
    metrics: dict[str, Any] | None
    error: str | None

