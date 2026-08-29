"""Browser automation with a dependency-free deterministic fallback."""

from __future__ import annotations

import asyncio
import inspect
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from uuid import uuid4

from ..authority.approvals.service import DurableApprovalEngine
from ..authority.audit.service import DurableAuditService
from ..authority.permissions.engine import PolicyPermissionEngine
from ..bus import InMemoryEventBus
from ..contracts import ApprovalRequest, AuditRecord, BrowserAction, BrowserCapability, BrowserResult, BrowserSession, DeviceIdentity, Identity, ToolContext
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.links: list[dict[str, str]] = []
        self.headings: list[str] = []
        self._link: dict[str, str] | None = None
        self._heading = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self._link = {"href": values["href"] or ""}
        if tag in {"h1", "h2", "h3"}:
            self._heading = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._link = None
        if tag in {"h1", "h2", "h3"}:
            self._heading = False

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        self.text.append(value)
        if self._heading and len(self.headings) < 100:
            self.headings.append(value)
        if self._link is not None and len(self.links) < 100:
            self._link["text"] = value
            self.links.append(dict(self._link))


class LocalBrowserController:
    """Use urllib and HTML parsing for bounded read-only browser actions."""

    def __init__(self, fetcher: Callable[[str], tuple[str, str]] | None = None) -> None:
        self._fetcher = fetcher
        self._sessions: dict[str, BrowserSession] = {}

    async def execute(self, action: BrowserAction, context: ToolContext) -> BrowserResult:
        if context.device is None:
            return BrowserResult("denied", error_code="device_missing")
        try:
            capability = BrowserCapability(action.action)
        except ValueError:
            return BrowserResult("denied", error_code="unsupported_browser_action")
        if capability is BrowserCapability.OPEN_URL:
            return self._open_url(action.parameters, context)
        session = self._session(action.parameters, context)
        if session is None:
            return BrowserResult("failed", error_code="browser_session_missing")
        if capability is BrowserCapability.NAVIGATE:
            return self._navigate(session, action.parameters)
        if capability is BrowserCapability.BACK:
            return self._back(session)
        if capability is BrowserCapability.FORWARD:
            return self._forward(session)
        if capability in {BrowserCapability.READ_PAGE, BrowserCapability.EXTRACT_TEXT, BrowserCapability.INSPECT_ACCESSIBILITY_TREE}:
            return await self._read(session, capability)
        if capability is BrowserCapability.TABS:
            return BrowserResult("succeeded", {"tabs": [self._session_data(item) for item in self._sessions.values()]}, verified=True)
        if capability is BrowserCapability.FIND_ELEMENT:
            return await self._find(session, action.parameters)
        if capability in {BrowserCapability.CLICK, BrowserCapability.TYPE, BrowserCapability.SELECT}:
            return BrowserResult("failed", error_code="dom_interaction_requires_playwright")
        if capability in {BrowserCapability.DOWNLOAD_FILE, BrowserCapability.UPLOAD_FILE, BrowserCapability.SCREENSHOT}:
            return BrowserResult("failed", error_code="browser_action_requires_configured_adapter")
        return BrowserResult("failed", error_code="browser_action_not_configured")

    def _open_url(self, parameters: Mapping[str, object], context: ToolContext) -> BrowserResult:
        url = parameters.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return BrowserResult("denied", error_code="url_scheme_not_allowed")
        session = BrowserSession(f"browser-{uuid4()}", context.identity.owner_id if context.identity else context.device.owner_id, context.device.device_id, url, (url,))
        self._sessions[session.session_id] = session
        return BrowserResult("succeeded", {"session_id": session.session_id, "url": url}, verified=True)

    def _session(self, parameters: Mapping[str, object], context: ToolContext) -> BrowserSession | None:
        session_id = parameters.get("session_id")
        if not isinstance(session_id, str):
            return None
        session = self._sessions.get(session_id)
        if session is None or not session.active or session.device_id != context.device.device_id:
            return None
        return session

    def _navigate(self, session: BrowserSession, parameters: Mapping[str, object]) -> BrowserResult:
        url = parameters.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return BrowserResult("denied", error_code="url_scheme_not_allowed")
        history = session.history + (url,)
        updated = BrowserSession(session.session_id, session.owner_id, session.device_id, url, history)
        self._sessions[session.session_id] = updated
        return BrowserResult("succeeded", {"session_id": session.session_id, "url": url}, verified=True)

    def _back(self, session: BrowserSession) -> BrowserResult:
        if len(session.history) < 2:
            return BrowserResult("failed", error_code="browser_history_empty")
        updated = BrowserSession(session.session_id, session.owner_id, session.device_id, session.history[-2], session.history[:-1])
        self._sessions[session.session_id] = updated
        return BrowserResult("succeeded", {"url": updated.current_url}, verified=True)

    @staticmethod
    def _forward(session: BrowserSession) -> BrowserResult:
        del session
        return BrowserResult("failed", error_code="browser_forward_not_available_in_local_adapter")

    async def _read(self, session: BrowserSession, capability: BrowserCapability) -> BrowserResult:
        if session.current_url is None:
            return BrowserResult("failed", error_code="browser_url_missing")
        try:
            html, final_url = await asyncio.to_thread(self._fetch, session.current_url)
        except (OSError, urllib.error.URLError, ValueError) as exc:
            return BrowserResult("failed", error_code=f"page_fetch_failed:{exc.__class__.__name__}")
        parser = _PageParser()
        parser.feed(html)
        output: dict[str, object] = {"session_id": session.session_id, "url": final_url, "text": " ".join(parser.text)[:20000], "title": parser.headings[0] if parser.headings else None}
        if capability is BrowserCapability.INSPECT_ACCESSIBILITY_TREE:
            output["accessibility_tree"] = {"headings": parser.headings, "links": parser.links}
        if capability is BrowserCapability.READ_PAGE:
            output["links"] = parser.links
        self._sessions[session.session_id] = BrowserSession(session.session_id, session.owner_id, session.device_id, final_url, session.history + ((final_url,) if final_url != session.current_url else ()))
        return BrowserResult("succeeded", output, verified=True)

    async def _find(self, session: BrowserSession, parameters: Mapping[str, object]) -> BrowserResult:
        needle = parameters.get("text") or parameters.get("selector")
        if not isinstance(needle, str) or not needle.strip():
            return BrowserResult("denied", error_code="element_query_required")
        page = await self._read(session, BrowserCapability.READ_PAGE)
        if page.status != "succeeded":
            return page
        links = [link for link in page.output.get("links", []) if needle.casefold() in str(link).casefold()]
        return BrowserResult("succeeded", {"matches": links[:50]}, verified=True)

    def _fetch(self, url: str) -> tuple[str, str]:
        if self._fetcher is not None:
            return self._fetcher(url)
        request = urllib.request.Request(url, headers={"User-Agent": "JARVIS-local-browser/1"})
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise ValueError("page_too_large")
            return body.decode("utf-8", errors="replace"), response.geturl()

    @staticmethod
    def _session_data(session: BrowserSession) -> dict[str, object]:
        return {"session_id": session.session_id, "url": session.current_url, "device_id": session.device_id, "active": session.active}


