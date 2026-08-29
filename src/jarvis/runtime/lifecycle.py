"""Small explicit lifecycle supervisor for deployments and tests."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..bootstrap import JarvisRuntime


@dataclass(frozen=True, slots=True)
class LifecycleSnapshot:
    state: str
    started_at: str | None
    stopped_at: str | None
    uptime_seconds: float | None


class RuntimeLifecycle:
    """Make start/stop/status callable by a service host without side effects."""

    def __init__(self, runtime: JarvisRuntime) -> None:
        self.runtime = runtime
        self._started_at: datetime | None = None
        self._stopped_at: datetime | None = None
        self._started_monotonic: float | None = None

    async def start(self) -> LifecycleSnapshot:
        await self.runtime.start()
        if self._started_at is None:
            self._started_at = datetime.now(UTC)
            self._started_monotonic = time.monotonic()
        return self.snapshot()

    async def stop(self) -> LifecycleSnapshot:
        await self.runtime.shutdown()
        self._stopped_at = datetime.now(UTC)
        return self.snapshot()

    def snapshot(self) -> LifecycleSnapshot:
        uptime = None
        if self._started_monotonic is not None and self._stopped_at is None:
            uptime = max(0.0, time.monotonic() - self._started_monotonic)
        return LifecycleSnapshot(
            self.runtime.state.value,
            self._started_at.isoformat() if self._started_at else None,
            self._stopped_at.isoformat() if self._stopped_at else None,
            uptime,
        )
