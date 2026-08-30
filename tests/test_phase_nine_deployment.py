from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PhaseNineDeploymentTests(unittest.TestCase):
    def test_required_phase_nine_runbooks_and_evidence_are_present(self) -> None:
        required = (
            "docs/architecture/DISTRIBUTED_RUNTIME.md",
            "docs/architecture/NODE_TRANSPORT.md",
            "docs/architecture/WINDOWS_SATELLITE_LIVE.md",
            "docs/architecture/LIVE_VOICE.md",
            "docs/architecture/LIVE_MODEL_RUNTIME.md",
            "docs/development/TUNNEL_SETUP.md",
            "docs/phase09/WORKSTATION_INVENTORY.md",
            "docs/phase09/evidence/WORKSTATION_INVENTORY.json",
            "docs/audits/MEGA_PHASE_09_REVIEW.md",
        )
        for relative in required:
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_satellite_launcher_requires_external_secret_and_uses_typed_entrypoint(self) -> None:
        script = (ROOT / "scripts/phase09/run_windows_satellite.ps1").read_text(encoding="utf-8")
        self.assertIn("JARVIS_SATELLITE_CREDENTIAL", script)
        self.assertIn("python -m jarvis.satellite_agent", script)
        self.assertNotIn("ollama pull", script.casefold())
        self.assertNotIn("Invoke-WebRequest", script)


if __name__ == "__main__":
    unittest.main()