class PlaywrightBrowserController:
    """JARVIS-owned boundary for an injected Playwright MCP/client adapter."""

    def __init__(self, executor: Callable[[BrowserAction, ToolContext], BrowserResult | Awaitable[BrowserResult]] | None = None) -> None:
        self._executor = executor

    async def execute(self, action: BrowserAction, context: ToolContext) -> BrowserResult:
        if self._executor is None:
            return BrowserResult("failed", error_code="playwright_adapter_not_configured")
        result = self._executor(action, context)
        if inspect.isawaitable(result):
            result = await result
        return result


class BrowserActionService:
    """Apply common authority, audit, and event behavior to browser actions."""

    _read_actions = frozenset({item.value for item in (BrowserCapability.OPEN_URL, BrowserCapability.NAVIGATE, BrowserCapability.BACK, BrowserCapability.FORWARD, BrowserCapability.READ_PAGE, BrowserCapability.INSPECT_ACCESSIBILITY_TREE, BrowserCapability.FIND_ELEMENT, BrowserCapability.EXTRACT_TEXT, BrowserCapability.TABS)})

    def __init__(self, controller: LocalBrowserController | PlaywrightBrowserController, repository: RuntimeRepository, event_bus: InMemoryEventBus, permission: PolicyPermissionEngine, audit: DurableAuditService, approvals: DurableApprovalEngine | None = None) -> None:
        self.controller = controller
        self.repository = repository
        self.event_bus = event_bus
        self.permission = permission
        self.audit = audit
        self.approvals = approvals
        self._pending: dict[str, tuple[BrowserAction, Identity, DeviceIdentity]] = {}

    async def execute(self, action: BrowserAction, identity: Identity, device: DeviceIdentity, *, session_id: str = "browser", correlation_id: str | None = None) -> BrowserResult:
        correlation = correlation_id or f"browser-{uuid4()}"
        required_capability = f"browser.{action.action}"
        risk = "read" if action.action in self._read_actions else "consequential"
        decision = await self.permission.evaluate(identity, device, required_capability, {"required_scope": "tool.request", "required_capabilities": frozenset({required_capability}), "risk_level": risk})
        if decision.effect.value != "allow":
            await self.audit.record(AuditRecord(f"audit-{uuid4()}", "browser.permission_denied", datetime.now(UTC), identity.identity_id, device.device_id, correlation, decision.effect.value, decision.reason_code, {"action": action.action}))
            if decision.effect.value == "require_approval" and self.approvals is not None:
                approval_id = f"approval-{uuid4()}"
                await self.approvals.request(ApprovalRequest(approval_id, required_capability, identity.owner_id, device.device_id, "browser action requires approval", datetime.now(UTC), datetime.now(UTC) + timedelta(minutes=10), {"action": action.action, "parameters": dict(action.parameters)}))
                self._pending[approval_id] = (action, identity, device)
                await self._emit("browser.action_requested", identity.owner_id, correlation, {"action": action.action, "approval_id": approval_id}, EventState.ACCEPTED)
                return BrowserResult("approval_required", error_code=decision.reason_code, approval_id=approval_id)
            await self._emit("browser.action_failed", identity.owner_id, correlation, {"action": action.action, "reason": decision.reason_code}, EventState.FAILED)
            return BrowserResult("approval_required" if decision.effect.value == "require_approval" else "denied", error_code=decision.reason_code)
        return await self._execute_controller(action, identity, device, session_id, correlation)

    async def decide(self, approval_id: str, approved: bool, decided_by: str) -> BrowserResult:
        pending = self._pending.get(approval_id)
        if pending is None or self.approvals is None:
            raise KeyError(approval_id)
        action, identity, device = pending
        decision = await self.approvals.decide(approval_id, approved, decided_by)
        self._pending.pop(approval_id, None)
        if decision.status.value != "approved":
            return BrowserResult("denied", error_code=decision.status.value, approval_id=approval_id)
        return await self._execute_controller(action, identity, device, "browser", f"browser-{approval_id}", approval_id)

    async def _execute_controller(self, action: BrowserAction, identity: Identity, device: DeviceIdentity, session_id: str, correlation: str, approval_id: str | None = None) -> BrowserResult:
        await self._emit("browser.action_started", identity.owner_id, correlation, {"action": action.action}, EventState.ACCEPTED)
        result = await self.controller.execute(action, ToolContext(identity, device, session_id, correlation))
        if action.action == BrowserCapability.OPEN_URL.value and result.status == "succeeded":
            await self._emit(
                "browser.session_started", identity.owner_id, correlation,
                {"session_id": result.output.get("session_id"), "url": result.output.get("url")},
                EventState.COMPLETED,
            )
        event_type = "browser.action_completed" if result.status == "succeeded" else "browser.action_failed"
        await self._emit(event_type, identity.owner_id, correlation, {"action": action.action, "error_code": result.error_code}, EventState.COMPLETED if result.status == "succeeded" else EventState.FAILED)
        await self.audit.record(AuditRecord(f"audit-{uuid4()}", event_type, datetime.now(UTC), identity.identity_id, device.device_id, correlation, result.status, result.error_code, {"action": action.action}))
        return BrowserResult(result.status, result.output, result.error_code, result.verified, approval_id)

    async def _emit(self, event_type: str, owner_id: str, correlation: str, payload: dict[str, object], state: EventState) -> None:
        event = Event.create(event_type, EventCategory.BROWSER, correlation_id=correlation, actor_id=owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
