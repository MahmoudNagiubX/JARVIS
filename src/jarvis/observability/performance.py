"""Dependency-free process and operation measurements for acceptance runs."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PerformanceSnapshot:
    wall_time: float
    process_time: float
    pid: int
    resident_bytes: int | None

    def as_dict(self) -> dict[str, object]:
        return {
            "wall_time": self.wall_time,
            "process_time": self.process_time,
            "pid": self.pid,
            "resident_bytes": self.resident_bytes,
        }


class PerformanceProfiler:
    """Use standard-library clocks; memory is unavailable without psutil on Windows."""

    @staticmethod
    def snapshot() -> PerformanceSnapshot:
        resident = None
        try:
            import resource

            resident = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            if os.name != "nt":
                resident *= 1024
        except (ImportError, AttributeError, OSError):
            pass
        return PerformanceSnapshot(time.perf_counter(), time.process_time(), os.getpid(), resident)

    @classmethod
    def measure(cls, operation: Callable[[], T]) -> tuple[T, dict[str, float]]:
        started = cls.snapshot()
        result = operation()
        finished = cls.snapshot()
        return result, {
            "wall_ms": (finished.wall_time - started.wall_time) * 1000,
            "process_ms": (finished.process_time - started.process_time) * 1000,
        }
