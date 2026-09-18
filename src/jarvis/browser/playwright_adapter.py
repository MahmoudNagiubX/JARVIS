"""A bounded, optional Playwright backend behind the browser controller seam."""

from __future__ import annotations

import importlib
import inspect
import hashlib
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

from ..contracts import BrowserAction, BrowserCapability, BrowserResult, BrowserSessionMode, ToolContext
from .policy import BrowserURLPolicy, BrowserURLPolicyError
from .profile import BrowserProfilePolicy, BrowserProfilePolicyError, validate_brave_executable_path


PlaywrightModuleLoader = Callable[[str], object]


@dataclass(slots=True)
class _PlaywrightSession:
    session_id: str
    owner_id: str
    device_id: str
    mode: BrowserSessionMode
    context: Any
    page: Any
    browser: Any = None
    page_ref: str = ""
    source_url: str = ""
    epoch: int = 0
    bindings: dict[str, "_ElementBinding"] = field(default_factory=dict)


@dataclass(slots=True)
class _ElementBinding:
    element_ref: str
    session_id: str
    page_ref: str
    epoch: int
    origin: str
    role: str
    accessible_name: str
    tag: str
    fingerprint: str
    expires_at: float
    bound_action: str | None = None


@dataclass(slots=True)
class _ObservedElement:
    locator: Any
    role: str
    accessible_name: str
    tag: str
    fingerprint: str
    visible: bool
    enabled: bool
    checked: bool | None
    selected: bool | None
    context: str
    input_type: str


