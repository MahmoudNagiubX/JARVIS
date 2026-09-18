"""A bounded, optional Playwright backend behind the browser controller seam."""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
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
    epoch: int = 0


class PlaywrightBrowserController:
    """Run owned Playwright contexts without creating a second browser authority.

    The optional import is lazy so the normal JARVIS runtime remains usable
    without Playwright.  The legacy injected executor is retained for
    deterministic product-owned tests and compatibility with the existing
    controller seam; it is never exposed to model/tool arguments.
    """

    _MAX_TEXT = 20_000
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
            if action.action in {
                BrowserCapability.CLICK.value,
                BrowserCapability.TYPE.value,
                BrowserCapability.SELECT.value,
            }:
                return BrowserResult("failed", error_code="browser_action_requires_t3_grounding")
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
            session_id,
            context.identity.owner_id,
            context.device.device_id,
            mode,
            browser_context,
            page,
            browser,
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
        session.epoch += 1
        return BrowserResult("succeeded", {"session_id": session.session_id, "url": final_url}, verified=True)

    async def _history_action(self, session: _PlaywrightSession, *, forward: bool) -> BrowserResult:
        operation = session.page.go_forward if forward else session.page.go_back
        response = await operation(wait_until="domcontentloaded", timeout=self._NAVIGATION_TIMEOUT_MS)
        final_url = str(session.page.url)
        self._url_policy.validate(final_url)
        session.epoch += 1
        return BrowserResult("succeeded", {"session_id": session.session_id, "url": final_url, "moved": response is not None}, verified=True)

    async def _read(self, session: _PlaywrightSession, action: str) -> BrowserResult:
        page = session.page
        title = str(await page.title())[:500]
        body = await page.locator("body").inner_text(timeout=self._ACTION_TIMEOUT_MS)
        text = str(body)[: self._MAX_TEXT]
        output: dict[str, object] = {
            "session_id": session.session_id,
            "url": self._safe_page_url(page),
            "title": title,
            "text": text,
        }
        if action == BrowserCapability.READ_PAGE.value:
            output["links"] = await self._bounded_links(page)
        if action == BrowserCapability.INSPECT_ACCESSIBILITY_TREE.value:
            output["accessibility_tree"] = await self._bounded_accessibility(page)
        return BrowserResult("succeeded", output, verified=True)

    async def _find(self, session: _PlaywrightSession, parameters: Mapping[str, object]) -> BrowserResult:
        needle = parameters.get("text")
        if not isinstance(needle, str) or not needle.strip() or len(needle) > 200:
            return BrowserResult("denied", error_code="element_query_required")
        page = session.page
        locator = page.get_by_text(needle, exact=False)
        count = await locator.count()
        if count == 0:
            return BrowserResult("succeeded", {"matches": []}, verified=True)
        if count > 50:
            count = 50
        matches = []
        for index in range(count):
            item = locator.nth(index)
            try:
                matches.append({
                    "text": (await item.inner_text(timeout=self._ACTION_TIMEOUT_MS))[:200],
                    "visible": await item.is_visible(),
                    "enabled": await item.is_enabled(),
                })
            except Exception:
                continue
        return BrowserResult("succeeded", {"matches": matches}, verified=True)

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

    async def _bounded_links(self, page: Any) -> list[dict[str, str]]:
        links = page.locator("a")
        count = min(await links.count(), 100)
        output: list[dict[str, str]] = []
        for index in range(count):
            item = links.nth(index)
            try:
                output.append({
                    "text": (await item.inner_text(timeout=self._ACTION_TIMEOUT_MS))[:200],
                    "href": (await item.get_attribute("href") or "")[:4_096],
                })
            except Exception:
                continue
        return output

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
