from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.bootstrap import create_runtime
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.browser.profile import BrowserProfilePolicy, BrowserProfilePolicyError
from jarvis.browser.service import LocalBrowserController, PlaywrightBrowserController
from jarvis.browser.policy import BrowserURLPolicy
from jarvis.config import JarvisConfig
from jarvis.contracts import BrowserAction, BrowserSessionMode, ToolContext


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

    async def test_browser_tool_schemas_do_not_expose_session_mode_or_raw_execution(self) -> None:
        browser_specs = [spec for spec in self.runtime.tools.list() if spec.name.startswith("browser.")]
        self.assertTrue(browser_specs)
        for spec in browser_specs:
            properties = set(spec.parameters_schema.get("properties", {}))
            self.assertNotIn("session_mode", properties)
            self.assertNotIn("evaluate", properties)
            self.assertNotIn("javascript", properties)
            self.assertNotIn("cdp", properties)


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
