"""Reversible current-user, no-console Windows login startup."""

from __future__ import annotations

import os
import sys
from pathlib import Path


class UserStartupManager:
    """Use a hidden Windows Script Host launcher; no secrets are embedded."""

    def __init__(self, startup_dir: Path | None = None) -> None:
        if startup_dir is not None:
            self.startup_dir = Path(startup_dir)
        else:
            app_data = os.getenv("APPDATA", "").strip()
            base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
            self.startup_dir = base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        self.entry_path = self.startup_dir / "JARVIS.vbs"

    @staticmethod
    def pythonw_executable(executable: str | Path | None = None) -> Path:
        value = Path(executable or sys.executable).expanduser()
        if value.name.casefold() in {"python.exe", "python"}:
            return value.with_name("pythonw.exe")
        return value

    def command(self, executable: str | Path | None = None) -> tuple[str, ...]:
        return (str(self.pythonw_executable(executable)), "-m", "jarvis.desktop")

    def register(self, executable: str | Path | None = None, working_directory: str | Path | None = None) -> Path:
        self.startup_dir.mkdir(parents=True, exist_ok=True)
        pythonw, _, module = self.command(executable)
        workdir = str(Path(working_directory or Path.cwd()).expanduser().resolve())
        escaped_workdir = workdir.replace('"', '""')
        escaped_pythonw = str(pythonw).replace('"', '""')
        script = (
            'Set shell = CreateObject("WScript.Shell")\n'
            f'shell.CurrentDirectory = "{escaped_workdir}"\n'
            f'shell.Run """{escaped_pythonw}"" -m {module}", 0, False\n'
        )
        self.entry_path.write_text(script, encoding="utf-8")
        return self.entry_path

    def unregister(self) -> None:
        try:
            self.entry_path.unlink()
        except FileNotFoundError:
            pass

    def enabled(self) -> bool:
        return self.entry_path.is_file()
