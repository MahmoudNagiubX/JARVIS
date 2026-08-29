from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BoundaryTests(unittest.TestCase):
    def test_contract_catalog_contains_required_boundary_modules(self) -> None:
        required = {
            "identity.py",
            "authorization.py",
            "approval.py",
            "audit.py",
            "model.py",
            "tools.py",
            "memory.py",
            "world.py",
            "goals.py",
            "computer.py",
            "browser.py",
            "voice.py",
            "communication.py",
        }
        actual = {path.name for path in (ROOT / "src" / "jarvis" / "contracts").glob("*.py")}
        self.assertTrue(required.issubset(actual))

    def test_phase_one_bootstrap_has_no_provider_or_transport_dependency(self) -> None:
        source = (ROOT / "src" / "jarvis" / "bootstrap.py").read_text(encoding="utf-8")
        for forbidden in ("openai", "anthropic", "ollama", "httpx", "websockets", "sounddevice"):
            self.assertNotIn(forbidden, source.lower())

    def test_project_declares_no_runtime_dependencies(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("dependencies = []", pyproject)
