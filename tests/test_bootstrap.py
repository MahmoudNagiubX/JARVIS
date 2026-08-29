from __future__ import annotations

import unittest

from jarvis.bootstrap import RuntimeState, bootstrap_runtime, create_runtime, running_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import LLMRequest, PermissionEffect


class BootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_bootstrap_emits_started_and_ready_then_shutdown_events(self) -> None:
        events = []
        runtime = create_runtime(JarvisConfig(environment="test"))
        runtime.event_bus.subscribe("*", lambda event: events.append(event.event_type))
        await runtime.start()
        self.assertEqual(runtime.state, RuntimeState.READY)
        self.assertEqual(runtime.config.environment, "test")
        self.assertEqual(events, ["system.bootstrap.started", "system.bootstrap.ready"])
        self.assertEqual((await runtime.models.generate(LLMRequest("r-1", ()))).finish_reason, "not_configured")
        decision = await runtime.permission.evaluate(None, None, "anything")
        self.assertEqual(decision.effect, PermissionEffect.DENY)
        await runtime.shutdown()
        self.assertEqual(runtime.state, RuntimeState.STOPPED)
        self.assertTrue(runtime.event_bus.closed)

    async def test_running_context_cleans_up(self) -> None:
        async with running_runtime(JarvisConfig(environment="test")) as runtime:
            self.assertEqual(runtime.state, RuntimeState.READY)
        self.assertEqual(runtime.state, RuntimeState.STOPPED)
    async def test_bootstrap_does_not_require_external_services(self) -> None:
        runtime = await bootstrap_runtime(JarvisConfig(environment="offline-test"))
        self.assertEqual(runtime.tools.list(), ())
        self.assertEqual((await runtime.world_state.snapshot()).observations, ())
        await runtime.shutdown()
