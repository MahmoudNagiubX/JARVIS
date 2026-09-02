from __future__ import annotations

import asyncio
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jarvis.api.core import CoreApplication, DemoPrincipal
from jarvis.api.http import CoreHttpServer
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import ComputerAction, ComputerResult, ToolContext
from jarvis.satellite_agent import SatelliteAgentConfig, WindowsSatelliteAgent


class _AgentController:
    async def execute(self, action, context):
        return ComputerResult("succeeded", {"action": action.action, "dry_run": action.dry_run}, verified=True)


class PhaseNineHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        identity = await self.runtime.identity.bootstrap_owner("Phase Nine HTTP Owner")
        enrollment = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                identity.owner_id,
                "HTTP Windows Satellite",
                "desktop",
                "windows",
                ("tool.request",),
                ("computer.observe",),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(enrollment.code)
        device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert device is not None
        self.principal = DemoPrincipal(identity, device, issued.raw)
        self.server = CoreHttpServer(CoreApplication(self.runtime), port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    async def asyncTearDown(self) -> None:
        await asyncio.to_thread(self.server.shutdown)
        self.thread.join(timeout=2)
        await self.runtime.shutdown()

    def _request(self, method: str, path: str, payload: dict[str, object] | None = None, *, auth: bool = True) -> tuple[int, dict[str, object]]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        if auth:
            headers.update(
                {
                    "Authorization": f"Bearer {self.principal.credential}",
                    "X-JARVIS-Device-ID": self.principal.device.device_id,
                    "X-JARVIS-Identity-ID": self.principal.identity.identity_id,
                }
            )
        request = Request(f"http://127.0.0.1:{self.server.address[1]}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            finally:
                exc.close()

    async def test_http_transport_routes_use_header_auth_and_typed_session(self) -> None:
        status, welcome = await asyncio.to_thread(
            self._request,
            "POST",
            "/v1/satellites/connect",
            {
                "device_id": self.principal.device.device_id,
                "owner_id": self.principal.identity.owner_id,
                "platform": "windows",
                "capabilities": ["computer.observe"],
            },
        )
        self.assertEqual(status, 201)
        self.assertTrue(welcome["accepted"])

        status, empty = await asyncio.to_thread(
            self._request,
            "GET",
            f"/v1/satellites/commands?session_id={welcome['session_id']}&wait_seconds=0",
        )
        self.assertEqual(status, 200)
        self.assertIsNone(empty["command"])

        status, heartbeat = await asyncio.to_thread(
            self._request,
            "POST",
            "/v1/satellites/heartbeat",
            {"session_id": welcome["session_id"], "sequence": 1},
        )
        self.assertEqual(status, 200)
        self.assertTrue(heartbeat["accepted"])

    async def test_http_private_route_rejects_missing_or_query_credentials(self) -> None:
        status, payload = await asyncio.to_thread(
            self._request,
            "GET",
            "/v1/satellites/commands?session_id=none&wait_seconds=0",
            auth=False,
        )
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "principal_not_found")

        status, payload = await asyncio.to_thread(
            self._request,
            "GET",
            "/v1/satellites/commands?credential=secret&wait_seconds=0",
            auth=False,
        )
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "principal_not_found")
        self.assertEqual(CoreHttpServer.PUBLIC_GET_ROUTES, frozenset({"/health", "/hud", "/experience/hud"}))

    async def test_real_agent_and_core_complete_typed_command_over_loopback_http(self) -> None:
        agent = WindowsSatelliteAgent(
            SatelliteAgentConfig(
                f"http://127.0.0.1:{self.server.address[1]}",
                self.principal.identity.owner_id,
                self.principal.identity.identity_id,
                self.principal.device.device_id,
                frozenset({"computer.observe"}),
            ),
            self.principal.credential or "",
            network_mode="test",
            controller=_AgentController(),
        )
        await agent.connect()
        task = asyncio.create_task(
            self.runtime.computer.execute(
                ComputerAction("list_processes", dry_run=True),
                ToolContext(self.principal.identity, self.principal.device, "http-agent", "http-command"),
            )
        )
        observation = await agent.poll_once(wait_seconds=2)
        result = await asyncio.wait_for(task, timeout=2)
        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertEqual(observation.status, "completed")
        self.assertEqual(result.status.value, "succeeded")
        self.assertTrue(result.verified)
        self.assertTrue(await agent.disconnect())


if __name__ == "__main__":
    unittest.main()
