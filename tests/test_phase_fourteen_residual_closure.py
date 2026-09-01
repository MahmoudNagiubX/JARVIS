from __future__ import annotations

import asyncio
import json
import threading
from datetime import UTC, datetime
from typing import Any
from urllib.request import Request, urlopen

from jarvis.api.core import CoreApplication
from jarvis.api.http import CoreHttpServer
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig


def request_json(
    base: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[Any, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(f"{base}{path}", method=method, data=body, headers=headers or {})
    with urlopen(request) as response:
        return response, json.loads(response.read().decode("utf-8"))


class TestPhaseFourteenResidualClosure:
    def setup_method(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.runtime = self.loop.run_until_complete(
            create_runtime_async()
        )
        self.application = CoreApplication(self.runtime)
        self.server = CoreHttpServer(self.application, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://{self.server.address[0]}:{self.server.address[1]}"

        self.identity = self.loop.run_until_complete(
            self.runtime.identity.bootstrap_owner("Phase Fourteen Residual Owner")
        )
        enrollment = self.loop.run_until_complete(
            self.runtime.identity.create_enrollment(
                EnrollmentGrant(
                    self.identity.owner_id,
                    "Phase Fourteen Residual Browser",
                    "desktop",
                    "windows",
                    ("tool.request",),
                    ("computer.observe", "perception.screen"),
                )
            )
        )
        issued = self.loop.run_until_complete(
            self.runtime.identity.redeem_enrollment(enrollment.code)
        )
        self.credential = issued.raw
        self.device_id = issued.device_id

    def teardown_method(self) -> None:
        self.server.shutdown()
        self.loop.run_until_complete(self.runtime.shutdown())
        self.loop.close()

    def bootstrap_session(self) -> str:
        token = self.server.issue_desktop_bootstrap(
            self.credential,
            self.device_id,
            self.identity.identity_id,
        )
        response, session = request_json(
            self.base,
            "/v1/auth/desktop-session",
            method="POST",
            payload={"bootstrap": token},
        )
        assert response.status == 201
        return response.headers["Set-Cookie"].split(";", 1)[0]

    def test_experience_state_projects_safe_notification_context_from_canonical_service(self) -> None:
        created_at = datetime.now(UTC)
        self.loop.run_until_complete(
            self.runtime.notifications.create(
                self.identity.owner_id,
                "Proactive update",
                "A local proactive update",
                source="proactive.attention",
                metadata={"private_token": "must-not-leak"},
            )
        )
        important = self.loop.run_until_complete(
            self.runtime.notifications.create(
                self.identity.owner_id,
                "System alert",
                "A critical local alert",
                severity="critical",
                source="system.runtime",
                metadata={"private_token": "must-not-leak"},
            )
        )
        cookie = self.bootstrap_session()

        response, state = request_json(
            self.base,
            "/v1/experience/state",
            headers={"Cookie": cookie},
        )

        assert response.status == 200
        notifications = {item["notification_id"]: item for item in state["notifications"]}
        proactive = next(item for item in notifications.values() if item["source"] == "proactive.attention")
        alert = notifications[important.notification_id]
        assert proactive["created_at"]
        assert datetime.fromisoformat(proactive["created_at"]) >= created_at
        assert proactive["important"] is False
        assert alert["source"] == "system.runtime"
        assert alert["important"] is True
        assert "metadata" not in proactive
        assert "private_token" not in json.dumps(state)


async def create_runtime_async():
    runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
    await runtime.start()
    return runtime
