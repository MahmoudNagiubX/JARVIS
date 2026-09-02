"""RED-first tests for the final Phase 17 real-network readiness closure."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from jarvis.api.core import CoreApplication, DemoPrincipal
from jarvis.api.node_http import CoreNodeHttpServer
from jarvis.authority.approvals.service import DurableApprovalEngine
from jarvis.authority.audit.service import DurableAuditService
from jarvis.authority.identity.service import IdentityService
from jarvis.authority.permissions.engine import PolicyPermissionEngine
from jarvis.bus import InMemoryEventBus
from jarvis.contracts import DeviceEnrollmentRequest, DeviceIdentity, DeviceRole, HomeAction, HomeEntity, Identity
from jarvis.devices.fabric import DeviceFabricService
from jarvis.devices.home.service import HomeActionService, InMemoryHomeTransport
from jarvis.desktop.config import DesktopProductConfig
from jarvis.desktop.instance import SingleInstanceLock
from jarvis.desktop.lifecycle import JarvisDesktopLifecycle, PRODUCT_SECRET_KEY
from jarvis.desktop.model import LocalModelDiscovery
from jarvis.desktop.secret_store import MemorySecretStore
from jarvis.desktop.startup import UserStartupManager
from jarvis.network import validation as network_validation
from jarvis.network.validation import NetworkValidationError, is_private_ip, validate_private_core_url
from jarvis.nodes.venom import VenomNode
from jarvis.persistence.db import SQLiteDatabase
from jarvis.persistence.repositories import RuntimeRepository
from jarvis.satellite_agent.agent import SatelliteAgentConfig, WindowsSatelliteAgent


def _venom_setup_module():
    path = Path(__file__).parents[1] / "scripts" / "venom" / "setup.py"
    spec = importlib.util.spec_from_file_location("phase17_venom_setup", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _desktop_lifecycle(tmp_path: Path, store: MemorySecretStore) -> JarvisDesktopLifecycle:
    database = tmp_path / "data" / "jarvis.sqlite3"
    from jarvis.config import JarvisConfig

    return JarvisDesktopLifecycle(
        config_path=tmp_path / "localappdata" / "JARVIS" / "config" / "settings.json",
        secret_store=store,
        base_config_factory=lambda: JarvisConfig(
            environment="development",
            database_path=str(database),
            model_provider="mock",
            deployment_profile="development",
        ),
        startup_manager=UserStartupManager(tmp_path / "startup"),
        instance_lock=SingleInstanceLock(tmp_path / "localappdata" / "JARVIS" / "run" / "instance.lock"),
        model_discovery=LocalModelDiscovery(runtime_root=tmp_path / "no-runtime", model_roots=(tmp_path / "no-models",)),
    )


class TestPhaseSeventeenNetworkReadinessClosure:
    def setup_method(self) -> None:
        self.db = SQLiteDatabase(":memory:")
        self.repo = RuntimeRepository(self.db)
        self.bus = InMemoryEventBus()
        self.audit = DurableAuditService(self.repo)
        self.fabric = DeviceFabricService(self.repo, self.bus, self.audit)
        self.identity_service = IdentityService(self.repo, self.bus)
        self.owner_id = self.repo.create_owner("Owner")
        identity_id = self.repo.create_identity(self.owner_id, "Owner", "owner", ("owner",))
        self.identity = Identity(identity_id, "Owner", self.owner_id, frozenset({"owner"}))
        self.runtime = SimpleNamespace(
            repository=self.repo,
            identity=self.identity_service,
            device_fabric=self.fabric,
            venom=VenomNode(),
        )
        self.app = CoreApplication(self.runtime)

    def teardown_method(self) -> None:
        if not self.db.closed:
            self.db.close()

    async def _enroll(
        self,
        device_id: str,
        *,
        role: str = DeviceRole.SERVER.value,
        capabilities: tuple[str, ...] = ("node.health",),
        owner_id: str | None = None,
    ) -> tuple[str, DeviceIdentity]:
        owner = owner_id or self.owner_id
        ticket = await self.fabric.issue_enrollment_ticket(
            owner,
            device_id,
            role=role,
            platform="linux",
            capabilities=capabilities,
        )
        result = await self.fabric.enroll_device(DeviceEnrollmentRequest(
            code=ticket.code,
            device_id=device_id,
            name=device_id,
            platform="linux",
            capabilities=frozenset(capabilities),
        ))
        assert result.accepted and result.credential
        device = await self.identity_service.device(device_id)
        assert device is not None
        return result.credential, device

    @staticmethod
    def _coordinate_pending(home: HomeActionService, approval_id: str) -> None:
        class CoordinatedPending(dict):
            def __init__(self, values):
                super().__init__(values)
                self.barrier = threading.Barrier(2)
                self.calls = 0
                self.lock = threading.Lock()

            def get(self, key, default=None):
                value = super().get(key, default)
                if key == approval_id and value is not None:
                    with self.lock:
                        self.calls += 1
                        should_wait = self.calls <= 2
                    if should_wait:
                        self.barrier.wait(timeout=5)
                return value

        home._pending_approvals = CoordinatedPending(home._pending_approvals)

    def test_owner_cidr_is_explicit_override_and_dangerous_cidrs_are_rejected(self) -> None:
        trusted = ("192.162.1.0/24",)
        assert validate_private_core_url(
            "http://192.162.1.33:8788",
            mode="live-distributed",
            trusted_lan_cidrs=trusted,
        ) == "http://192.162.1.33:8788"
        assert is_private_ip("192.162.1.2", trusted_lan_cidrs=trusted)
        assert not is_private_ip("192.162.2.10", trusted_lan_cidrs=trusted)
        assert not is_private_ip("8.8.8.8", trusted_lan_cidrs=trusted)
        assert network_validation.classify_ip("192.162.1.33", trusted) == "EXPLICIT_LOCAL_TRUST_OVERRIDE"
        with pytest.raises(NetworkValidationError):
            validate_private_core_url("http://192.162.1.33:8788", trusted_lan_cidrs=("0.0.0.0/0",))
        with pytest.raises(NetworkValidationError):
            validate_private_core_url("http://192.162.1.33:8788", trusted_lan_cidrs=("::/0",))

    def test_default_policy_keeps_owner_lan_blocked_and_safe_private_lan_allowed(self) -> None:
        assert validate_private_core_url("http://192.168.1.10:8788", mode="live-distributed") == "http://192.168.1.10:8788"
        assert validate_private_core_url("http://10.0.0.10:8788", mode="live-distributed") == "http://10.0.0.10:8788"
        assert validate_private_core_url("http://172.20.0.10:8788", mode="live-distributed") == "http://172.20.0.10:8788"
        with pytest.raises(NetworkValidationError):
            validate_private_core_url("http://192.162.1.33:8788", mode="live-distributed")
        with pytest.raises(NetworkValidationError):
            validate_private_core_url("http://8.8.8.8:8788", mode="live-distributed")

    def test_windows_satellite_accepts_configured_owner_lan_and_blocks_public_url(self) -> None:
        config = SatelliteAgentConfig(
            core_url="http://192.162.1.33:8788",
            owner_id=self.owner_id,
            identity_id=self.identity.identity_id,
            device_id="satellite-1",
            capabilities=frozenset({"computer.observe"}),
            trusted_lan_cidrs=("192.162.1.0/24",),
        )
        WindowsSatelliteAgent(config, "credential")
        with pytest.raises(ValueError):
            WindowsSatelliteAgent(replace(config, core_url="http://8.8.8.8:8788"), "credential")

    def test_node_server_uses_the_same_trusted_lan_policy_for_bind_and_client_ip(self) -> None:
        with pytest.raises(ValueError):
            CoreNodeHttpServer(self.app, host="192.162.1.33", port=8788)
        server = CoreNodeHttpServer(
            self.app,
            host="192.162.1.33",
            port=8788,
            trusted_lan_cidrs=("192.162.1.0/24",),
        )
        assert server.host == "192.162.1.33"
        assert is_private_ip("192.162.1.2", trusted_lan_cidrs=server.trusted_lan_cidrs)

    def test_only_bound_server_device_can_publish_venom_heartbeat(self) -> None:
        async def scenario() -> None:
            _, venom_device = await self._enroll("venom-1")
            venom_principal = DemoPrincipal(self.identity, venom_device)
            accepted = await self.app.venom_heartbeat(venom_principal, {"healthy": True, "details": "ok"})
            assert accepted["accepted"] is True

            _, room_device = await self._enroll("room-1", role=DeviceRole.ROOM_SATELLITE.value)
            with pytest.raises(PermissionError):
                await self.app.venom_heartbeat(DemoPrincipal(self.identity, room_device), {"healthy": True})

            _, desktop_device = await self._enroll("desktop-1", role=DeviceRole.PRIMARY_PC.value)
            with pytest.raises(PermissionError):
                await self.app.venom_heartbeat(DemoPrincipal(self.identity, desktop_device), {"healthy": True})

            other_owner = self.repo.create_owner("Other")
            other_identity_id = self.repo.create_identity(other_owner, "Other", "owner", ("owner",))
            other_identity = Identity(other_identity_id, "Other", other_owner, frozenset({"owner"}))
            forged = DeviceIdentity("venom-1", other_owner, DeviceRole.SERVER.value, "linux", frozenset({"node.health"}))
            with pytest.raises(PermissionError):
                await self.app.venom_heartbeat(DemoPrincipal(other_identity, forged), {"healthy": True})

            _, revoked_device = await self._enroll("venom-revoked")
            await self.fabric.revoke(self.owner_id, revoked_device.device_id)
            with pytest.raises(PermissionError):
                await self.app.venom_heartbeat(DemoPrincipal(self.identity, revoked_device), {"healthy": True})

        asyncio.run(scenario())

    def test_detailed_node_health_requires_authentication_but_authenticated_health_passes(self) -> None:
        async def scenario() -> None:
            credential, device = await self._enroll("venom-health")
            async def health() -> dict[str, object]:
                return {"service": "jarvis-node", "state": "ready"}

            self.app.health = health  # type: ignore[method-assign]
            server = CoreNodeHttpServer(self.app, host="127.0.0.1", port=0)
            server.start()
            try:
                headers = {
                    "Authorization": f"Bearer {credential}",
                    "X-JARVIS-Device-ID": device.device_id,
                    "X-JARVIS-Identity-ID": self.identity.identity_id,
                }
                for path in ("/health", "/nodes/health", "/venom/health", "/nodes/venom/health"):
                    url = f"http://127.0.0.1:{server.port}{path}"
                    with pytest.raises(HTTPError) as error:
                        urlopen(Request(url), timeout=3)
                    assert error.value.code == 401
                    with urlopen(Request(url, headers=headers), timeout=3) as response:
                        assert response.status == 200
                        payload = json.loads(response.read().decode("utf-8"))
                        assert payload
            finally:
                server.stop()

        asyncio.run(scenario())

    def test_desktop_config_round_trips_bounded_node_settings_without_secrets(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        config = DesktopProductConfig(
            distributed_fabric_enabled=True,
            node_bind_host="192.162.1.33",
            node_port=8788,
            trusted_lan_cidrs=("192.162.1.0/24",),
        )
        config.save(path)
        loaded = DesktopProductConfig.load(path)
        assert loaded.distributed_fabric_enabled is True
        assert loaded.node_bind_host == "192.162.1.33"
        assert loaded.node_port == 8788
        assert loaded.trusted_lan_cidrs == ("192.162.1.0/24",)
        assert "credential" not in path.read_text(encoding="utf-8").casefold()

    def test_desktop_start_automatically_starts_and_stops_one_node_server(self, tmp_path: Path) -> None:
        async def scenario() -> None:
            store = MemorySecretStore()
            lifecycle = _desktop_lifecycle(tmp_path, store)
            setup = await lifecycle.setup(enable_voice=False)
            settings = DesktopProductConfig.load(lifecycle.config_path)
            replace(
                settings,
                distributed_fabric_enabled=True,
                node_bind_host="127.0.0.1",
                node_port=0,
            ).save(lifecycle.config_path)

            started = await lifecycle.start()
            assert started.node_transport_state == "online"
            assert lifecycle._node_server is not None
            assert lifecycle.runtime is not None
            assert lifecycle.identity is not None
            assert store.get(PRODUCT_SECRET_KEY)

            second = _desktop_lifecycle(tmp_path, store)
            assert (await second.start()).reason == "already_running"
            await lifecycle.stop()
            assert lifecycle._node_server is None

        asyncio.run(scenario())

    def test_venom_provisioner_installs_and_import_smoke_checks_a_local_package(self, tmp_path: Path) -> None:
        setup = _venom_setup_module()
        commands: list[list[str]] = []

        def runner(command: list[str]) -> tuple[int, str]:
            commands.append(command)
            return 0, "ok"

        result = setup.provision(
            install_dir=tmp_path / "opt" / "jarvis-venom",
            config_dir=tmp_path / "etc" / "jarvis",
            data_dir=tmp_path / "var" / "lib" / "jarvis" / "backups",
            log_dir=tmp_path / "var" / "log" / "jarvis",
            systemd_dir=tmp_path / "etc" / "systemd" / "system",
            source_dir=Path(__file__).parents[1],
            command_runner=runner,
            start_service=True,
        )
        assert result["status"] == "success"
        assert "create_virtualenv" in result["steps_completed"]
        assert "install_local_package" in result["steps_completed"]
        assert "import_smoke" in result["steps_completed"]
        assert any("--no-index" in command for command in commands)
        assert any(command[-1] == "import jarvis; import jarvis.nodes.venom_daemon" for command in commands)

        real_root = tmp_path / "real"
        real_result = setup.provision(
            install_dir=real_root / "opt" / "jarvis-venom",
            config_dir=real_root / "etc" / "jarvis",
            data_dir=real_root / "var" / "lib" / "jarvis" / "backups",
            log_dir=real_root / "var" / "log" / "jarvis",
            systemd_dir=real_root / "etc" / "systemd" / "system",
            source_dir=Path(__file__).parents[1],
        )
        assert real_result["status"] == "success"
        assert real_result["package_install_mode"] in {"offline_pip", "bounded_source_copy"}
        assert (real_root / "etc" / "systemd" / "system" / "jarvis-venom.service").is_file()

    def test_venom_provisioner_reports_package_or_systemd_failure(self, tmp_path: Path) -> None:
        setup = _venom_setup_module()

        def runner(command: list[str]) -> tuple[int, str]:
            if "venv" in command or "pip" in command:
                return 1, "package operation failed"
            return 0, "ok"

        result = setup.provision(
            install_dir=tmp_path / "opt" / "jarvis-venom",
            config_dir=tmp_path / "etc" / "jarvis",
            source_dir=Path(__file__).parents[1],
            command_runner=runner,
        )
        assert result["status"] == "failed"
        assert result["failed_step"] in {"create_virtualenv", "install_local_package"}

    def test_concurrent_home_approval_executes_one_external_action(self) -> None:
        class CountingTransport(InMemoryHomeTransport):
            def __init__(self) -> None:
                super().__init__((HomeEntity("climate.office", "Office HVAC", "climate", "off", {"temperature": 20}, "office"),))
                self.calls = 0
                self._lock = threading.Lock()

            async def execute(self, action: HomeAction):
                with self._lock:
                    self.calls += 1
                await asyncio.sleep(0.05)
                return await super().execute(action)

        async def scenario() -> None:
            transport = CountingTransport()
            approval = DurableApprovalEngine(self.repo)
            home = HomeActionService(
                transport,
                self.repo,
                self.bus,
                PolicyPermissionEngine(),
                self.audit,
                approval=approval,
            )
            action = HomeAction("climate.office", "set_temperature", {"temperature": 35}, dry_run=False)
            requested = await home.execute(action, self.identity, DeviceIdentity("desktop", self.owner_id, "desktop", "windows", frozenset({"home.control"}), frozenset({"tool.request"})))
            assert requested.approval_id
            self._coordinate_pending(home, requested.approval_id)

            results = await asyncio.gather(*(
                asyncio.to_thread(lambda: asyncio.run(home.decide_approval(requested.approval_id, True, self.identity.identity_id))),
                asyncio.to_thread(lambda: asyncio.run(home.decide_approval(requested.approval_id, True, self.identity.identity_id))),
            ))
            assert sum(result.status == "succeeded" for result in results) == 1
            assert transport.calls == 1
            assert self.repo.approval(requested.approval_id)["status"] == "approved"

        asyncio.run(scenario())

    def test_approve_deny_race_has_one_canonical_decision(self) -> None:
        async def scenario() -> None:
            transport = InMemoryHomeTransport((HomeEntity("climate.office", "Office HVAC", "climate", "off", {"temperature": 20}, "office"),))
            approval = DurableApprovalEngine(self.repo)
            home = HomeActionService(transport, self.repo, self.bus, PolicyPermissionEngine(), self.audit, approval=approval)
            device = DeviceIdentity("desktop", self.owner_id, "desktop", "windows", frozenset({"home.control"}), frozenset({"tool.request"}))
            requested = await home.execute(HomeAction("climate.office", "set_temperature", {"temperature": 35}, dry_run=False), self.identity, device)
            assert requested.approval_id
            self._coordinate_pending(home, requested.approval_id)
            results = await asyncio.gather(*(
                asyncio.to_thread(lambda: asyncio.run(home.decide_approval(requested.approval_id, True, self.identity.identity_id))),
                asyncio.to_thread(lambda: asyncio.run(home.decide_approval(requested.approval_id, False, self.identity.identity_id))),
            ))
            row = self.repo.approval(requested.approval_id)
            assert row is not None
            assert row["status"] in {"approved", "rejected"}
            assert sum(result.status == "succeeded" for result in results) <= 1
            if row["status"] == "rejected":
                assert transport.entities["climate.office"].attributes["temperature"] == 20

        asyncio.run(scenario())

    def test_restart_after_approval_cannot_replay_raw_home_action(self) -> None:
        class CountingTransport(InMemoryHomeTransport):
            def __init__(self) -> None:
                super().__init__((HomeEntity("climate.office", "Office HVAC", "climate", "off", {"temperature": 20}, "office"),))
                self.calls = 0

            async def execute(self, action: HomeAction):
                self.calls += 1
                return await super().execute(action)

        async def scenario() -> None:
            transport = CountingTransport()
            approval = DurableApprovalEngine(self.repo)
            home = HomeActionService(transport, self.repo, self.bus, PolicyPermissionEngine(), self.audit, approval=approval)
            device = DeviceIdentity("desktop", self.owner_id, "desktop", "windows", frozenset({"home.control"}), frozenset({"tool.request"}))
            requested = await home.execute(HomeAction("climate.office", "set_temperature", {"temperature": 35}, dry_run=False), self.identity, device)
            assert requested.approval_id
            completed = await home.decide_approval(requested.approval_id, True, self.identity.identity_id)
            assert completed.status == "succeeded"
            assert transport.calls == 1

            restarted = HomeActionService(transport, self.repo, self.bus, PolicyPermissionEngine(), self.audit, approval=approval)
            replay = await restarted.decide_approval(requested.approval_id, True, self.identity.identity_id)
            assert replay.status == "failed"
            assert replay.error_code == "pending_action_unavailable_after_restart"
            assert transport.calls == 1

        asyncio.run(scenario())


if __name__ == "__main__":
    pytest.main([__file__])
