"""Browser automation with a dependency-free deterministic fallback."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import re
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin
from uuid import uuid4

from ..authority.approvals.service import DurableApprovalEngine
from ..authority.audit.service import DurableAuditService
from ..authority.permissions.engine import PolicyPermissionEngine
from ..bus import InMemoryEventBus
from ..contracts import ApprovalRequest, AuditRecord, BrowserAction, BrowserCapability, BrowserResult, BrowserSession, BrowserSessionMode, DeviceIdentity, Identity, ToolContext
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from .policy import BrowserURLPolicy, BrowserURLPolicyError
from .playwright_adapter import PlaywrightBrowserController


class _PageParser(HTMLParser):
    _IGNORED_TAGS = frozenset({"script", "style", "noscript", "template"})
    _VOID_TAGS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"})
    _MAX_TEXT_CHARS = 20_000
    _MAX_HEADINGS = 100
    _MAX_LINKS = 100
    _MAX_METADATA = 20

    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.links: list[dict[str, str]] = []
        self.headings: list[str] = []
        self.metadata: dict[str, str] = {}
        self._link: dict[str, str] | None = None
        self._link_text: list[str] = []
        self._heading_tag: str | None = None
        self._heading_text: list[str] = []
        self._title_depth = 0
        self._title_text: list[str] = []
        self._main_depth = 0
        self._main_text: list[str] = []
        self._suppression_stack: list[bool] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        suppressed = bool(self._suppression_stack and self._suppression_stack[-1]) or tag in self._IGNORED_TAGS or "hidden" in values or values.get("aria-hidden", "").casefold() == "true"
        if tag in self._VOID_TAGS:
            if not suppressed and tag == "meta" and len(self.metadata) < self._MAX_METADATA:
                key = (values.get("name") or values.get("property") or "").casefold().strip()
                content = (values.get("content") or "").strip()
                if key in {"description", "og:title", "og:description", "author"} and content:
                    self.metadata[key] = content[:500]
            return
        self._suppression_stack.append(suppressed)
        if suppressed:
            return
        if tag == "a" and values.get("href") and len(self.links) < self._MAX_LINKS:
            self._link = {"href": (values["href"] or "")[:4_096]}
            self._link_text = []
        if tag in {"h1", "h2", "h3"} and self._heading_tag is None:
            self._heading_tag = tag
            self._heading_text = []
        if tag == "title":
            self._title_depth += 1
        if tag == "main":
            self._main_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self._suppression_stack:
            return
        suppressed = self._suppression_stack.pop()
        if suppressed:
            return
        if tag == "a" and self._link is not None:
            if len(self.links) < self._MAX_LINKS:
                self._link["text"] = " ".join(self._link_text).strip()[:200]
                self.links.append(self._link)
            self._link = None
            self._link_text = []
        if tag == self._heading_tag:
            heading = " ".join(self._heading_text).strip()
            if heading and len(self.headings) < self._MAX_HEADINGS:
                self.headings.append(heading[:500])
            self._heading_tag = None
            self._heading_text = []
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
        if tag == "main" and self._main_depth:
            self._main_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._suppression_stack and self._suppression_stack[-1]:
            return
        value = " ".join(data.split())
        if not value:
            return
        self.text.append(value)
        if self._main_depth:
            self._main_text.append(value)
        if self._heading_tag is not None:
            self._heading_text.append(value)
        if self._title_depth:
            self._title_text.append(value)
        if self._link is not None:
            self._link_text.append(value)

    @property
    def title(self) -> str:
        return " ".join(self._title_text).strip()[:500]

    @property
    def main_text(self) -> str:
        return " ".join(self._main_text).strip()[: self._MAX_TEXT_CHARS]


class _ElementParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if len(self.elements) < 500:
            self.elements.append((tag.casefold(), {key.casefold(): value or "" for key, value in attrs}))


class LocalBrowserController:
    """Use urllib and HTML parsing for bounded read-only browser actions."""

    _MAX_BODY_BYTES = 2_000_000
    _MAX_TEXT_CHARS = 20_000
    _MAX_LINKS = 100
    _MAX_HEADINGS = 100
    _MAX_METADATA = 20

    def __init__(self, fetcher: Callable[[str], tuple[str, str]] | None = None, *, interaction_timeout_seconds: float = 10.0, url_policy: BrowserURLPolicy | None = None) -> None:
        self._fetcher = fetcher
        self._url_policy = url_policy or BrowserURLPolicy()
        self._sessions: dict[str, BrowserSession] = {}
        self._form_values: dict[tuple[str, str], str] = {}
        self._interaction_timeout_seconds = max(0.05, min(interaction_timeout_seconds, 30.0))

    async def execute(self, action: BrowserAction, context: ToolContext, *, session_mode: BrowserSessionMode = BrowserSessionMode.EPHEMERAL) -> BrowserResult:
        if context.device is None:
            return BrowserResult("denied", error_code="device_missing")
        if not isinstance(session_mode, BrowserSessionMode):
            return BrowserResult("denied", error_code="browser_session_mode_invalid")
        if session_mode is BrowserSessionMode.OWNER_PERSISTENT:
            return BrowserResult("failed", error_code="browser_persistent_requires_playwright")
        try:
            capability = BrowserCapability(action.action)
        except ValueError:
            return BrowserResult("denied", error_code="unsupported_browser_action")
        if capability is BrowserCapability.OPEN_URL:
            return self._open_url(action.parameters, context, session_mode)
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
            return await self._interact(session, capability, action.parameters)
        if capability in {BrowserCapability.DOWNLOAD_FILE, BrowserCapability.UPLOAD_FILE, BrowserCapability.SCREENSHOT}:
            return BrowserResult("failed", error_code="browser_action_requires_configured_adapter")
        return BrowserResult("failed", error_code="browser_action_not_configured")

    def _open_url(self, parameters: Mapping[str, object], context: ToolContext, session_mode: BrowserSessionMode) -> BrowserResult:
        url = parameters.get("url")
        if not isinstance(url, str):
            return BrowserResult("denied", error_code="url_invalid")
        try:
            self._validate_url(url)
        except BrowserURLPolicyError as exc:
            return BrowserResult("denied", error_code=exc.code)
        session = BrowserSession(
            f"browser-{uuid4()}",
            context.identity.owner_id if context.identity else context.device.owner_id,
            context.device.device_id,
            url,
            (url,),
            True,
            session_mode,
        )
        self._sessions[session.session_id] = session
        return BrowserResult("succeeded", {"session_id": session.session_id, "url": url}, verified=True)

    def _session(self, parameters: Mapping[str, object], context: ToolContext) -> BrowserSession | None:
        session_id = parameters.get("session_id")
        if not isinstance(session_id, str):
            return None
        session = self._sessions.get(session_id)
        if (
            session is None
            or not session.active
            or session.device_id != context.device.device_id
            or context.identity is None
            or session.owner_id != context.identity.owner_id
        ):
            return None
        return session

    def _navigate(self, session: BrowserSession, parameters: Mapping[str, object]) -> BrowserResult:
        url = parameters.get("url")
        if not isinstance(url, str):
            return BrowserResult("denied", error_code="url_invalid")
        try:
            self._validate_url(url)
        except BrowserURLPolicyError as exc:
            return BrowserResult("denied", error_code=exc.code)
        history = session.history + (url,)
        updated = replace(session, current_url=url, history=history)
        self._sessions[session.session_id] = updated
        return BrowserResult("succeeded", {"session_id": session.session_id, "url": url}, verified=True)

    def _back(self, session: BrowserSession) -> BrowserResult:
        if len(session.history) < 2:
            return BrowserResult("failed", error_code="browser_history_empty")
        updated = replace(session, current_url=session.history[-2], history=session.history[:-1])
        self._sessions[session.session_id] = updated
        return BrowserResult("succeeded", {"url": updated.current_url}, verified=True)

    @staticmethod
    def _forward(session: BrowserSession) -> BrowserResult:
        del session
        return BrowserResult("failed", error_code="browser_forward_not_available_in_local_adapter")

    async def _read(self, session: BrowserSession, capability: BrowserCapability) -> BrowserResult:
        if session.current_url is None:
            return BrowserResult("failed", error_code="browser_url_missing")
        source_url = session.current_url
        try:
            html, final_url = await asyncio.to_thread(self._fetch, source_url)
        except BrowserURLPolicyError as exc:
            return BrowserResult("denied", error_code=exc.code)
        except (OSError, urllib.error.URLError, ValueError) as exc:
            return BrowserResult("failed", error_code=self._fetch_error_code(exc))
        parser = _PageParser()
        parser.feed(html)
        text = " ".join(parser.text).strip()[: self._MAX_TEXT_CHARS]
        main_text = (parser.main_text or text)[: self._MAX_TEXT_CHARS]
        links = self._normalize_links(parser.links, final_url)
        headings = parser.headings[: self._MAX_HEADINGS]
        output: dict[str, object] = {
            "session_id": session.session_id,
            "url": final_url,
            "source_url": source_url,
            "final_url": final_url,
            "text": text,
            "main_text": main_text,
            "title": parser.title or (headings[0] if headings else None),
            "headings": headings,
            "links": links,
            "structured_metadata": dict(list(parser.metadata.items())[: self._MAX_METADATA]),
            "retrieved_at": datetime.now(UTC).isoformat(),
            "adapter_kind": "local_static",
            "content_digest": hashlib.sha256(main_text.encode("utf-8", errors="replace")).hexdigest(),
        }
        if capability is BrowserCapability.INSPECT_ACCESSIBILITY_TREE:
            output["accessibility_tree"] = {"headings": headings, "links": links}
        self._sessions[session.session_id] = replace(session, current_url=final_url, history=session.history + ((final_url,) if final_url != session.current_url else ()))
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

    async def _interact(self, session: BrowserSession, capability: BrowserCapability, parameters: Mapping[str, object]) -> BrowserResult:
        selector = parameters.get("selector")
        if not isinstance(selector, str) or not selector.strip() or len(selector) > 200 or "\x00" in selector:
            return BrowserResult("denied", error_code="element_selector_required")
        if capability is BrowserCapability.TYPE:
            value = parameters.get("text")
            if not isinstance(value, str) or not value or len(value) > 2_000 or "\x00" in value:
                return BrowserResult("denied", error_code="element_text_invalid")
        elif capability is BrowserCapability.SELECT:
            value = parameters.get("value")
            if not isinstance(value, str) or not value or len(value) > 200:
                return BrowserResult("denied", error_code="select_value_invalid")
        try:
            html, _ = await asyncio.wait_for(asyncio.to_thread(self._fetch, session.current_url or ""), self._interaction_timeout_seconds)
        except asyncio.TimeoutError:
            return BrowserResult("failed", error_code="browser_interaction_timeout")
        except BrowserURLPolicyError as exc:
            return BrowserResult("denied", error_code=exc.code)
        except (OSError, urllib.error.URLError, ValueError) as exc:
            return BrowserResult("failed", error_code=self._fetch_error_code(exc))
        parser = _ElementParser()
        parser.feed(html)
        matches = [(tag, attrs) for tag, attrs in parser.elements if self._matches_selector(tag, attrs, selector)]
        if not matches:
            return BrowserResult("failed", error_code="element_not_found")
        if capability is BrowserCapability.CLICK:
            tag, attrs = matches[0]
            href = attrs.get("href") if tag == "a" else None
            if href:
                url = urljoin(session.current_url or "", href)
                try:
                    self._validate_url(url)
                except BrowserURLPolicyError as exc:
                    return BrowserResult("denied", error_code=exc.code)
                updated = replace(session, current_url=url, history=session.history + (url,))
                self._sessions[session.session_id] = updated
                return BrowserResult("succeeded", {"session_id": session.session_id, "selector": selector, "url": url, "action": "click"}, verified=True)
            return BrowserResult("succeeded", {"session_id": session.session_id, "selector": selector, "action": "click"}, verified=True)
        if capability is BrowserCapability.TYPE:
            self._form_values[(session.session_id, selector)] = value
            return BrowserResult("succeeded", {"session_id": session.session_id, "selector": selector, "value_length": len(value), "action": "type"}, verified=True)
        return BrowserResult("succeeded", {"session_id": session.session_id, "selector": selector, "value_length": len(value), "content_redacted": True, "action": "select"}, verified=True)

    @staticmethod
    def _matches_selector(tag: str, attrs: Mapping[str, str], selector: str) -> bool:
        selector = selector.strip()
        if selector.startswith("#"):
            return attrs.get("id") == selector[1:]
        if selector.startswith("."):
            return selector[1:] in attrs.get("class", "").split()
        name_match = re.fullmatch(r"\[name=['\"]?([^'\"]+)['\"]?\]", selector)
        if name_match:
            return attrs.get("name") == name_match.group(1)
        return tag == selector.casefold()

    def _fetch(self, url: str) -> tuple[str, str]:
        self._validate_url(url)
        if self._fetcher is not None:
            body, final_url = self._fetcher(url)
            self._enforce_body_limit(body)
            self._validate_url(final_url)
            return body, final_url
        request = urllib.request.Request(url, headers={"User-Agent": "JARVIS-local-browser/1"})
        opener = urllib.request.build_opener(_SafeRedirectHandler(self._url_policy))
        with opener.open(request, timeout=10) as response:
            body = response.read(self._MAX_BODY_BYTES + 1)
            if len(body) > self._MAX_BODY_BYTES:
                raise ValueError("page_too_large")
            final_url = response.geturl()
            self._url_policy.validate(final_url)
            return body.decode("utf-8", errors="replace"), final_url

    @classmethod
    def _enforce_body_limit(cls, body: str) -> None:
        if len(body.encode("utf-8", errors="replace")) > cls._MAX_BODY_BYTES:
            raise ValueError("page_too_large")

    @staticmethod
    def _fetch_error_code(exc: Exception) -> str:
        return "page_too_large" if str(exc) == "page_too_large" else f"page_fetch_failed:{exc.__class__.__name__}"

    def _normalize_links(self, links: list[dict[str, str]], final_url: str) -> list[dict[str, str]]:
        output: list[dict[str, str]] = []
        for link in links[: self._MAX_LINKS]:
            href = link.get("href", "")
            try:
                absolute = urljoin(final_url, href)
                self._url_policy.validate(absolute, resolve_dns=False)
            except BrowserURLPolicyError:
                continue
            output.append({"text": link.get("text", "")[:200], "href": absolute[:4_096]})
        return output

    def _validate_url(self, url: str) -> str:
        # Injected deterministic fetchers are intentionally allowed to use
        # synthetic public hosts, but literal/private destinations are still
        # rejected. Real urllib requests resolve before network I/O.
        return self._url_policy.validate(url, resolve_dns=self._fetcher is None)

    @staticmethod
    def _session_data(session: BrowserSession) -> dict[str, object]:
        return {"session_id": session.session_id, "url": session.current_url, "device_id": session.device_id, "active": session.active, "mode": session.mode.value}

    async def close(self) -> None:
        self._sessions.clear()
        self._form_values.clear()


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, policy: BrowserURLPolicy) -> None:
        super().__init__()
        self._policy = policy
        self._redirects = 0

    def redirect_request(self, req: urllib.request.Request, fp: object, code: int, msg: str, headers: object, newurl: str) -> urllib.request.Request | None:
        if self._redirects >= self._policy.MAX_REDIRECTS:
            raise BrowserURLPolicyError("browser_redirect_limit")
        self._policy.validate(newurl)
        self._redirects += 1
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class BrowserActionService:
    """Apply common authority, audit, and event behavior to browser actions."""

    _read_actions = frozenset({item.value for item in (BrowserCapability.OPEN_URL, BrowserCapability.NAVIGATE, BrowserCapability.BACK, BrowserCapability.FORWARD, BrowserCapability.READ_PAGE, BrowserCapability.INSPECT_ACCESSIBILITY_TREE, BrowserCapability.FIND_ELEMENT, BrowserCapability.EXTRACT_TEXT, BrowserCapability.TABS)})

    def __init__(self, controller: object, repository: RuntimeRepository, event_bus: InMemoryEventBus, permission: PolicyPermissionEngine, audit: DurableAuditService, approvals: DurableApprovalEngine | None = None) -> None:
        self.controller = controller
        self.repository = repository
        self.event_bus = event_bus
        self.permission = permission
        self.audit = audit
        self.approvals = approvals
        self._pending: dict[str, tuple[BrowserAction, Identity, DeviceIdentity, str, str, BrowserSessionMode, object | None]] = {}

    async def execute(
        self,
        action: BrowserAction,
        identity: Identity,
        device: DeviceIdentity,
        *,
        session_id: str = "browser",
        correlation_id: str | None = None,
        session_mode: BrowserSessionMode = BrowserSessionMode.EPHEMERAL,
    ) -> BrowserResult:
        if not isinstance(session_mode, BrowserSessionMode):
            return BrowserResult("denied", error_code="browser_session_mode_invalid")
        correlation = correlation_id or f"browser-{uuid4()}"
        required_capability = f"browser.{action.action}"
        risk = "read" if action.action in self._read_actions else "consequential"
        decision = await self.permission.evaluate(identity, device, required_capability, {"required_scope": "tool.request", "required_capabilities": frozenset({required_capability}), "risk_level": risk})
        if decision.effect.value != "allow":
            await self.audit.record(AuditRecord(f"audit-{uuid4()}", "browser.permission_denied", datetime.now(UTC), identity.identity_id, device.device_id, correlation, decision.effect.value, decision.reason_code, {"action": action.action}))
            if decision.effect.value == "require_approval" and self.approvals is not None:
                target_error, target_binding = await self._prepare_target(action, identity, device, session_id, correlation, session_mode)
                if target_error is not None:
                    await self._emit("browser.action_failed", identity.owner_id, correlation, {"action": action.action, "error_code": target_error.error_code}, EventState.FAILED)
                    await self.audit.record(AuditRecord(f"audit-{uuid4()}", "browser.action_failed", datetime.now(UTC), identity.identity_id, device.device_id, correlation, target_error.status, target_error.error_code, {"action": action.action}))
                    return target_error
                approval_id = f"approval-{uuid4()}"
                await self.approvals.request(ApprovalRequest(approval_id, required_capability, identity.owner_id, device.device_id, "browser action requires approval", datetime.now(UTC), datetime.now(UTC) + timedelta(minutes=10), self._approval_preview(action)))
                self._pending[approval_id] = (action, identity, device, session_id, correlation, session_mode, target_binding)
                await self._emit("browser.action_requested", identity.owner_id, correlation, {"action": action.action, "approval_id": approval_id}, EventState.ACCEPTED)
                return BrowserResult("approval_required", error_code=decision.reason_code, approval_id=approval_id)
            await self._emit("browser.action_failed", identity.owner_id, correlation, {"action": action.action, "reason": decision.reason_code}, EventState.FAILED)
            return BrowserResult("approval_required" if decision.effect.value == "require_approval" else "denied", error_code=decision.reason_code)
        return await self._execute_controller(action, identity, device, session_id, correlation, session_mode)

    async def decide(self, approval_id: str, approved: bool, decided_by: str) -> BrowserResult:
        pending = self._pending.get(approval_id)
        if pending is None or self.approvals is None:
            return BrowserResult("failed", error_code="browser_approval_unavailable", approval_id=approval_id)
        action, identity, device, session_id, correlation, session_mode, target_binding = pending
        decision = await self.approvals.decide(approval_id, approved, decided_by)
        self._pending.pop(approval_id, None)
        if decision.status.value != "approved":
            return BrowserResult("denied", error_code=decision.status.value, approval_id=approval_id)
        target_error = await self._revalidate_target(action, identity, device, session_id, correlation, session_mode, target_binding)
        if target_error is not None:
            await self._emit("browser.action_failed", identity.owner_id, correlation, {"action": action.action, "error_code": target_error.error_code, "approval_id": approval_id}, EventState.FAILED)
            await self.audit.record(AuditRecord(f"audit-{uuid4()}", "browser.action_failed", datetime.now(UTC), identity.identity_id, device.device_id, correlation, target_error.status, target_error.error_code, {"action": action.action, "approval_id": approval_id}))
            return BrowserResult(target_error.status, target_error.output, target_error.error_code, target_error.verified, approval_id)
        return await self._execute_controller(action, identity, device, session_id, correlation, session_mode, approval_id)

    async def _execute_controller(self, action: BrowserAction, identity: Identity, device: DeviceIdentity, session_id: str, correlation: str, session_mode: BrowserSessionMode, approval_id: str | None = None) -> BrowserResult:
        await self._emit("browser.action_started", identity.owner_id, correlation, {"action": action.action}, EventState.ACCEPTED)
        metadata = {"browser_approval_id": approval_id} if approval_id is not None else {}
        result = await self.controller.execute(action, ToolContext(identity, device, session_id, correlation, metadata=metadata), session_mode=session_mode)
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

    async def close(self) -> None:
        close = getattr(self.controller, "close", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result

    async def _prepare_target(
        self,
        action: BrowserAction,
        identity: Identity,
        device: DeviceIdentity,
        session_id: str,
        correlation: str,
        session_mode: BrowserSessionMode,
    ) -> tuple[BrowserResult | None, object | None]:
        prepare = getattr(self.controller, "prepare_approval", None)
        if prepare is None:
            return None, None
        result = prepare(action, ToolContext(identity, device, session_id, correlation), session_mode)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, tuple) or len(result) != 2:
            return BrowserResult("failed", error_code="browser_target_preparation_failed"), None
        error, binding = result
        if error is None:
            return None, binding
        if isinstance(error, BrowserResult):
            return error, None
        return BrowserResult("failed", error_code="browser_target_preparation_failed"), None

    async def _revalidate_target(
        self,
        action: BrowserAction,
        identity: Identity,
        device: DeviceIdentity,
        session_id: str,
        correlation: str,
        session_mode: BrowserSessionMode,
        binding: object | None,
    ) -> BrowserResult | None:
        revalidate = getattr(self.controller, "revalidate_approval", None)
        if revalidate is None:
            return None
        result = revalidate(
            action,
            ToolContext(identity, device, session_id, correlation),
            session_mode,
            binding,
        )
        if inspect.isawaitable(result):
            result = await result
        if result is None:
            return None
        return result if isinstance(result, BrowserResult) else BrowserResult("failed", error_code="browser_approval_target_changed")

    @staticmethod
    def _approval_preview(action: BrowserAction) -> dict[str, object]:
        parameters = action.parameters
        preview: dict[str, object] = {"action": action.action}
        element_ref = parameters.get("element_ref")
        if isinstance(element_ref, str):
            preview["element_ref"] = element_ref[:100]
        session_id = parameters.get("session_id")
        if isinstance(session_id, str):
            preview["session_id"] = session_id[:100]
        if action.action == BrowserCapability.TYPE.value:
            text = parameters.get("text")
            preview.update({"text_length": len(text) if isinstance(text, str) else 0, "content_redacted": True})
        elif action.action == BrowserCapability.SELECT.value:
            value = parameters.get("value")
            preview.update({"value_length": len(value) if isinstance(value, str) else 0, "content_redacted": True})
        elif action.action == BrowserCapability.UPLOAD_FILE.value:
            path = parameters.get("path")
            preview.update({"path_name": str(path).replace("\\", "/").rsplit("/", 1)[-1][:120] if isinstance(path, str) else None, "path_redacted": True})
        elif action.action in {BrowserCapability.NAVIGATE.value, BrowserCapability.CLICK.value}:
            preview["target_metadata"] = "bounded browser destination"
        return preview

    async def _emit(self, event_type: str, owner_id: str, correlation: str, payload: dict[str, object], state: EventState) -> None:
        event = Event.create(event_type, EventCategory.BROWSER, correlation_id=correlation, actor_id=owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
