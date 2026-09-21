"""Tray façade whose state is always read from JarvisDesktopLifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Awaitable
from typing import Any, Callable

from .lifecycle import DesktopPhase, JarvisDesktopLifecycle


@dataclass(frozen=True, slots=True)
class TrayMenu:
    title: str
    items: tuple[str, ...] = (
        "Open JARVIS", "Pause Voice", "Resume Voice", "Mute Output",
        "Diagnostics", "Settings", "Restart JARVIS", "Quit",
    )


class TrayController:
    """Use pystray when installed; remain a safe no-op in test/headless hosts."""

    def __init__(
        self,
        lifecycle: JarvisDesktopLifecycle,
        *,
        open_callback: Callable[[], Any] | None = None,
        settings_callback: Callable[[], Any] | None = None,
        diagnostics_callback: Callable[[], Any] | None = None,
        run_async: Callable[[Awaitable[Any]], Any] | None = None,
    ) -> None:
        self.lifecycle = lifecycle
        self.open_callback = open_callback
        self.settings_callback = settings_callback
        self.diagnostics_callback = diagnostics_callback
        self.run_async = run_async
        self.menu = TrayMenu("JARVIS - Ready")
        self.icon: Any | None = None
        self.running = False

    @property
    def state_label(self) -> str:
        phase = self.lifecycle.status.phase
        return {
            DesktopPhase.READY: "Ready",
            DesktopPhase.PAUSED: "Offline",
            DesktopPhase.DEGRADED: "Degraded",
            DesktopPhase.STARTING: "Thinking",
            DesktopPhase.STOPPED: "Offline",
        }.get(phase, "Ready")

    def refresh(self) -> TrayMenu:
        self.menu = TrayMenu(f"JARVIS - {self.state_label}")
        return self.menu

    def invoke(self, item: str) -> Any:
        """Dispatch menu intent through the lifecycle; the tray owns no state."""

        if item == "Open JARVIS":
            if self.open_callback:
                return self.open_callback()
            return self.lifecycle.open_hud()
        if item == "Pause Voice":
            return self._run(self.lifecycle.pause_voice())
        if item == "Resume Voice":
            return self._run(self.lifecycle.resume_voice())
        if item == "Restart JARVIS":
            return self._run(self._restart())
        if item == "Quit":
            return self._run(self.lifecycle.stop())
        if item == "Mute Output":
            return self.lifecycle.status
        if item == "Diagnostics":
            if self.diagnostics_callback:
                return self.diagnostics_callback()
            return None
        if item == "Settings":
            if self.settings_callback:
                return self.settings_callback()
            return None
        return None

    async def _restart(self) -> Any:
        await self.lifecycle.stop()
        return await self.lifecycle.start()

    def _run(self, awaitable: Awaitable[Any]) -> Any:
        if self.run_async is None:
            return awaitable
        return self.run_async(awaitable)

    def start(self) -> None:
        self.running = True
        self.refresh()
        try:
            import pystray  # type: ignore[import-not-found]
            from PIL import Image, ImageDraw  # type: ignore[import-not-found]
        except ImportError:
            return
        image = Image.new("RGBA", (32, 32), (8, 11, 16, 255))
        ImageDraw.Draw(image).ellipse((4, 4, 28, 28), outline=(103, 232, 249, 255), width=2)
        menu = pystray.Menu(
            *(pystray.MenuItem(item, self._menu_callback(item)) for item in self.menu.items)
        )
        self.icon = pystray.Icon("JARVIS", image, self.menu.title, menu=menu)
        self.icon.run_detached()

    def _menu_callback(self, item: str) -> Callable[[Any, Any], Any]:
        def callback(_icon: Any, _menu_item: Any) -> Any:
            return self.invoke(item)

        return callback

    def stop(self) -> None:
        self.running = False
        if self.icon is not None:
            self.icon.stop()
            self.icon = None