class PlaywrightBrowserController:
    """Run owned Playwright contexts without creating a second browser authority.

    The optional import is lazy so the normal JARVIS runtime remains usable
    without Playwright.  The legacy injected executor is retained for
    deterministic product-owned tests and compatibility with the existing
    controller seam; it is never exposed to model/tool arguments.
    """

    _MAX_TEXT = 20_000
    _MAX_ELEMENTS = 100
    _ELEMENT_REF_TTL_SECONDS = 120.0
    _NAVIGATION_TIMEOUT_MS = 30_000
    _ACTION_TIMEOUT_MS = 10_000

    def __init__(
        self,
        executor: Callable[[BrowserAction, ToolContext], BrowserResult | Awaitable[BrowserResult]] | None = None,
        *,
        executable_path: str | None = None,
        headless: bool = True,
        profile_policy: BrowserProfilePolicy | None = None,
        playwright_module_loader: PlaywrightModuleLoader | None = None,
        url_policy: BrowserURLPolicy | None = None,
    ) -> None:
        self._executor = executor
        self._executable_path = executable_path
        self._headless = bool(headless)
        self._profile_policy = profile_policy or BrowserProfilePolicy(None, owner_persistent_opt_in=False)
        self._module_loader = playwright_module_loader or importlib.import_module
        self._url_policy = url_policy or BrowserURLPolicy()
        self._playwright: Any = None
        self._browser_type: Any = None
        self._sessions: dict[str, _PlaywrightSession] = {}
        self._closed = False

    @property
    def playwright(self) -> Any:
        """Expose only internal readiness for diagnostics, never model data."""

        return self._playwright

    async def execute(
        self,
        action: BrowserAction,
        context: ToolContext,
        *,
        session_mode: BrowserSessionMode = BrowserSessionMode.EPHEMERAL,
    ) -> BrowserResult:
        if self._executor is not None:
            try:
                result = self._executor(action, context)
                if inspect.isawaitable(result):
                    result = await result
                return result
            except Exception as exc:  # noqa: BLE001 - provider boundary normalizes details
                return BrowserResult("failed", error_code=self._normalize_error(action.action, exc))
        if self._closed:
            return BrowserResult("failed", error_code="browser_controller_closed")
        if not isinstance(session_mode, BrowserSessionMode):
            return BrowserResult("denied", error_code="browser_session_mode_invalid")
        if context.identity is None or context.device is None:
            return BrowserResult("denied", error_code="identity_or_device_missing")
        if context.identity.owner_id != context.device.owner_id:
            return BrowserResult("denied", error_code="owner_binding_mismatch")
        try:
            await self._ensure_runtime()
            if action.action == BrowserCapability.OPEN_URL.value:
                return await self._open(action.parameters, context, session_mode)
            if action.action == BrowserCapability.TABS.value:
                await self._ensure_runtime()
                return self._tabs(context)
            session = self._session(action.parameters, context)
            if session is None:
                return BrowserResult("failed", error_code="browser_session_missing")
            if action.action == BrowserCapability.NAVIGATE.value:
                return await self._navigate(session, action.parameters)
            if action.action == BrowserCapability.BACK.value:
                return await self._history_action(session, forward=False)
            if action.action == BrowserCapability.FORWARD.value:
                return await self._history_action(session, forward=True)
            if action.action in {
                BrowserCapability.READ_PAGE.value,
                BrowserCapability.EXTRACT_TEXT.value,
                BrowserCapability.INSPECT_ACCESSIBILITY_TREE.value,
            }:
                return await self._read(session, action.action)
            if action.action == BrowserCapability.FIND_ELEMENT.value:
                return await self._find(session, action.parameters)
            if action.action == BrowserCapability.CLICK.value:
                return await self._click(session, action.parameters, context)
            if action.action == BrowserCapability.TYPE.value:
                return await self._type(session, action.parameters, context)
            if action.action == BrowserCapability.SELECT.value:
                return await self._select(session, action.parameters, context)
            if action.action in {
                BrowserCapability.DOWNLOAD_FILE.value,
                BrowserCapability.UPLOAD_FILE.value,
                BrowserCapability.SCREENSHOT.value,
            }:
                return BrowserResult("failed", error_code="browser_action_requires_t5_adapter")
            return BrowserResult("denied", error_code="unsupported_browser_action")
        except BrowserURLPolicyError as exc:
            return BrowserResult("denied", error_code=exc.code)
        except BrowserProfilePolicyError as exc:
            status = "failed" if exc.code in {"playwright_adapter_not_available", "browser_process_launch_failed"} else "denied"
            return BrowserResult(status, error_code=exc.code)
        except Exception as exc:  # noqa: BLE001 - provider boundary normalizes details
            return BrowserResult("failed", error_code=self._normalize_error(action.action, exc))

    async def close(self) -> None:
        """Close only contexts and browser processes created by this instance."""

        if self._closed and self._playwright is None and not self._sessions:
            return
        self._closed = True
        sessions = tuple(self._sessions.values())
        self._sessions.clear()
        closed_context_ids: set[int] = set()
        closed_browser_ids: set[int] = set()
        for session in sessions:
            context = session.context
            if context is not None and id(context) not in closed_context_ids:
                closed_context_ids.add(id(context))
                await self._close_object(context)
            browser = session.browser
            if browser is not None and id(browser) not in closed_browser_ids:
                closed_browser_ids.add(id(browser))
                await self._close_object(browser)
        if self._playwright is not None:
            await self._close_object(self._playwright, method_name="stop")
            self._playwright = None
            self._browser_type = None

    async def _ensure_runtime(self) -> None:
        if self._playwright is not None:
            return
        try:
            module = self._module_loader("playwright.async_api")
        except (ImportError, ModuleNotFoundError) as exc:
            raise BrowserProfilePolicyError("playwright_adapter_not_available") from exc
        try:
            manager = module.async_playwright()
            self._playwright = await manager.start()
            self._browser_type = self._playwright.chromium
        except Exception as exc:  # noqa: BLE001 - normalized at controller boundary
            raise RuntimeError("browser_process_launch_failed") from exc

    async def _open(self, parameters: Mapping[str, object], context: ToolContext, mode: BrowserSessionMode) -> BrowserResult:
        url = parameters.get("url")
        if not isinstance(url, str):
            return BrowserResult("denied", error_code="url_invalid")
        self._url_policy.validate(url)
        await self._ensure_runtime()
        executable = validate_brave_executable_path(self._executable_path)
        browser = None
        if mode is BrowserSessionMode.OWNER_PERSISTENT:
            profile_path = self._profile_policy.persistent_user_data_dir(required=True)
            assert profile_path is not None
            profile_path.mkdir(parents=True, exist_ok=True)
            browser_context = await self._browser_type.launch_persistent_context(
                user_data_dir=str(profile_path),
                executable_path=str(executable),
                headless=self._headless,
            )
        else:
            browser = await self._browser_type.launch(
                executable_path=str(executable),
                headless=self._headless,
            )
            browser_context = await browser.new_context()
        page = await browser_context.new_page()
        session_id = f"browser-{uuid4()}"
        session = _PlaywrightSession(
            session_id=session_id,
            owner_id=context.identity.owner_id,
            device_id=context.device.device_id,
            mode=mode,
            context=browser_context,
            page=page,
            browser=browser,
            page_ref=f"browser-page-{uuid4()}",
            source_url=url,
        )
        self._sessions[session_id] = session
        try:
            final_url = await self._goto(page, url)
        except Exception:
            self._sessions.pop(session_id, None)
            await self._close_object(browser_context)
            if browser is not None:
                await self._close_object(browser)
            raise
        return BrowserResult("succeeded", {"session_id": session_id, "url": final_url, "mode": mode.value}, verified=True)

    async def _navigate(self, session: _PlaywrightSession, parameters: Mapping[str, object]) -> BrowserResult:
        url = parameters.get("url")
        if not isinstance(url, str):
            return BrowserResult("denied", error_code="url_invalid")
        self._url_policy.validate(url)
        final_url = await self._goto(session.page, url)
        session.source_url = url
        session.epoch += 1
        session.bindings.clear()
        return BrowserResult("succeeded", {"session_id": session.session_id, "url": final_url}, verified=True)

    async def _history_action(self, session: _PlaywrightSession, *, forward: bool) -> BrowserResult:
        operation = session.page.go_forward if forward else session.page.go_back
        response = await operation(wait_until="domcontentloaded", timeout=self._NAVIGATION_TIMEOUT_MS)
        final_url = str(session.page.url)
        self._url_policy.validate(final_url)
        session.source_url = final_url
        session.epoch += 1
        session.bindings.clear()
        return BrowserResult("succeeded", {"session_id": session.session_id, "url": final_url, "moved": response is not None}, verified=True)

    async def _read(self, session: _PlaywrightSession, action: str) -> BrowserResult:
        output = await self._dynamic_extraction(session)
        if action == BrowserCapability.INSPECT_ACCESSIBILITY_TREE.value:
            output["accessibility_tree"] = await self._accessibility(session)
        return BrowserResult("succeeded", output, verified=True)

    async def _dynamic_extraction(self, session: _PlaywrightSession) -> dict[str, object]:
        page = session.page
        final_url = self._safe_page_url(page)
        title = str(await page.title())[:500]
        text = str(await page.locator("body").inner_text(timeout=self._ACTION_TIMEOUT_MS)).strip()[: self._MAX_TEXT]
        main_text = text
        main = page.locator("main")
        if await main.count():
            candidate = str(await main.nth(0).inner_text(timeout=self._ACTION_TIMEOUT_MS)).strip()
            if candidate:
                main_text = candidate[: self._MAX_TEXT]
        headings = await self._bounded_headings(page)
        links = await self._bounded_links(page, final_url)
        metadata = await self._bounded_metadata(page)
        return {
            "session_id": session.session_id,
            "url": final_url,
            "source_url": session.source_url or final_url,
            "final_url": final_url,
            "title": title,
            "text": text,
            "main_text": main_text,
            "headings": headings,
            "links": links,
            "structured_metadata": metadata,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "adapter_kind": "playwright_dynamic",
            "content_digest": hashlib.sha256(main_text.encode("utf-8", errors="replace")).hexdigest(),
        }

    async def _find(self, session: _PlaywrightSession, parameters: Mapping[str, object]) -> BrowserResult:
        needle = parameters.get("text")
        if not isinstance(needle, str) or not needle.strip() or len(needle) > 200:
            return BrowserResult("denied", error_code="element_query_required")
        matches = []
        for target in await self._collect_elements(session.page):
            if needle.casefold() not in f"{target.accessible_name} {target.context}".casefold():
                continue
            matches.append(await self._register_target(session, target))
            if len(matches) >= self._MAX_ELEMENTS:
                break
        return BrowserResult("succeeded", {"matches": matches}, verified=True)

    async def _accessibility(self, session: _PlaywrightSession) -> dict[str, object]:
        elements = [
            await self._register_target(session, target)
            for target in await self._collect_elements(session.page)
        ]
        landmarks: list[dict[str, object]] = []
        for tag in ("header", "nav", "main", "aside", "footer"):
            locator = session.page.locator(tag)
            count = min(await locator.count(), 20)
            for index in range(count):
                item = locator.nth(index)
                try:
                    text = (await item.inner_text(timeout=self._ACTION_TIMEOUT_MS)).strip()[:200]
                except Exception:
                    text = ""
                landmarks.append({"role": tag, "context": text})
        return {
            "page_ref": session.page_ref,
            "url": self._safe_page_url(session.page),
            "landmarks": landmarks[:50],
            "elements": elements[: self._MAX_ELEMENTS],
        }

    async def _collect_elements(self, page: Any) -> list[_ObservedElement]:
        selectors: tuple[tuple[str, str | None], ...] = (
            ('button:not([role])', "button"),
            ('a[href]:not([role])', "link"),
            ('input:not([type="hidden"]):not([role])', None),
            ('textarea:not([role])', "textbox"),
            ('select:not([role])', "combobox"),
            ('[role="button"]', "button"),
            ('[role="link"]', "link"),
            ('[role="textbox"]', "textbox"),
            ('[role="checkbox"]', "checkbox"),
            ('[role="radio"]', "radio"),
            ('[role="combobox"]', "combobox"),
            ('[role="listbox"]', "listbox"),
            ('[role="tab"]', "tab"),
            ('[role="menuitem"]', "menuitem"),
        )
        elements: list[_ObservedElement] = []
        seen_with_id: set[tuple[str, str]] = set()
        for selector, implied_role in selectors:
            locator = page.locator(selector)
            count = min(await locator.count(), self._MAX_ELEMENTS)
            for index in range(count):
                item = locator.nth(index)
                try:
                    attrs = {
                        name: (await item.get_attribute(name) or "")[:500]
                        for name in (
                            "role", "aria-label", "aria-labelledby", "title", "placeholder",
                            "name", "type", "href", "autocomplete", "id", "aria-checked", "aria-selected",
                        )
                    }
                    role = attrs["role"] or implied_role or self._implicit_role(selector, attrs)
                    if not role:
                        continue
                    name = await self._accessible_name(item, attrs, role)
                    tag = self._tag_for_selector(selector, attrs)
                    identifier = attrs["id"]
                    if identifier:
                        dedupe_key = (role, identifier)
                        if dedupe_key in seen_with_id:
                            continue
                        seen_with_id.add(dedupe_key)
                    visible = await item.is_visible()
                    enabled = await item.is_enabled()
                    checked = await self._optional_checked(item, attrs)
                    selected = self._optional_bool(attrs.get("aria-selected"))
                    context = (await item.inner_text(timeout=self._ACTION_TIMEOUT_MS)).strip()[:200]
                    fingerprint = self._fingerprint(role, name, tag, attrs)
                    elements.append(_ObservedElement(item, role, name, tag, fingerprint, visible, enabled, checked, selected, context, attrs["type"].casefold()))
                except Exception:
                    continue
                if len(elements) >= self._MAX_ELEMENTS:
                    return elements
        return elements

    async def _register_target(self, session: _PlaywrightSession, target: _ObservedElement) -> dict[str, object]:
        element_ref = f"browser-element-{uuid4()}"
        binding = _ElementBinding(
            element_ref,
            session.session_id,
            session.page_ref,
            session.epoch,
            self._origin(self._safe_page_url(session.page)),
            target.role,
            target.accessible_name,
            target.tag,
            target.fingerprint,
            time.monotonic() + self._ELEMENT_REF_TTL_SECONDS,
        )
        session.bindings[element_ref] = binding
        output: dict[str, object] = {
            "element_ref": element_ref,
            "role": target.role,
            "accessible_name": target.accessible_name,
            "enabled": target.enabled,
            "visible": target.visible,
            "context": target.context,
        }
        if target.checked is not None:
            output["checked"] = target.checked
        if target.selected is not None:
            output["selected"] = target.selected
        return output

    async def _resolve_binding(
        self,
        action: BrowserAction,
        context: ToolContext,
        session_mode: BrowserSessionMode,
        *,
        expected: _ElementBinding | None = None,
    ) -> tuple[BrowserResult | None, _PlaywrightSession | None, Any | None]:
        if context.identity is None or context.device is None:
            return BrowserResult("denied", error_code="identity_or_device_missing"), None, None
        session = self._session(action.parameters, context)
        if session is None:
            return BrowserResult("failed", error_code="browser_session_missing"), None, None
        if session.mode is not session_mode:
            return BrowserResult("failed", error_code="browser_target_changed" if expected else "browser_session_mode_changed"), None, None
        element_ref = action.parameters.get("element_ref")
        if not isinstance(element_ref, str) or not element_ref.startswith("browser-element-") or len(element_ref) > 100:
            return BrowserResult("denied", error_code="browser_element_ref_required"), None, None
        binding = expected or session.bindings.get(element_ref)
        if binding is None or binding.element_ref != element_ref:
            return BrowserResult("failed", error_code="browser_element_stale"), None, None
        if expected is not None and binding.bound_action not in {None, action.action}:
            return BrowserResult("failed", error_code="browser_approval_target_changed"), None, None
        if binding.expires_at < time.monotonic():
            session.bindings.pop(element_ref, None)
            return BrowserResult("failed", error_code="browser_element_stale"), None, None
        if binding.session_id != session.session_id or binding.page_ref != session.page_ref:
            return BrowserResult("failed", error_code="browser_target_changed" if expected else "browser_element_stale"), None, None
        if binding.epoch != session.epoch:
            return BrowserResult("failed", error_code="browser_approval_target_changed" if expected else "browser_element_stale"), None, None
        current_origin = self._origin(self._safe_page_url(session.page))
        if current_origin != binding.origin:
            return BrowserResult("failed", error_code="browser_approval_target_changed" if expected else "browser_target_changed"), None, None
        try:
            locator = session.page.get_by_role(binding.role, name=binding.accessible_name, exact=True)
            count = await locator.count()
        except Exception as exc:
            return BrowserResult("failed", error_code=self._normalize_error(action.action, exc)), None, None
        if count == 0:
            return BrowserResult("failed", error_code="browser_approval_target_changed" if expected else "browser_element_stale"), None, None
        if count != 1:
            return BrowserResult("failed", error_code="browser_approval_target_changed" if expected else "browser_element_ambiguous"), None, None
        target = await self._observe_locator(locator, binding.role, binding.tag)
        if target is None:
            return BrowserResult("failed", error_code="browser_approval_target_changed" if expected else "browser_element_stale"), None, None
        if target.fingerprint != binding.fingerprint:
            return BrowserResult("failed", error_code="browser_approval_target_changed" if expected else "browser_element_stale"), None, None
        if action.action == BrowserCapability.TYPE.value:
            if self._sensitive_target(target):
                return BrowserResult("denied", error_code="browser_sensitive_input_denied"), None, None
            if target.role not in {"textbox", "searchbox"}:
                return BrowserResult("denied", error_code="browser_actionability_failed"), None, None
        if action.action == BrowserCapability.SELECT.value and target.tag != "select":
            return BrowserResult("denied", error_code="browser_select_target_invalid"), None, None
        if action.action in {BrowserCapability.CLICK.value, BrowserCapability.TYPE.value, BrowserCapability.SELECT.value} and not target.visible:
            return BrowserResult("failed", error_code="browser_actionability_failed"), None, None
        if action.action in {BrowserCapability.CLICK.value, BrowserCapability.TYPE.value, BrowserCapability.SELECT.value} and not target.enabled:
            return BrowserResult("failed", error_code="browser_actionability_failed"), None, None
        return None, session, locator

    async def prepare_approval(self, action: BrowserAction, context: ToolContext, session_mode: BrowserSessionMode) -> tuple[BrowserResult | None, object | None]:
        if action.action not in {BrowserCapability.CLICK.value, BrowserCapability.TYPE.value, BrowserCapability.SELECT.value}:
            return None, None
        error, _, _ = await self._resolve_binding(action, context, session_mode)
        if error is not None:
            return error, None
        session = self._session(action.parameters, context)
        assert session is not None
        element_ref = str(action.parameters["element_ref"])
        binding = session.bindings.get(element_ref)
        return None, replace(binding, bound_action=action.action) if binding is not None else None

    async def revalidate_approval(self, action: BrowserAction, context: ToolContext, session_mode: BrowserSessionMode, binding: object | None) -> BrowserResult | None:
        if action.action not in {BrowserCapability.CLICK.value, BrowserCapability.TYPE.value, BrowserCapability.SELECT.value}:
            return None
        if not isinstance(binding, _ElementBinding):
            return BrowserResult("failed", error_code="browser_approval_target_changed")
        error, _, _ = await self._resolve_binding(action, context, session_mode, expected=binding)
        return error

    async def _click(self, session: _PlaywrightSession, parameters: Mapping[str, object], context: ToolContext) -> BrowserResult:
        if context.metadata.get("browser_approval_id") is None:
            return BrowserResult("denied", error_code="browser_action_requires_approval")
        action = BrowserAction(BrowserCapability.CLICK.value, parameters)
        error, _, locator = await self._resolve_binding(action, context, session.mode)
        if error is not None:
            return error
        before_url = self._safe_page_url(session.page)
        before_state = await self._action_state(locator)
        await locator.click(timeout=self._ACTION_TIMEOUT_MS)
        after_url = self._safe_page_url(session.page)
        if after_url != before_url:
            self._url_policy.validate(after_url)
            session.epoch += 1
            session.bindings.clear()
            verified = True
        else:
            after_state = await self._action_state(locator)
            verified = before_state != after_state
        return BrowserResult("succeeded", {"session_id": session.session_id, "element_ref": parameters.get("element_ref"), "action": "click"}, verified=verified)

    async def _type(self, session: _PlaywrightSession, parameters: Mapping[str, object], context: ToolContext) -> BrowserResult:
        value = parameters.get("text")
        if not isinstance(value, str) or not value or len(value) > 2_000 or "\x00" in value:
            return BrowserResult("denied", error_code="element_text_invalid")
        if context.metadata.get("browser_approval_id") is None:
            return BrowserResult("denied", error_code="browser_action_requires_approval")
        action = BrowserAction(BrowserCapability.TYPE.value, parameters)
        error, _, locator = await self._resolve_binding(action, context, session.mode)
        if error is not None:
            return error
        await locator.fill(value, timeout=self._ACTION_TIMEOUT_MS)
        readback = await locator.input_value(timeout=self._ACTION_TIMEOUT_MS)
        return BrowserResult(
            "succeeded",
            {"session_id": session.session_id, "element_ref": parameters.get("element_ref"), "value_length": len(value), "content_redacted": True, "action": "type"},
            verified=readback == value,
        )

    async def _select(self, session: _PlaywrightSession, parameters: Mapping[str, object], context: ToolContext) -> BrowserResult:
        value = parameters.get("value")
        if not isinstance(value, str) or not value or len(value) > 200 or "\x00" in value:
            return BrowserResult("denied", error_code="select_value_invalid")
        if context.metadata.get("browser_approval_id") is None:
            return BrowserResult("denied", error_code="browser_action_requires_approval")
        action = BrowserAction(BrowserCapability.SELECT.value, parameters)
        error, _, locator = await self._resolve_binding(action, context, session.mode)
        if error is not None:
            return error
        await locator.select_option(value=value, timeout=self._ACTION_TIMEOUT_MS)
        readback = await locator.input_value(timeout=self._ACTION_TIMEOUT_MS)
        return BrowserResult(
            "succeeded",
            {"session_id": session.session_id, "element_ref": parameters.get("element_ref"), "value_length": len(value), "content_redacted": True, "action": "select"},
            verified=readback == value,
        )

    async def _observe_locator(self, locator: Any, role: str, tag: str) -> _ObservedElement | None:
        try:
            attrs = {
                name: (await locator.get_attribute(name) or "")[:500]
                for name in (
                    "role", "aria-label", "aria-labelledby", "title", "placeholder", "name",
                    "type", "href", "autocomplete", "id", "aria-checked", "aria-selected",
                )
            }
            name = await self._accessible_name(locator, attrs, role)
            return _ObservedElement(
                locator,
                attrs["role"] or role,
                name,
                tag,
                self._fingerprint(attrs["role"] or role, name, tag, attrs),
                await locator.is_visible(),
                await locator.is_enabled(),
                await self._optional_checked(locator, attrs),
                self._optional_bool(attrs.get("aria-selected")),
                (await locator.inner_text(timeout=self._ACTION_TIMEOUT_MS)).strip()[:200],
                attrs["type"].casefold(),
            )
        except Exception:
            return None

    async def _accessible_name(self, locator: Any, attrs: Mapping[str, str], role: str) -> str:
        for key in ("aria-label", "title", "placeholder", "name"):
            if attrs.get(key, "").strip():
                return attrs[key].strip()[:200]
        try:
            text = (await locator.inner_text(timeout=self._ACTION_TIMEOUT_MS)).strip()
        except Exception:
            text = ""
        if not text and role == "button":
            text = attrs.get("type", "")
        return text[:200]

    @staticmethod
    async def _optional_checked(locator: Any, attrs: Mapping[str, str]) -> bool | None:
        aria_value = attrs.get("aria-checked", "")
        if aria_value.casefold() in {"true", "false"}:
            return aria_value.casefold() == "true"
        if attrs.get("type", "").casefold() not in {"checkbox", "radio"}:
            return None
        try:
            return bool(await locator.is_checked())
        except Exception:
            return None

    @staticmethod
    def _optional_bool(value: str | None) -> bool | None:
        if value is None or value.casefold() not in {"true", "false"}:
            return None
        return value.casefold() == "true"

    @staticmethod
    def _tag_for_selector(selector: str, attrs: Mapping[str, str]) -> str:
        if selector.startswith("button") or attrs.get("role") == "button":
            return "button"
        if selector.startswith("a") or attrs.get("role") == "link":
            return "a"
        if selector.startswith("textarea"):
            return "textarea"
        if selector.startswith("select"):
            return "select"
        if selector.startswith("input"):
            return "input"
        return "role"

    @staticmethod
    def _implicit_role(selector: str, attrs: Mapping[str, str]) -> str | None:
        if selector.startswith("button"):
            return "button"
        if selector.startswith("a"):
            return "link"
        if selector.startswith("textarea"):
            return "textbox"
        if selector.startswith("select"):
            return "combobox"
        input_type = attrs.get("type", "text").casefold()
        return {"checkbox": "checkbox", "radio": "radio", "button": "button", "submit": "button", "search": "searchbox"}.get(input_type, "textbox")

    @staticmethod
    def _fingerprint(role: str, name: str, tag: str, attrs: Mapping[str, str]) -> str:
        material = "|".join(
            (
                role,
                name,
                tag,
                attrs.get("id", ""),
                attrs.get("name", ""),
                attrs.get("type", ""),
                attrs.get("href", ""),
                attrs.get("aria-label", ""),
            )
        )
        return hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:32]

    @staticmethod
    def _sensitive_target(target: _ObservedElement) -> bool:
        sensitive_terms = ("password", "passcode", "otp", "one-time", "one time", "recovery", "credit card", "card number", "cvv", "security answer", "secret", "token")
        material = " ".join((target.input_type, target.accessible_name, target.context)).casefold()
        return target.input_type in {"password", "hidden"} or any(term in material for term in sensitive_terms)

    @staticmethod
    async def _action_state(locator: Any) -> tuple[object, ...]:
        state: list[object] = []
        for name in ("aria-pressed", "aria-expanded", "aria-checked", "aria-selected"):
            state.append(await locator.get_attribute(name))
        try:
            state.append(await locator.is_checked())
        except Exception:
            state.append(None)
        return tuple(state)

    async def _goto(self, page: Any, url: str) -> str:
        await page.goto(url, wait_until="domcontentloaded", timeout=self._NAVIGATION_TIMEOUT_MS)
        final_url = self._safe_page_url(page)
        self._url_policy.validate(final_url)
        return final_url

    def _session(self, parameters: Mapping[str, object], context: ToolContext) -> _PlaywrightSession | None:
        session_id = parameters.get("session_id")
        if not isinstance(session_id, str) or len(session_id) > 100:
            return None
        session = self._sessions.get(session_id)
        if session is None or session.owner_id != context.identity.owner_id or session.device_id != context.device.device_id:
            return None
        return session

    def _tabs(self, context: ToolContext) -> BrowserResult:
        sessions = [
            {
                "session_id": session.session_id,
                "url": self._safe_page_url(session.page),
                "device_id": session.device_id,
                "mode": session.mode.value,
                "active": True,
            }
            for session in self._sessions.values()
            if session.owner_id == context.identity.owner_id and session.device_id == context.device.device_id
        ]
        return BrowserResult("succeeded", {"tabs": sessions[:50]}, verified=True)

    @staticmethod
    def _safe_page_url(page: Any) -> str:
        return str(getattr(page, "url", ""))[:4_096]

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.hostname:
            return ""
        default_port = 443 if parsed.scheme.casefold() == "https" else 80
        port = parsed.port or default_port
        return f"{parsed.scheme.casefold()}://{parsed.hostname.casefold()}:{port}"

    async def _bounded_links(self, page: Any, final_url: str) -> list[dict[str, str]]:
        links = page.locator("a[href]")
        count = min(await links.count(), 100)
        output: list[dict[str, str]] = []
        for index in range(count):
            item = links.nth(index)
            try:
                href = await item.get_attribute("href") or ""
                absolute = urljoin(final_url, href)
                self._url_policy.validate(absolute, resolve_dns=False)
                output.append({"text": (await item.inner_text(timeout=self._ACTION_TIMEOUT_MS)).strip()[:200], "href": absolute[:4_096]})
            except BrowserURLPolicyError:
                continue
            except Exception:
                continue
        return output

    async def _bounded_headings(self, page: Any) -> list[str]:
        headings = page.locator("h1, h2, h3")
        count = min(await headings.count(), self._MAX_ELEMENTS)
        output: list[str] = []
        for index in range(count):
            try:
                text = (await headings.nth(index).inner_text(timeout=self._ACTION_TIMEOUT_MS)).strip()[:500]
            except Exception:
                continue
            if text:
                output.append(text)
        return output[: self._MAX_ELEMENTS]

    async def _bounded_metadata(self, page: Any) -> dict[str, str]:
        metadata = page.locator('meta[name], meta[property]')
        count = min(await metadata.count(), 20)
        output: dict[str, str] = {}
        for index in range(count):
            item = metadata.nth(index)
            try:
                key = (await item.get_attribute("name") or await item.get_attribute("property") or "").casefold().strip()
                value = (await item.get_attribute("content") or "").strip()
            except Exception:
                continue
            if key in {"description", "og:title", "og:description", "author"} and value:
                output[key] = value[:500]
        return dict(list(output.items())[:20])

    async def _bounded_accessibility(self, page: Any) -> dict[str, object]:
        return {"page_ref": f"browser-page-{uuid4()}", "landmarks": [], "elements": [], "text": ""}

    @staticmethod
    async def _close_object(value: Any, *, method_name: str = "close") -> None:
        method = getattr(value, method_name, None)
        if method is None:
            return
        result = method()
        if inspect.isawaitable(result):
            await result

    @staticmethod
    def _normalize_error(action: str, exc: Exception) -> str:
        detail = str(exc).casefold()
        name = exc.__class__.__name__.casefold()
        if "playwright_adapter_not_available" in detail:
            return "playwright_adapter_not_available"
        if isinstance(exc, TimeoutError) or "timeout" in name or "timeout" in detail:
            if action in {BrowserCapability.OPEN_URL.value, BrowserCapability.NAVIGATE.value, BrowserCapability.BACK.value, BrowserCapability.FORWARD.value}:
                return "browser_navigation_timeout"
            return "browser_actionability_failed"
        if "target closed" in detail or "page closed" in detail:
            return "browser_page_unavailable"
        if "stale" in detail:
            return "browser_element_stale"
        if "ambiguous" in detail:
            return "browser_element_ambiguous"
        if "actionability" in detail:
            return "browser_actionability_failed"
        if "target changed" in detail:
            return "browser_target_changed"
        if "process" in detail or "launch" in detail:
            return "browser_process_launch_failed"
        return "browser_provider_failed"
