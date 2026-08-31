"""Current-user single-instance lock for the desktop launcher."""

from __future__ import annotations

import os
from pathlib import Path


class SingleInstanceLock:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._handle: int | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._handle = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if self._stale():
                try:
                    self.path.unlink()
                except OSError:
                    return False
                return self.acquire()
            return False
        os.write(self._handle, str(os.getpid()).encode("ascii"))
        return True

    def _stale(self) -> bool:
        try:
            pid = int(self.path.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return True
        if pid == os.getpid():
            return False
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            return True
        return False

    def release(self) -> None:
        if self._handle is not None:
            os.close(self._handle)
            self._handle = None
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
