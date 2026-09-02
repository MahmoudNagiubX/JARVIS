from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from jarvis.api.core import CoreApplication
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig


class PhaseNineProfileTests(unittest.IsolatedAsyncioTestCase):
    def test_satellite_profile_live_distributed_accepts_private_lan_and_rejects_loopback(self) -> None:
        # Valid private-LAN core URL in live-distributed
        values = {
            "JARVIS_ENVIRONMENT": "test",
            "JARVIS_DEPLOYMENT_PROFILE": "live-distributed",
            "JARVIS_RUNTIME_ROLE": "satellite",
            "JARVIS_NODE_ID": "office-windows-01",
            "JARVIS_CORE_URL": "http://192.168.1.50:8788",
            "JARVIS_MODEL_LOOPBACK_ENDPOINT": "http://127.0.0.1:11434",
            "JARVIS_VOICE_INPUT_ADAPTER": "noop",
            "JARVIS_VOICE_OUTPUT_ADAPTER": "noop",
        }
        with patch.dict(os.environ, values, clear=False):
            config = JarvisConfig.from_env()
        self.assertEqual(config.deployment_profile, "live-distributed")
        self.assertEqual(config.runtime_role, "satellite")
        self.assertEqual(config.node_id, "office-windows-01")
        self.assertEqual(config.core_url, "http://192.168.1.50:8788")
        self.assertEqual(config.model_loopback_endpoint, "http://127.0.0.1:11434")

        # Explicit loopback rejection in live-distributed
        loopback_values = dict(values, JARVIS_CORE_URL="http://127.0.0.1:8787")
        with patch.dict(os.environ, loopback_values, clear=False):
            with self.assertRaisesRegex(ValueError, "JARVIS_CORE_URL"):
                JarvisConfig.from_env()

        # Loopback accepted in live-workstation
        workstation_values = dict(values, JARVIS_DEPLOYMENT_PROFILE="live-workstation", JARVIS_CORE_URL="http://127.0.0.1:8787")
        with patch.dict(os.environ, workstation_values, clear=False):
            cfg_ws = JarvisConfig.from_env()
            self.assertEqual(cfg_ws.core_url, "http://127.0.0.1:8787")

    def test_public_core_and_model_endpoints_are_rejected(self) -> None:
        base = {
            "JARVIS_ENVIRONMENT": "test",
            "JARVIS_DEPLOYMENT_PROFILE": "live-distributed",
            "JARVIS_RUNTIME_ROLE": "satellite",
            "JARVIS_NODE_ID": "satellite-01",
            "JARVIS_CORE_URL": "http://192.0.2.1:8787",
            "JARVIS_MODEL_LOOPBACK_ENDPOINT": "http://127.0.0.1:11434",
        }
        with patch.dict(os.environ, base, clear=False):
            with self.assertRaisesRegex(ValueError, "JARVIS_CORE_URL"):
                JarvisConfig.from_env()

        base["JARVIS_CORE_URL"] = "http://192.168.1.50:8788"
        base["JARVIS_MODEL_LOOPBACK_ENDPOINT"] = "http://198.51.100.10:11434"
        with patch.dict(os.environ, base, clear=False):
            with self.assertRaisesRegex(ValueError, "JARVIS_OLLAMA_BASE_URL"):
                JarvisConfig.from_env()

    async def test_health_exposes_topology_without_credentials(self) -> None:
        runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:", node_id="core-test"))
        await runtime.start()
        try:
            health = await CoreApplication(runtime).health()
            self.assertEqual(health["runtime_profile"]["node_id"], "core-test")
            self.assertEqual(health["node_transport"]["transport"], "http-long-poll")
            self.assertNotIn("credential", str(health).casefold())
        finally:
            await runtime.shutdown()


if __name__ == "__main__":
    unittest.main()
