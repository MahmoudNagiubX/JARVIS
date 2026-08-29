"""Bounded worker abstraction; external worker clients remain adapters."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


class WorkerCategory(StrEnum):
    CODING = "coding"
    RESEARCH = "research"
    BROWSER = "browser"
    ENGINEERING = "engineering"
    GENERAL_BACKGROUND = "general_background"


class WorkerStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class WorkerRequest:
    task: str
    category: WorkerCategory
    workspace_scope: str | None = None
    read_only: bool = True
    timeout_seconds: float = 60.0
    budget: int = 1
    context: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkerResult:
    worker_id: str
    status: WorkerStatus
    summary: str
    artifacts: tuple[str, ...] = ()
    changes: tuple[str, ...] = ()
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None


WorkerHandler = Callable[[WorkerRequest], Awaitable[WorkerResult]]


class LocalWorkerRuntime:
    """Runs one bounded worker task at a time and supports cancellation."""

    def __init__(self, handlers: dict[WorkerCategory, WorkerHandler] | None = None) -> None:
        self.handlers = dict(handlers or {})
        self._tasks: dict[str, asyncio.Task[WorkerResult]] = {}

    async def run(self, request: WorkerRequest) -> WorkerResult:
        worker_id = f"worker-{uuid4()}"
        started = datetime.now(UTC)
        handler = self.handlers.get(request.category)
        if handler is None:
            return WorkerResult(
                worker_id, WorkerStatus.FAILED, "worker adapter not configured",
                started_at=started, completed_at=datetime.now(UTC), error_code="worker_adapter_not_configured",
            )
        task = asyncio.create_task(handler(request))
        self._tasks[worker_id] = task
        try:
            result = await asyncio.wait_for(task, timeout=request.timeout_seconds)
            return result
        except asyncio.CancelledError:
            task.cancel()
            return WorkerResult(
                worker_id, WorkerStatus.CANCELLED, "worker cancelled",
                started_at=started, completed_at=datetime.now(UTC), error_code="cancelled",
            )
        except asyncio.TimeoutError:
            task.cancel()
            return WorkerResult(
                worker_id, WorkerStatus.CANCELLED, "worker timed out",
                started_at=started, completed_at=datetime.now(UTC), error_code="timeout",
            )
        except Exception as exc:
            return WorkerResult(
                worker_id, WorkerStatus.FAILED, "worker failed",
                started_at=started, completed_at=datetime.now(UTC), error_code=exc.__class__.__name__,
            )
        finally:
            self._tasks.pop(worker_id, None)

    def cancel(self, worker_id: str) -> bool:
        task = self._tasks.get(worker_id)
        if task is None:
            return False
        task.cancel()
        return True
