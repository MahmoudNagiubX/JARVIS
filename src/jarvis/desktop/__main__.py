"""Normal product entry point: ``python -m jarvis.desktop``."""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
from collections.abc import Awaitable
from concurrent.futures import Future
from dataclasses import asdict
from typing import Any

from .diagnostics import DesktopDiagnostics
from .lifecycle import JarvisDesktopLifecycle
from .logging import DesktopOperationalLogger
from .tray import TrayController
from .ui import DesktopWindow


def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _submit(loop: asyncio.AbstractEventLoop, awaitable: Awaitable[Any]) -> Any:
    future: Future[Any] = asyncio.run_coroutine_threadsafe(awaitable, loop)  # type: ignore[arg-type]
    return future.result()


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the zero-touch JARVIS desktop product")
    parser.add_argument("--setup", action="store_true", help="explicitly run first-run setup")
    parser.add_argument("--diagnostics", action="store_true", help="print safe diagnostics and exit")
    parser.add_argument("--headless", action="store_true", help="start/check without opening a window")
    args = parser.parse_args()
    logger = DesktopOperationalLogger()
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=_run_loop, args=(loop,), name="jarvis-desktop-async", daemon=True)
    loop_thread.start()
    lifecycle = JarvisDesktopLifecycle(operational_logger=logger)
    submit = lambda awaitable: _submit(loop, awaitable)
    tray: TrayController | None = None
    window: DesktopWindow | None = None
    try:
        if args.setup:
            submit(lifecycle.setup())
        status = submit(lifecycle.start())
        if status.reason == "already_running":
            if args.headless:
                print(json.dumps({"phase": status.phase.value, "reason": status.reason}, ensure_ascii=False))
            else:
                lifecycle.open_existing_hud()
            return
        if args.diagnostics:
            results = submit(DesktopDiagnostics(lifecycle).run())
            print(json.dumps([asdict(item) for item in results], ensure_ascii=False))
            if lifecycle.runtime is not None:
                submit(lifecycle.stop())
            return
        if args.headless:
            print(json.dumps({"phase": status.phase.value, "reason": status.reason, "identity_id": status.identity_id, "device_id": status.device_id}, ensure_ascii=False))
            if lifecycle.runtime is not None:
                submit(lifecycle.stop())
            return
        tray = TrayController(lifecycle)
        tray.start()
        window = DesktopWindow(lifecycle, run_async=submit)
        if status.phase.value == "setup_required":
            if not window.show_setup(on_complete=lambda: submit(lifecycle.start())):
                return
            window.run()
        else:
            lifecycle.open_hud()
            if not window.run_background():
                return
    finally:
        if tray is not None:
            tray.stop()
        if window is not None:
            window.close()
        if lifecycle.runtime is not None:
            submit(lifecycle.stop())
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=5)
        loop.close()
        logger.close()


if __name__ == "__main__":
    main()
