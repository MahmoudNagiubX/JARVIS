"""Reversible current-user, no-console Windows login startup."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class UserStartupManager:
    """Use a hidden Windows Script Host launcher; no secrets are embedded."""

    def __init__(self, startup_dir: Path | None = None) -> None:
        if startup_dir is not None:
            self.startup_dir = Path(startup_dir)
            self.start_menu_dir = self.startup_dir.parent / "Programs"
        else:
            app_data = os.getenv("APPDATA", "").strip()
            base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
            self.startup_dir = base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
            self.start_menu_dir = self.startup_dir.parent
        self.entry_path = self.startup_dir / "JARVIS.vbs"
        self.shortcut_path = self.start_menu_dir / "JARVIS.lnk"
        self.last_shortcut_spec: dict[str, str | int] | None = None

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

    def shortcut_spec(self, executable: str | Path | None = None, working_directory: str | Path | None = None) -> dict[str, str | int]:
        target = str(self.pythonw_executable(executable).expanduser().resolve())
        workdir = str(Path(working_directory or Path.cwd()).expanduser().resolve())
        return {
            "target": target,
            "arguments": "-m jarvis.desktop",
            "working_directory": workdir,
            "window_style": 0,
        }

    def install_start_menu_shortcut(
        self,
        executable: str | Path | None = None,
        working_directory: str | Path | None = None,
    ) -> Path:
        """Create the current-user ``JARVIS.lnk`` through Windows Script Host."""

        if os.name != "nt":
            raise RuntimeError("Start Menu shortcuts require Windows")
        spec = self.shortcut_spec(executable, working_directory)
        cscript = shutil.which("cscript.exe") or shutil.which("cscript")
        if not cscript:
            raise RuntimeError("Windows Script Host is unavailable")
        self.start_menu_dir.mkdir(parents=True, exist_ok=True)
        self.shortcut_path.unlink(missing_ok=True)
        script = (
            'Set shell = CreateObject("WScript.Shell")\n'
            f'set shortcut = shell.CreateShortcut("{_vbs_escape(str(self.shortcut_path.resolve()))}")\n'
            f'shortcut.TargetPath = "{_vbs_escape(str(spec["target"]))}"\n'
            f'shortcut.Arguments = "{_vbs_escape(str(spec["arguments"]))}"\n'
            f'shortcut.WorkingDirectory = "{_vbs_escape(str(spec["working_directory"]))}"\n'
            f'shortcut.WindowStyle = {spec["window_style"]}\n'
            'shortcut.Save\n'
        )
        with tempfile.NamedTemporaryFile(prefix="jarvis-shortcut-", suffix=".vbs", mode="w", encoding="utf-8", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(script)
            handle.flush()
        try:
            completed = subprocess.run(
                [cscript, "//NoLogo", str(temporary)],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                **_hidden_process_kwargs(),
            )
        finally:
            temporary.unlink(missing_ok=True)
        if completed.returncode != 0 or not self.shortcut_path.is_file():
            raise RuntimeError("JARVIS Start Menu shortcut could not be created")
        self.last_shortcut_spec = spec
        return self.shortcut_path

    def uninstall_start_menu_shortcut(self) -> None:
        self.shortcut_path.unlink(missing_ok=True)
        self.last_shortcut_spec = None

    def shortcut_enabled(self) -> bool:
        return self.shortcut_path.is_file()


def _vbs_escape(value: str) -> str:
    return value.replace('"', '""')


def _hidden_process_kwargs() -> dict[str, int]:
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
