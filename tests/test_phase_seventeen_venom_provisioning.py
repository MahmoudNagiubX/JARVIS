"""Tests for Phase 17 Venom node model, health inspection, and provisioning artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import unittest
from pathlib import Path
from jarvis.contracts import NodeRole, NodeStatus
from jarvis.nodes.venom import VenomNode
from scripts.venom.setup import provision
from scripts.venom.preflight import run_preflight


class TestPhaseSeventeenVenomProvisioning(unittest.TestCase):
    def test_venom_node_initial_state_and_plan(self):
        venom = VenomNode()
        plan = venom.plan()
        self.assertEqual(plan.descriptor.role, NodeRole.SERVER)
        self.assertFalse(plan.heavy_inference)
        self.assertIn("mqtt_broker", plan.descriptor.capabilities)
        self.assertIn("backup_receiver", plan.descriptor.capabilities)
        self.assertEqual(venom.status, NodeStatus.NOT_CONFIGURED.value)
        self.assertEqual(venom.version, "phase17")

    def test_venom_health_and_storage_monitoring(self):
        venom = VenomNode()
        venom.set_health(True, "health_probed")
        self.assertEqual(venom.status, NodeStatus.ONLINE.value)

        # Update storage: 100 GB total, 80 GB free -> 20 GB used (20% usage -> healthy)
        st = venom.update_storage_health(100 * (1024**3), 80 * (1024**3), 20 * (1024**3))
        self.assertEqual(st.status, "healthy")
        self.assertEqual(st.usage_percent, 20.0)

        # Update storage: 90% usage -> warning
        st_warn = venom.update_storage_health(100 * (1024**3), 10 * (1024**3), 90 * (1024**3))
        self.assertEqual(st_warn.status, "warning")

        # Update service health
        srv = venom.update_service_health("mosquitto", True, "active (running)")
        self.assertTrue(srv.active)
        self.assertEqual(srv.status, "active (running)")

        details = venom.detailed_health()
        self.assertEqual(details.status, NodeStatus.ONLINE.value)
        self.assertIsNotNone(details.storage)
        self.assertTrue(details.mqtt_healthy)
        self.assertTrue(any(s.service_name == "mosquitto" for s in details.services))

    def test_venom_backup_verification(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            venom = VenomNode()
            backup_file = tmp_path / "jarvis_backup.sqlite3"

            # Valid SQLite file with header
            header = b"SQLite format 3\000" + b"\x00" * 500
            backup_file.write_bytes(header)
            expected_sha = hashlib.sha256(header).hexdigest()

            result = venom.verify_backup(backup_file, expected_sha256=expected_sha)
            self.assertTrue(result["valid"])
            self.assertEqual(result["sha256"], expected_sha)

            # Corrupt header test
            bad_file = tmp_path / "corrupt.sqlite3"
            bad_file.write_bytes(b"INVALID_HEADER_DATA_1234567890" * 10)
            bad_result = venom.verify_backup(bad_file)
            self.assertFalse(bad_result["valid"])
            self.assertEqual(bad_result["reason"], "invalid_sqlite_header")

    def test_venom_deployment_status_gate(self):
        venom = VenomNode()
        old_env = os.environ.pop("JARVIS_VENOM_HOST", None)
        try:
            self.assertEqual(venom.deployment_status(), "BLOCKED_WAITING_FOR_CONNECTION_DETAILS")
        finally:
            if old_env is not None:
                os.environ["JARVIS_VENOM_HOST"] = old_env

    def test_venom_preflight_and_setup_dry_run(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            preflight = run_preflight()
            self.assertIn("platform", preflight)
            self.assertIn("python_supported", preflight)

            install_dir = tmp_path / "opt" / "venom"
            config_dir = tmp_path / "etc" / "jarvis"
            prov_result = provision(install_dir, config_dir, dry_run=True)
            self.assertTrue(prov_result["dry_run"])
            self.assertIn("generate_config", prov_result["steps_completed"])

            real_prov = provision(install_dir, config_dir, dry_run=False)
            self.assertTrue((config_dir / "venom.json").exists())
            self.assertTrue((config_dir / "jarvis-venom.service").exists())
            self.assertIn("created_directories", real_prov["steps_completed"])

    def test_venom_daemon_module_exists_and_importable(self):
        import importlib
        mod = importlib.import_module("jarvis.nodes.venom_daemon")
        self.assertTrue(hasattr(mod, "VenomDaemon") or hasattr(mod, "main") or hasattr(mod, "run_daemon"))

    def test_venom_health_check_truthful_probes(self):
        from scripts.venom.health_check import check_health
        health = check_health()
        self.assertIn("services", health)
        self.assertIn("storage", health)
        for srv in health["services"]:
            self.assertIn("name", srv)
            self.assertIn("status", srv)
            # On Windows without active Linux services, status must NOT be hardcoded "running"
            self.assertIn(srv["status"], {"active", "inactive", "unknown", "failed", "stopped"})

    def test_venom_health_check_aggregate_status_requires_active_services(self):
        import shutil
        from unittest.mock import patch
        from scripts.venom.health_check import check_health

        fake_disk = shutil._ntuple_diskusage(100 * (1024**3), 20 * (1024**3), 80 * (1024**3))

        with patch("shutil.disk_usage", return_value=fake_disk):
            # Case 1: Services unknown or inactive -> aggregate status MUST be warning, NOT healthy
            with patch("scripts.venom.health_check.probe_service_status", return_value="unknown"):
                health_unknown = check_health()
                self.assertEqual(health_unknown["status"], "warning")

            with patch("scripts.venom.health_check.probe_service_status", return_value="inactive"):
                health_inactive = check_health()
                self.assertEqual(health_inactive["status"], "warning")

            # Case 2: Services active and storage ample -> aggregate status is healthy
            with patch("scripts.venom.health_check.probe_service_status", return_value="active"):
                health_active = check_health()
                self.assertEqual(health_active["status"], "healthy")

            # Case 3: A service failed -> aggregate status is unhealthy
            with patch("scripts.venom.health_check.probe_service_status", return_value="failed"):
                health_failed = check_health()
                self.assertEqual(health_failed["status"], "unhealthy")


if __name__ == "__main__":
    unittest.main()
