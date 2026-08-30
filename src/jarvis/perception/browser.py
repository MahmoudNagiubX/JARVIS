"""Structural browser perception bridge; it never rasterizes a browser screen."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ..contracts import BrowserAction, DeviceIdentity, Identity, ScreenObservation, VisualElement


class BrowserDomPerceptionBridge:
    """Reuse BrowserActionService's bounded DOM/text result for managed sessions."""

    name = "browser-dom"

    def __init__(self, browser_actions: object) -> None:
        self.browser_actions = browser_actions

    async def observe(self, identity: Identity, device: DeviceIdentity, session_id: str) -> ScreenObservation:
        result = await self.browser_actions.execute(
            BrowserAction("read_page", {"session_id": session_id}), identity, device,
            session_id=f"perception-{session_id}", correlation_id=f"perception-{uuid4()}",
        )
        if result.status != "succeeded":
            raise RuntimeError(result.error_code or "browser_dom_unavailable")
        output = dict(result.output)
        headings = output.get("headings") if isinstance(output.get("headings"), (list, tuple)) else ()
        elements = tuple(
            VisualElement("heading", str(item)[:300], source=self.name, confidence=1.0)
            for item in headings[:100]
        )
        return ScreenObservation(
            f"observation-{uuid4()}", device.device_id, datetime.now(UTC), self.name,
            active_window=output.get("title") if isinstance(output.get("title"), str) else None,
            text=output.get("text")[:16_000] if isinstance(output.get("text"), str) else None,
            elements=elements, raw_retained=False, confidence=1.0,
            metadata={"url": output.get("url"), "session_id": session_id, "source": self.name},
        )
