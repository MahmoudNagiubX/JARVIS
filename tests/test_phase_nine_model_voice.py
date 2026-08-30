from __future__ import annotations

import unittest

from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.models.probes import LocalModelCapabilityProbe
from jarvis.models.routing import ModelRoute


class PhaseNineModelVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_probe_is_explicit_and_voice_has_one_runtime_authority(self) -> None:
        runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await runtime.start()
        try:
            self.assertIs(runtime.voice, runtime.notification_delivery.voice_core)
            self.assertEqual(runtime.config.model_loopback_endpoint, "http://127.0.0.1:11434")
            probe = await LocalModelCapabilityProbe(runtime.models).run(
                ModelRoute.GENERAL_REASONING,
                exercise_generation=True,
            )
            self.assertTrue(probe.available)
            self.assertTrue(probe.generation_checked)
            self.assertIn("chat", probe.capabilities)
        finally:
            await runtime.shutdown()


if __name__ == "__main__":
    unittest.main()
