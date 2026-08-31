"""Small first-run/status window that delegates state to the existing HUD."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any, Callable

from .diagnostics import DesktopDiagnostics
from .lifecycle import DesktopPhase, JarvisDesktopLifecycle


class DesktopWindow:
    """Dependency-light Tk window; the existing authenticated HUD remains primary."""

    def __init__(self, lifecycle: JarvisDesktopLifecycle, *, run_async: Callable[[Awaitable[Any]], Any] | None = None) -> None:
        self.lifecycle = lifecycle
        self.run_async = run_async or asyncio.run
        self.root: Any | None = None
        self.state_label: Any | None = None
        self.detail_label: Any | None = None
        self._build_error: Exception | None = None

    def _build(self) -> bool:
        try:
            import tkinter as tk
            from tkinter import ttk
        except Exception as exc:
            self._build_error = exc
            return False
        self.root = tk.Tk()
        self.root.title("JARVIS")
        self.root.geometry("540x420")
        self.root.configure(bg="#080b10")
        title = tk.Label(self.root, text="J.A.R.V.I.S.", fg="#67e8f9", bg="#080b10", font=("Consolas", 22, "bold"))
        title.pack(pady=(26, 8))
        self.state_label = tk.Label(self.root, text="STARTING", fg="#86efac", bg="#080b10", font=("Consolas", 18, "bold"))
        self.state_label.pack(pady=8)
        self.detail_label = tk.Label(self.root, text="", fg="#8aa0b4", bg="#080b10", justify="left", font=("Consolas", 11))
        self.detail_label.pack(pady=16)
        style = ttk.Style(self.root)
        style.configure("JARVIS.TButton", padding=8)
        return True

    def show_setup(self, on_complete: Callable[[], None] | None = None) -> bool:
        if not self._build():
            return False
        import tkinter as tk
        from tkinter import messagebox

        self.state_label.configure(text="SETUP REQUIRED")
        self.detail_label.configure(text="Core and local device setup\nwill be completed for this Windows user.")
        def complete() -> None:
            try:
                self.run_async(self.lifecycle.setup())
            except Exception as exc:
                messagebox.showerror("JARVIS setup", "Setup could not be completed safely.")
                self.detail_label.configure(text=f"Setup unavailable: {exc.__class__.__name__}")
                return
            if on_complete:
                on_complete()
            self.render()
        tk.Button(self.root, text="Finish Setup", command=complete, bg="#122637", fg="#d8e5ef", relief="flat").pack(pady=10)
        tk.Button(self.root, text="Diagnostics", command=self.show_diagnostics, bg="#101720", fg="#d8e5ef", relief="flat").pack(pady=4)
        return True

    def show_status(self) -> bool:
        if not self._build():
            return False
        import tkinter as tk

        tk.Button(self.root, text="Open JARVIS HUD", command=self.lifecycle.open_hud, bg="#122637", fg="#d8e5ef", relief="flat").pack(pady=8)
        tk.Button(self.root, text="Pause / Resume Voice", command=self._toggle_voice, bg="#101720", fg="#d8e5ef", relief="flat").pack(pady=4)
        tk.Button(self.root, text="Diagnostics", command=self.show_diagnostics, bg="#101720", fg="#d8e5ef", relief="flat").pack(pady=4)
        self.render()
        return True

    def _toggle_voice(self) -> None:
        try:
            if self.lifecycle.status.phase is DesktopPhase.PAUSED:
                self.run_async(self.lifecycle.resume_voice())
            else:
                self.run_async(self.lifecycle.pause_voice())
            self.render()
        except Exception:
            return

    def show_diagnostics(self) -> None:
        if self.root is None:
            return
        from tkinter import messagebox

        results = self.run_async(DesktopDiagnostics(self.lifecycle).run())
        messagebox.showinfo("JARVIS diagnostics", "\n".join(f"{item.name}: {item.status}" for item in results))

    def render(self) -> None:
        if self.state_label is None or self.detail_label is None:
            return
        status = self.lifecycle.status
        self.state_label.configure(text=status.phase.value.upper())
        self.detail_label.configure(text=(
            f"Brain       {'Ready' if status.brain_ready else 'Unavailable'}\n"
            f"Voice       {status.voice_state.title()}\n"
            f"Memory      {'Ready' if self.lifecycle.runtime is not None else 'Unavailable'}\n"
            f"Computer    {'Available' if self.lifecycle.runtime is not None else 'Unavailable'}\n\n"
            f"{status.reason}"
        ))

    def run(self) -> None:
        if self.root is not None:
            self.root.mainloop()

    def close(self) -> None:
        if self.root is not None:
            self.root.destroy()
            self.root = None
