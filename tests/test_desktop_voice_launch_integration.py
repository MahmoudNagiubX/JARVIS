from __future__ import annotations

import asyncio
import sys
import threading
import types
import tomllib
from types import SimpleNamespace
from unittest.mock import AsyncMock
from pathlib import Path

from jarvis.desktop.lifecycle import JarvisDesktopLifecycle
from jarvis.desktop.tray import TrayController
from jarvis.desktop.ui import DesktopWindow
from jarvis.models.llama_runtime import LlamaRuntimeState, LlamaRuntimeStatus


def test_desktop_extra_declares_real_tray_runtime() -> None:
    project = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with project.open("rb") as handle:
        optional = tomllib.load(handle)["project"]["optional-dependencies"]

    assert "pystray==0.19.5" in optional["desktop"]
    assert "Pillow>=10,<13" in optional["desktop"]


def test_hybrid_desktop_readiness_uses_authoritative_runtime_supervisor() -> None:
    status = LlamaRuntimeStatus(
        LlamaRuntimeState.READY,
        "llama_cpp",
        True,
        "Qwen3.5-4B-Heretic",
        True,
        "ready",
    )
    runtime_health = AsyncMock(return_value=status)
    provider_health = AsyncMock(side_effect=AssertionError("provider health is not runtime ownership"))
    runtime = SimpleNamespace(
        config=SimpleNamespace(model_provider="hybrid"),
        models=SimpleNamespace(
            runtime_supervisor=object(),
            runtime_health=runtime_health,
            health=provider_health,
        ),
    )

    observed, ready = asyncio.run(JarvisDesktopLifecycle()._model_status(runtime))

    assert observed is status
    assert ready is True
    runtime_health.assert_awaited_once_with()
    provider_health.assert_not_awaited()


def test_native_window_build_is_idempotent_and_reuses_root(monkeypatch) -> None:
    created: list[object] = []

    class FakeRoot:
        def title(self, _value):
            pass

        def geometry(self, _value):
            pass

        def configure(self, **_kwargs):
            pass

    class FakeLabel:
        def __init__(self, *_args, **_kwargs):
            pass

        def pack(self, **_kwargs):
            pass

    class FakeFrame(FakeLabel):
        pass

    class FakeStyle:
        def __init__(self, *_args, **_kwargs):
            pass

        def configure(self, *_args, **_kwargs):
            pass

    def make_root():
        root = FakeRoot()
        created.append(root)
        return root

    fake_tk = types.ModuleType("tkinter")
    fake_tk.Tk = make_root
    fake_tk.Label = FakeLabel
    fake_tk.Frame = FakeFrame
    fake_ttk = types.ModuleType("tkinter.ttk")
    fake_ttk.Style = FakeStyle
    monkeypatch.setitem(sys.modules, "tkinter", fake_tk)
    monkeypatch.setitem(sys.modules, "tkinter.ttk", fake_ttk)

    window = DesktopWindow(SimpleNamespace())
    assert window._build() is True
    first = window.root
    assert window._build() is True

    assert window.root is first
    assert len(created) == 1


def test_native_window_settings_restores_and_focuses_existing_root() -> None:
    class FakeRoot:
        def __init__(self):
            self.calls: list[str] = []

        def deiconify(self):
            self.calls.append("deiconify")

        def lift(self):
            self.calls.append("lift")

        def focus_force(self):
            self.calls.append("focus_force")

    root = FakeRoot()
    window = DesktopWindow(SimpleNamespace())
    window.root = root
    window._build = lambda: True
    window._render_product_panel = lambda **_kwargs: None

    assert window.show_status() is True
    assert root.calls == ["deiconify", "lift", "focus_force"]


def test_native_window_settings_from_tray_thread_is_queued_on_same_root() -> None:
    class FakeRoot:
        def __init__(self):
            self.queued: list[object] = []

        def after(self, _delay, callback):
            self.queued.append(callback)

    root = FakeRoot()
    rendered: list[bool] = []
    window = DesktopWindow(SimpleNamespace())
    window.root = root
    window._ui_thread_id = threading.get_ident() + 1
    window._build = lambda: True
    window._render_product_panel = lambda **_kwargs: rendered.append(True)

    assert window.show_status() is True
    assert rendered == []
    assert len(root.queued) == 1

    window._ui_thread_id = threading.get_ident()
    root.queued[0]()
    assert rendered == [True]


def test_tray_dispatches_settings_and_diagnostics_callbacks() -> None:
    calls: list[str] = []
    tray = TrayController(
        SimpleNamespace(status=SimpleNamespace(phase="ready")),
        settings_callback=lambda: calls.append("settings"),
        diagnostics_callback=lambda: calls.append("diagnostics"),
    )

    tray.invoke("Settings")
    tray.invoke("Diagnostics")

    assert calls == ["settings", "diagnostics"]


def test_tray_attaches_all_menu_items_to_pystray(monkeypatch) -> None:
    class FakeMenuItem:
        def __init__(self, text, action):
            assert action.__code__.co_argcount == 2
            self.text = text
            self.action = action

    class FakeMenu:
        def __init__(self, *items):
            self.items = items

    class FakeIcon:
        def __init__(self, *args, **kwargs):
            self.menu = kwargs.get("menu")
            if self.menu is None and len(args) > 3:
                self.menu = args[3]

        def run_detached(self):
            pass

        def stop(self):
            pass

    fake_pystray = types.ModuleType("pystray")
    fake_pystray.MenuItem = FakeMenuItem
    fake_pystray.Menu = FakeMenu
    fake_pystray.Icon = FakeIcon
    monkeypatch.setitem(sys.modules, "pystray", fake_pystray)

    class FakeImage:
        @staticmethod
        def new(*_args, **_kwargs):
            return object()

    class FakeDraw:
        def ellipse(self, *_args, **_kwargs):
            pass

    fake_image = types.ModuleType("PIL.Image")
    fake_image.new = FakeImage.new
    fake_draw_module = types.ModuleType("PIL.ImageDraw")
    fake_draw_module.Draw = lambda _image: FakeDraw()
    fake_pil = types.ModuleType("PIL")
    fake_pil.Image = fake_image
    fake_pil.ImageDraw = fake_draw_module
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_image)
    monkeypatch.setitem(sys.modules, "PIL.ImageDraw", fake_draw_module)

    calls: list[str] = []
    lifecycle = SimpleNamespace(status=SimpleNamespace(phase="ready"))
    tray = TrayController(lifecycle, settings_callback=lambda: calls.append("settings"))
    tray.start()

    assert tray.icon is not None
    assert tuple(item.text for item in tray.icon.menu.items) == tray.menu.items
    settings_item = next(item for item in tray.icon.menu.items if item.text == "Settings")
    settings_item.action(tray.icon, settings_item)
    assert calls == ["settings"]
