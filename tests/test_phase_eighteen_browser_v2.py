from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.bootstrap import create_runtime
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.browser.profile import BrowserProfilePolicy, BrowserProfilePolicyError
from jarvis.browser.service import BrowserActionService, LocalBrowserController, PlaywrightBrowserController
from jarvis.browser.policy import BrowserURLPolicy
from jarvis.config import JarvisConfig
from jarvis.contracts import BrowserAction, BrowserSessionMode, DeviceIdentity, ToolContext


class PhaseEighteenBrowserV2FoundationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Browser V2 Test Owner")
        enrollment = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                self.identity.owner_id,
                "Browser V2 Test Device",
                "desktop",
                "windows",
                ("tool.request",),
                (
                    "browser.open_url",
                    "browser.read_page",
                    "browser.tabs",
                ),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(enrollment.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def test_missing_playwright_is_a_typed_failure_without_static_fallback(self) -> None:
        def missing(_: str) -> object:
            raise ModuleNotFoundError("playwright")

        result = await PlaywrightBrowserController(playwright_module_loader=missing).execute(
            BrowserAction("read_page", {"session_id": "browser-missing"}),
            ToolContext(self.identity, self.device, "browser", "browser-v2-test"),
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "playwright_adapter_not_available")
        self.assertNotEqual(result.error_code, "page_fetch_failed:HTTPError")

    async def test_provider_exception_is_normalized(self) -> None:
        def raises(_: BrowserAction, __: ToolContext) -> object:
            raise TimeoutError("provider detail must not escape")

        result = await PlaywrightBrowserController(executor=raises).execute(
            BrowserAction("navigate", {"url": "https://example.test"}),
            ToolContext(self.identity, self.device, "browser", "browser-v2-test"),
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "browser_navigation_timeout")
        self.assertNotIn("provider detail", str(result.output))

    async def test_real_controller_owns_and_closes_only_its_context_and_browser(self) -> None:
        fake = _FakePlaywrightModule()
        with patch("jarvis.browser.playwright_adapter.validate_brave_executable_path", return_value=Path("C:/Brave/brave.exe")):
            controller = PlaywrightBrowserController(
                executable_path="C:/Brave/brave.exe",
                playwright_module_loader=lambda _: fake,
                url_policy=BrowserURLPolicy(resolver=lambda _host, _port: ("93.184.216.34",)),
            )
            opened = await controller.execute(
                BrowserAction("open_url", {"url": "https://example.test"}),
                ToolContext(self.identity, self.device, "browser", "browser-v2-test"),
            )
            self.assertEqual(opened.status, "succeeded")
            self.assertEqual(fake.chromium.launch_calls, 1)
            self.assertEqual(fake.chromium.last_launch["executable_path"], str(Path("C:/Brave/brave.exe")))
            await controller.close()
        self.assertEqual(fake.chromium.browser.close_calls, 1)
        self.assertEqual(fake.chromium.browser.context.close_calls, 1)
        self.assertEqual(fake.stop_calls, 1)

    async def test_owner_persistent_mode_requires_opt_in_and_uses_dedicated_context(self) -> None:
        fake = _FakePlaywrightModule()
        with tempfile.TemporaryDirectory() as temp:
            policy = BrowserProfilePolicy(Path(temp) / "OwnerPersistent", owner_persistent_opt_in=True)
            with patch("jarvis.browser.playwright_adapter.validate_brave_executable_path", return_value=Path("C:/Brave/brave.exe")):
                controller = PlaywrightBrowserController(
                    executable_path="C:/Brave/brave.exe",
                    profile_policy=policy,
                    playwright_module_loader=lambda _: fake,
                    url_policy=BrowserURLPolicy(resolver=lambda _host, _port: ("93.184.216.34",)),
                )
                opened = await controller.execute(
                    BrowserAction("open_url", {"url": "https://example.test"}),
                    ToolContext(self.identity, self.device, "browser", "browser-v2-test"),
                    session_mode=BrowserSessionMode.OWNER_PERSISTENT,
                )
                self.assertEqual(opened.status, "succeeded")
                self.assertEqual(fake.chromium.persistent_calls, 1)
                self.assertEqual(fake.chromium.launch_calls, 0)
                await controller.close()

    async def test_default_runtime_keeps_local_browser_without_optional_dependency(self) -> None:
        self.assertIsInstance(self.runtime.browser, LocalBrowserController)
        self.assertIsNone(getattr(self.runtime.browser, "playwright", None))

    async def test_local_backend_cannot_claim_owner_persistent_execution(self) -> None:
        controller = LocalBrowserController(lambda url: ("<h1>anonymous</h1>", url))
        result = await controller.execute(
            BrowserAction("open_url", {"url": "https://example.test"}),
            ToolContext(self.identity, self.device, "browser", "browser-v2-test"),
            session_mode=BrowserSessionMode.OWNER_PERSISTENT,
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "browser_persistent_requires_playwright")

    async def test_accessibility_observation_returns_opaque_refs_not_dom_or_selectors(self) -> None:
        controller, _, _, session_id, device = await self._interactive_controller(
            [{"tag": "button", "name": "Continue", "text": "Continue"}]
        )
        observed = await controller.execute(
            BrowserAction("inspect_accessibility_tree", {"session_id": session_id}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
        )
        self.assertEqual(observed.status, "succeeded", observed)
        elements = observed.output["accessibility_tree"]["elements"]
        self.assertEqual(len(elements), 1)
        self.assertTrue(str(elements[0]["element_ref"]).startswith("browser-element-"))
        self.assertEqual(elements[0]["role"], "button")
        self.assertEqual(elements[0]["accessible_name"], "Continue")
        self.assertNotIn("html", str(observed.output).casefold())
        self.assertNotIn("selector", str(observed.output).casefold())
        self.assertNotIn("xpath", str(observed.output).casefold())

    async def test_duplicate_target_fails_closed_before_approval(self) -> None:
        controller, _, _, session_id, device = await self._interactive_controller(
            [
                {"tag": "button", "name": "Continue", "text": "Continue"},
                {"tag": "button", "name": "Continue", "text": "Continue"},
            ]
        )
        observed = await controller.execute(
            BrowserAction("inspect_accessibility_tree", {"session_id": session_id}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
        )
        ref = observed.output["accessibility_tree"]["elements"][0]["element_ref"]
        error, binding = await controller.prepare_approval(
            BrowserAction("click", {"session_id": session_id, "element_ref": ref}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
            BrowserSessionMode.EPHEMERAL,
        )
        self.assertIsNone(binding)
        self.assertIsNotNone(error)
        self.assertEqual(error.error_code, "browser_element_ambiguous")

    async def test_stale_and_removed_targets_fail_closed(self) -> None:
        controller, _, _, session_id, device = await self._interactive_controller(
            [{"tag": "button", "name": "Continue", "text": "Continue"}]
        )
        observed = await controller.execute(
            BrowserAction("inspect_accessibility_tree", {"session_id": session_id}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
        )
        ref = observed.output["accessibility_tree"]["elements"][0]["element_ref"]
        controller._sessions[session_id].bindings[ref].expires_at = 0
        error, binding = await controller.prepare_approval(
            BrowserAction("click", {"session_id": session_id, "element_ref": ref}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
            BrowserSessionMode.EPHEMERAL,
        )
        self.assertIsNone(binding)
        self.assertIsNotNone(error)
        self.assertEqual(error.error_code, "browser_element_stale")

        controller, _, page, session_id, device = await self._interactive_controller(
            [{"tag": "button", "name": "Continue", "text": "Continue"}]
        )
        observed = await controller.execute(
            BrowserAction("inspect_accessibility_tree", {"session_id": session_id}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
        )
        ref = observed.output["accessibility_tree"]["elements"][0]["element_ref"]
        page.targets.clear()
        error, binding = await controller.prepare_approval(
            BrowserAction("click", {"session_id": session_id, "element_ref": ref}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
            BrowserSessionMode.EPHEMERAL,
        )
        self.assertIsNone(binding)
        self.assertIsNotNone(error)
        self.assertEqual(error.error_code, "browser_element_stale")

    async def test_hidden_and_disabled_targets_do_not_reach_approval(self) -> None:
        for state in ({"visible": False}, {"enabled": False}):
            with self.subTest(state=state):
                controller, _, _, session_id, device = await self._interactive_controller(
                    [{"tag": "button", "name": "Continue", "text": "Continue", **state}]
                )
                observed = await controller.execute(
                    BrowserAction("inspect_accessibility_tree", {"session_id": session_id}),
                    ToolContext(self.identity, device, "browser", "browser-v2-t3"),
                )
                ref = observed.output["accessibility_tree"]["elements"][0]["element_ref"]
                service = BrowserActionService(
                    controller, self.runtime.repository, self.runtime.event_bus,
                    self.runtime.permission, self.runtime.audit, self.runtime.approval,
                )
                result = await service.execute(
                    BrowserAction("click", {"session_id": session_id, "element_ref": ref}),
                    self.identity,
                    device,
                    session_id="browser-session-context",
                    correlation_id="browser-actionability",
                )
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.error_code, "browser_actionability_failed")
                self.assertIsNone(result.approval_id)

    async def test_unique_click_requires_service_approval_and_clicks_once(self) -> None:
        controller, fake, page, session_id, device = await self._interactive_controller(
            [{"tag": "button", "name": "Continue", "text": "Continue", "href": "https://example.test/next"}]
        )
        observed = await controller.execute(
            BrowserAction("inspect_accessibility_tree", {"session_id": session_id}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
        )
        ref = observed.output["accessibility_tree"]["elements"][0]["element_ref"]
        service = BrowserActionService(
            controller, self.runtime.repository, self.runtime.event_bus,
            self.runtime.permission, self.runtime.audit, self.runtime.approval,
        )
        pending = await service.execute(
            BrowserAction("click", {"session_id": session_id, "element_ref": ref}),
            self.identity,
            device,
            session_id="browser-session-context",
            correlation_id="browser-click-once",
        )
        self.assertEqual(pending.status, "approval_required")
        completed = await service.decide(pending.approval_id or "", True, self.identity.identity_id)
        self.assertEqual(completed.status, "succeeded", completed)
        self.assertTrue(completed.verified)
        self.assertEqual(fake.chromium.browser.context.page.click_count, 1)
        self.assertEqual(page.url, "https://example.test/next")

    async def test_approval_target_drift_is_not_migrated_or_retried(self) -> None:
        controller, fake, _, session_id, device = await self._interactive_controller(
            [{"tag": "button", "name": "Continue", "text": "Continue"}]
        )
        observed = await controller.execute(
            BrowserAction("inspect_accessibility_tree", {"session_id": session_id}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
        )
        ref = observed.output["accessibility_tree"]["elements"][0]["element_ref"]
        service = BrowserActionService(
            controller, self.runtime.repository, self.runtime.event_bus,
            self.runtime.permission, self.runtime.audit, self.runtime.approval,
        )
        pending = await service.execute(
            BrowserAction("click", {"session_id": session_id, "element_ref": ref}),
            self.identity,
            device,
            session_id="browser-session-context",
            correlation_id="browser-click-drift",
        )
        self.assertEqual(pending.status, "approval_required")
        fake.chromium.browser.context.page.targets[0]["name"] = "Changed"
        changed = await service.decide(pending.approval_id or "", True, self.identity.identity_id)
        self.assertEqual(changed.status, "failed")
        self.assertEqual(changed.error_code, "browser_approval_target_changed")
        self.assertEqual(fake.chromium.browser.context.page.click_count, 0)

    async def test_removed_target_after_approval_is_not_retried(self) -> None:
        controller, fake, page, session_id, device = await self._interactive_controller(
            [{"tag": "button", "name": "Continue", "text": "Continue"}]
        )
        observed = await controller.execute(
            BrowserAction("inspect_accessibility_tree", {"session_id": session_id}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
        )
        ref = observed.output["accessibility_tree"]["elements"][0]["element_ref"]
        service = BrowserActionService(
            controller, self.runtime.repository, self.runtime.event_bus,
            self.runtime.permission, self.runtime.audit, self.runtime.approval,
        )
        pending = await service.execute(
            BrowserAction("click", {"session_id": session_id, "element_ref": ref}),
            self.identity,
            device,
            session_id="browser-session-context",
            correlation_id="browser-action-removed",
        )
        self.assertEqual(pending.status, "approval_required")
        page.targets.clear()
        changed = await service.decide(pending.approval_id or "", True, self.identity.identity_id)
        self.assertEqual(changed.status, "failed")
        self.assertEqual(changed.error_code, "browser_approval_target_changed")
        self.assertEqual(fake.chromium.browser.context.page.click_count, 0)

    async def test_navigation_and_wrong_tab_refs_fail_closed(self) -> None:
        controller, _, _, first_session, device = await self._interactive_controller(
            [{"tag": "button", "name": "Continue", "text": "Continue"}]
        )
        observed = await controller.execute(
            BrowserAction("inspect_accessibility_tree", {"session_id": first_session}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
        )
        ref = observed.output["accessibility_tree"]["elements"][0]["element_ref"]
        with patch("jarvis.browser.playwright_adapter.validate_brave_executable_path", return_value=Path("C:/Brave/brave.exe")):
            second = await controller.execute(
                BrowserAction("open_url", {"url": "https://example.test/second"}),
                ToolContext(self.identity, device, "browser", "browser-v2-t3"),
            )
        self.assertEqual(second.status, "succeeded", second)
        second_session = str(second.output["session_id"])
        error, binding = await controller.prepare_approval(
            BrowserAction("click", {"session_id": second_session, "element_ref": ref}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
            BrowserSessionMode.EPHEMERAL,
        )
        self.assertIsNone(binding)
        self.assertIsNotNone(error)
        self.assertEqual(error.error_code, "browser_element_stale")

        navigated = await controller.execute(
            BrowserAction("navigate", {"session_id": first_session, "url": "https://example.test/reloaded"}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
        )
        self.assertEqual(navigated.status, "succeeded")
        error, binding = await controller.prepare_approval(
            BrowserAction("click", {"session_id": first_session, "element_ref": ref}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
            BrowserSessionMode.EPHEMERAL,
        )
        self.assertIsNone(binding)
        self.assertIsNotNone(error)
        self.assertEqual(error.error_code, "browser_element_stale")

    async def test_type_is_sensitive_checked_and_freshly_verified(self) -> None:
        controller, _, page, session_id, device = await self._interactive_controller(
            [{"tag": "input", "name": "Search", "type": "text"}]
        )
        observed = await controller.execute(
            BrowserAction("inspect_accessibility_tree", {"session_id": session_id}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
        )
        ref = observed.output["accessibility_tree"]["elements"][0]["element_ref"]
        service = BrowserActionService(
            controller, self.runtime.repository, self.runtime.event_bus,
            self.runtime.permission, self.runtime.audit, self.runtime.approval,
        )
        pending = await service.execute(
            BrowserAction("type", {"session_id": session_id, "element_ref": ref, "text": "JARVIS"}),
            self.identity,
            device,
            session_id="browser-session-context",
            correlation_id="browser-type",
        )
        completed = await service.decide(pending.approval_id or "", True, self.identity.identity_id)
        self.assertEqual(completed.status, "succeeded", completed)
        self.assertTrue(completed.verified)
        self.assertEqual(completed.output["value_length"], 6)
        self.assertNotIn("JARVIS", str(completed.output))
        self.assertEqual(page.targets[0]["value"], "JARVIS")

    async def test_password_target_is_denied_without_reading_or_approving(self) -> None:
        controller, _, _, session_id, device = await self._interactive_controller(
            [{"tag": "input", "name": "Password", "type": "password"}]
        )
        observed = await controller.execute(
            BrowserAction("inspect_accessibility_tree", {"session_id": session_id}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
        )
        ref = observed.output["accessibility_tree"]["elements"][0]["element_ref"]
        error, binding = await controller.prepare_approval(
            BrowserAction("type", {"session_id": session_id, "element_ref": ref, "text": "secret"}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
            BrowserSessionMode.EPHEMERAL,
        )
        self.assertIsNone(binding)
        self.assertIsNotNone(error)
        self.assertEqual(error.error_code, "browser_sensitive_input_denied")

    async def test_select_is_native_and_freshly_verified(self) -> None:
        controller, _, page, session_id, device = await self._interactive_controller(
            [{"tag": "select", "name": "Country", "value": "egypt", "options": ["egypt", "canada"]}]
        )
        observed = await controller.execute(
            BrowserAction("inspect_accessibility_tree", {"session_id": session_id}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
        )
        ref = observed.output["accessibility_tree"]["elements"][0]["element_ref"]
        service = BrowserActionService(
            controller, self.runtime.repository, self.runtime.event_bus,
            self.runtime.permission, self.runtime.audit, self.runtime.approval,
        )
        pending = await service.execute(
            BrowserAction("select", {"session_id": session_id, "element_ref": ref, "value": "canada"}),
            self.identity,
            device,
            session_id="browser-session-context",
            correlation_id="browser-select",
        )
        completed = await service.decide(pending.approval_id or "", True, self.identity.identity_id)
        self.assertEqual(completed.status, "succeeded", completed)
        self.assertTrue(completed.verified)
        self.assertEqual(page.targets[0]["value"], "canada")

    async def test_uncertain_click_is_not_retried_and_is_not_claimed_verified(self) -> None:
        controller, fake, page, session_id, device = await self._interactive_controller(
            [{"tag": "button", "name": "Continue", "text": "Continue"}]
        )
        observed = await controller.execute(
            BrowserAction("inspect_accessibility_tree", {"session_id": session_id}),
            ToolContext(self.identity, device, "browser", "browser-v2-t3"),
        )
        ref = observed.output["accessibility_tree"]["elements"][0]["element_ref"]
        service = BrowserActionService(
            controller, self.runtime.repository, self.runtime.event_bus,
            self.runtime.permission, self.runtime.audit, self.runtime.approval,
        )
        pending = await service.execute(
            BrowserAction("click", {"session_id": session_id, "element_ref": ref}),
            self.identity,
            device,
            session_id="browser-session-context",
            correlation_id="browser-click-uncertain",
        )
        completed = await service.decide(pending.approval_id or "", True, self.identity.identity_id)
        self.assertEqual(completed.status, "succeeded")
        self.assertFalse(completed.verified)
        self.assertEqual(fake.chromium.browser.context.page.click_count, 1)
        self.assertEqual(page.url, "https://example.test")

    async def _interactive_controller(self, targets: list[dict[str, object]]) -> tuple[PlaywrightBrowserController, _InteractiveFakePlaywrightModule, _InteractiveFakePage, str, DeviceIdentity]:
        fake = _InteractiveFakePlaywrightModule(targets)
        device = DeviceIdentity(
            self.device.device_id,
            self.device.owner_id,
            self.device.device_kind,
            self.device.platform,
            self.device.capabilities | frozenset({"browser.click", "browser.type", "browser.select"}),
            self.device.scopes,
        )
        with patch("jarvis.browser.playwright_adapter.validate_brave_executable_path", return_value=Path("C:/Brave/brave.exe")):
            controller = PlaywrightBrowserController(
                executable_path="C:/Brave/brave.exe",
                playwright_module_loader=lambda _: fake,
                url_policy=BrowserURLPolicy(resolver=lambda _host, _port: ("93.184.216.34",)),
            )
            opened = await controller.execute(
                BrowserAction("open_url", {"url": "https://example.test"}),
                ToolContext(self.identity, device, "browser", "browser-v2-t3"),
            )
        return controller, fake, fake.chromium.browser.context.page, str(opened.output["session_id"]), device

    async def test_browser_tool_schemas_do_not_expose_session_mode_or_raw_execution(self) -> None:
        browser_specs = [spec for spec in self.runtime.tools.list() if spec.name.startswith("browser.")]
        self.assertTrue(browser_specs)
        by_name = {spec.name: spec for spec in browser_specs}
        for spec in browser_specs:
            properties = set(spec.parameters_schema.get("properties", {}))
            self.assertNotIn("session_mode", properties)
            self.assertNotIn("evaluate", properties)
            self.assertNotIn("javascript", properties)
            self.assertNotIn("cdp", properties)
        self.assertNotIn("selector", by_name["browser.find_element"].parameters_schema["properties"])
        for action in ("click", "type", "select"):
            schema = by_name[f"browser.{action}"].parameters_schema
            self.assertIn("element_ref", schema["properties"])
            self.assertNotIn("selector", schema["properties"])
            self.assertIn("element_ref", schema["required"])


class PhaseEighteenBrowserV2ProfileTests(unittest.TestCase):
    def test_normal_brave_profile_is_rejected(self) -> None:
        normal = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "BraveSoftware" / "Brave-Browser" / "User Data"
        with self.assertRaisesRegex(BrowserProfilePolicyError, "normal_browser_profile"):
            BrowserProfilePolicy.validate_dedicated_profile_path(normal)

    def test_chrome_and_edge_profiles_are_rejected(self) -> None:
        local = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
        for candidate in (
            local / "Google" / "Chrome" / "User Data",
            local / "Microsoft" / "Edge" / "User Data",
        ):
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(BrowserProfilePolicyError, "normal_browser_profile"):
                    BrowserProfilePolicy.validate_dedicated_profile_path(candidate)

    def test_ephemeral_profile_has_no_durable_user_data_directory(self) -> None:
        policy = BrowserProfilePolicy(None, owner_persistent_opt_in=False)
        self.assertIsNone(policy.persistent_user_data_dir())
        with self.assertRaisesRegex(BrowserProfilePolicyError, "owner_persistent_opt_in_required"):
            policy.persistent_user_data_dir(required=True)

    def test_persistent_profile_requires_explicit_opt_in_and_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "JARVIS" / "Browser" / "OwnerPersistent"
            policy = BrowserProfilePolicy(root, owner_persistent_opt_in=True)
            self.assertEqual(policy.persistent_user_data_dir(), root.resolve())

    def test_profile_path_is_not_model_controlled(self) -> None:
        runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        try:
            for spec in runtime.tools.list():
                if spec.name.startswith("browser."):
                    self.assertNotIn("profile_root", spec.parameters_schema.get("properties", {}))
        finally:
            runtime.database.close()

    def test_config_reads_local_opt_in_without_owner_specific_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "JARVIS_BROWSER_BACKEND": "playwright",
                "JARVIS_BROWSER_HEADLESS": "true",
                "JARVIS_BROWSER_OWNER_PERSISTENT": "true",
                "JARVIS_BROWSER_PROFILE_ROOT": "C:\\Users\\Public\\JARVIS\\Browser\\OwnerPersistent",
            },
            clear=False,
        ):
            config = JarvisConfig.from_env()
        self.assertEqual(config.browser_backend, "playwright")
        self.assertTrue(config.browser_owner_persistent_opt_in)
        self.assertEqual(config.browser_profile_root, "C:\\Users\\Public\\JARVIS\\Browser\\OwnerPersistent")


class _FakePlaywrightModule:
    def __init__(self) -> None:
        self.chromium = _FakeBrowserType()
        self.stop_calls = 0

    def async_playwright(self) -> "_FakePlaywrightManager":
        return _FakePlaywrightManager(self)

    async def stop(self) -> None:
        self.stop_calls += 1


class _FakePlaywrightManager:
    def __init__(self, module: _FakePlaywrightModule) -> None:
        self._module = module

    async def start(self) -> _FakePlaywrightModule:
        return self._module


class _FakeBrowserType:
    def __init__(self) -> None:
        self.launch_calls = 0
        self.persistent_calls = 0
        self.last_launch: dict[str, object] = {}
        self.browser = _FakeBrowser()

    async def launch(self, **kwargs: object) -> "_FakeBrowser":
        self.launch_calls += 1
        self.last_launch = kwargs
        return self.browser

    async def launch_persistent_context(self, **kwargs: object) -> "_FakeContext":
        self.persistent_calls += 1
        self.last_launch = kwargs
        return self.browser.context


class _FakeBrowser:
    def __init__(self) -> None:
        self.close_calls = 0
        self.context = _FakeContext()

    async def new_context(self) -> "_FakeContext":
        return self.context

    async def close(self) -> None:
        self.close_calls += 1


class _FakeContext:
    def __init__(self) -> None:
        self.close_calls = 0

    async def new_page(self) -> "_FakePage":
        return _FakePage()

    async def close(self) -> None:
        self.close_calls += 1


class _FakePage:
    url = "about:blank"

    async def goto(self, url: str, **_: object) -> object:
        self.url = url
        return object()


class _InteractiveFakePlaywrightModule:
    def __init__(self, targets: list[dict[str, object]]) -> None:
        self.chromium = _InteractiveFakeBrowserType(targets)
        self.stop_calls = 0

    def async_playwright(self) -> "_InteractiveFakePlaywrightManager":
        return _InteractiveFakePlaywrightManager(self)

    async def stop(self) -> None:
        self.stop_calls += 1


class _InteractiveFakePlaywrightManager:
    def __init__(self, module: _InteractiveFakePlaywrightModule) -> None:
        self.module = module

    async def start(self) -> _InteractiveFakePlaywrightModule:
        return self.module


class _InteractiveFakeBrowserType:
    def __init__(self, targets: list[dict[str, object]]) -> None:
        self.browser = _InteractiveFakeBrowser(targets)

    async def launch(self, **_: object) -> "_InteractiveFakeBrowser":
        return self.browser

    async def launch_persistent_context(self, **_: object) -> "_InteractiveFakeContext":
        return self.browser.context


class _InteractiveFakeBrowser:
    def __init__(self, targets: list[dict[str, object]]) -> None:
        self.context = _InteractiveFakeContext(targets)

    async def new_context(self) -> "_InteractiveFakeContext":
        return self.context

    async def close(self) -> None:
        return None


class _InteractiveFakeContext:
    def __init__(self, targets: list[dict[str, object]]) -> None:
        self.page = _InteractiveFakePage(targets)

    async def new_page(self) -> "_InteractiveFakePage":
        return self.page

    async def close(self) -> None:
        return None


class _InteractiveFakePage:
    def __init__(self, targets: list[dict[str, object]]) -> None:
        self.targets = targets
        self.url = "about:blank"
        self.click_count = 0

    async def goto(self, url: str, **_: object) -> object:
        self.url = url
        return object()

    async def title(self) -> str:
        return "Test page"

    def locator(self, selector: str) -> "_InteractiveFakeLocator":
        return _InteractiveFakeLocator(self, self._select(selector))

    def get_by_role(self, role: str, *, name: str | None = None, exact: bool = False) -> "_InteractiveFakeLocator":
        selected = [target for target in self.targets if _target_role(target) == role and (name is None or (target.get("name", "") == name if exact else name.casefold() in str(target.get("name", "")).casefold()))]
        return _InteractiveFakeLocator(self, selected)

    def _select(self, selector: str) -> list[dict[str, object]]:
        normalized = selector.casefold()
        if normalized == "body":
            return [{"tag": "body", "text": "Test page"}]
        role = None
        if "[role=" in normalized:
            role = normalized.split("[role=", 1)[1].split("]", 1)[0].strip("\"'")
        tag = normalized.split(":", 1)[0].split("[", 1)[0]
        selected = []
        for target in self.targets:
            target_tag = str(target.get("tag", "")).casefold()
            target_role = _target_role(target)
            if role is not None:
                if str(target.get("role", "")).casefold() != role:
                    continue
            elif tag and target_tag != tag:
                continue
            if ":not([role])" in normalized and target.get("role"):
                continue
            if ":not([type=\"hidden\"])" in normalized and str(target.get("type", "")).casefold() == "hidden":
                continue
            selected.append(target)
        return selected


class _InteractiveFakeLocator:
    def __init__(self, page: _InteractiveFakePage, targets: list[dict[str, object]]) -> None:
        self.page = page
        self.targets = targets

    def nth(self, index: int) -> "_InteractiveFakeLocator":
        return _InteractiveFakeLocator(self.page, self.targets[index : index + 1])

    async def count(self) -> int:
        return len(self.targets)

    def _target(self) -> dict[str, object]:
        if not self.targets:
            raise LookupError("no target")
        return self.targets[0]

    async def is_visible(self) -> bool:
        return bool(self._target().get("visible", True))

    async def is_enabled(self) -> bool:
        return bool(self._target().get("enabled", True))

    async def get_attribute(self, name: str) -> str | None:
        value = self._target().get(name)
        return None if value is None else str(value)

    async def inner_text(self, **_: object) -> str:
        return str(self._target().get("text", self._target().get("name", "")))

    async def is_checked(self) -> bool:
        return bool(self._target().get("checked", False))

    async def input_value(self, **_: object) -> str:
        return str(self._target().get("value", ""))

    async def fill(self, value: str, **_: object) -> None:
        self._target()["value"] = value

    async def select_option(self, *, value: str, **_: object) -> list[str]:
        options = self._target().get("options", [])
        if value not in options:
            raise ValueError("option not found")
        self._target()["value"] = value
        return [value]

    async def click(self, **_: object) -> None:
        self.page.click_count += 1
        href = self._target().get("href")
        if href:
            self.page.url = str(href)


def _target_role(target: dict[str, object]) -> str:
    explicit = target.get("role")
    if explicit:
        return str(explicit)
    tag = str(target.get("tag", "")).casefold()
    if tag == "button":
        return "button"
    if tag == "a":
        return "link"
    if tag == "select":
        return "combobox"
    if tag in {"input", "textarea"}:
        input_type = str(target.get("type", "text")).casefold()
        return {"checkbox": "checkbox", "radio": "radio", "button": "button", "submit": "button"}.get(input_type, "textbox")
    return "generic"
