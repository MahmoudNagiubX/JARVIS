"""In-process scheduler for maintenance and proactive checks."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4


JobCallback = Callable[[], object | Awaitable[object]]


@dataclass(slots=True)
class ScheduledJob:
    job_id: str
    name: str
    interval_seconds: float
    callback: JobCallback
    next_run: datetime
    enabled: bool = True
    last_error: str | None = None


class BackgroundScheduler:
    """Simple cancellable scheduler with bounded callback execution."""

    def __init__(self) -> None:
        self.jobs: dict[str, ScheduledJob] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def add(self, name: str, interval_seconds: float, callback: JobCallback) -> str:
        if interval_seconds < 1:
            raise ValueError("scheduler interval must be at least one second")
        job_id = f"job-{uuid4()}"
        self.jobs[job_id] = ScheduledJob(job_id, name, interval_seconds, callback, datetime.now(UTC) + timedelta(seconds=interval_seconds))
        return job_id

    def remove(self, job_id: str) -> bool:
        return self.jobs.pop(job_id, None) is not None

    async def run_once(self, job_id: str) -> object:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        try:
            result = job.callback()
            if inspect.isawaitable(result):
                result = await result
            job.last_error = None
            job.next_run = datetime.now(UTC) + timedelta(seconds=job.interval_seconds)
            return result
        except Exception as exc:
            job.last_error = exc.__class__.__name__
            job.next_run = datetime.now(UTC) + timedelta(seconds=job.interval_seconds)
            raise

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            now = datetime.now(UTC)
            due = [job for job in self.jobs.values() if job.enabled and job.next_run <= now]
            for job in due:
                try:
                    await self.run_once(job.job_id)
                except Exception:
                    continue
            await asyncio.sleep(1)
