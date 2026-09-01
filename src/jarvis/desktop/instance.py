"""Current-user single-instance lock for the desktop launcher."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


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

    def publish_metadata(self, **metadata: str) -> None:
        """Publish non-secret handoff data while retaining the PID first line."""

        if self._handle is None:
            return
        payload = json.dumps({"pid": os.getpid(), **metadata}, separators=(",", ":"))
        encoded = f"{os.getpid()}\n{payload}".encode("utf-8")
        os.lseek(self._handle, 0, os.SEEK_SET)
        os.ftruncate(self._handle, 0)
        os.write(self._handle, encoded)
        os.fsync(self._handle)

    def metadata(self) -> dict[str, Any]:
        """Read the current instance's non-secret handoff metadata."""

        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            payload = json.loads(lines[1]) if len(lines) > 1 else {}
        except (OSError, ValueError, IndexError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _stale(self) -> bool:
        try:
            pid = int(self.path.read_text(encoding="ascii").splitlines()[0].strip())
        except (OSError, ValueError, IndexError):
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
