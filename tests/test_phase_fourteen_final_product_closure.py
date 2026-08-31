from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import pytest

from jarvis.api.core import CoreApplication
from jarvis.api.http import CoreHttpServer
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import ApprovalRequest, LLMResponse, ToolContext


REPO_ROOT = Path(__file__).resolve().parents[1]


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


def expect_error(
    base: str,
    path: str,
    *,
    method: str,
    headers: dict[str, str],
    payload: dict[str, object] | None = None,
) -> HTTPError:
    with pytest.raises(HTTPError) as raised:
        request_json(base, path, method=method, payload=payload, headers=headers)
    return raised.value


class TestPhaseFourteenFinalProductClosure:
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
            self.runtime.identity.bootstrap_owner("Phase Fourteen Closure Owner")
        )
        enrollment = self.loop.run_until_complete(
            self.runtime.identity.create_enrollment(
                EnrollmentGrant(
                    self.identity.owner_id,
                    "Phase Fourteen Closure Browser",
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
        self.device = self.loop.run_until_complete(
            self.runtime.identity.device(self.device_id)
        )
        assert self.device is not None

    def teardown_method(self) -> None:
        self.server.shutdown()
        self.loop.run_until_complete(self.runtime.shutdown())
        self.loop.close()

    def bootstrap_session(self) -> tuple[str, str]:
        bootstrap = self.server.issue_desktop_bootstrap(
            self.credential, self.device_id, self.identity.identity_id
        )
        response, session = request_json(
            self.base,
            "/v1/auth/desktop-session",
            method="POST",
            payload={"bootstrap": bootstrap},
        )
        cookie = response.headers["Set-Cookie"].split(";", 1)[0]
        return cookie, str(session["csrf_token"])

    def test_session_refresh_rotates_cookie_and_csrf_and_revokes_old_session(self) -> None:
        old_cookie, old_csrf = self.bootstrap_session()
        response, refreshed = request_json(
            self.base,
            "/v1/auth/session/refresh",
            method="POST",
            payload={},
            headers={
                "Cookie": old_cookie,
                "X-JARVIS-CSRF": old_csrf,
                "Content-Type": "application/json",
            },
        )
        new_cookie = response.headers["Set-Cookie"].split(";", 1)[0]
        assert response.status == 200
        assert new_cookie != old_cookie
        assert refreshed["csrf_token"] != old_csrf
        assert "credential" not in json.dumps(refreshed).casefold()

        old_session = expect_error(
            self.base,
            "/v1/auth/session",
            headers={"Cookie": old_cookie},
            method="GET",
        )
        assert old_session.code == 401
        current_response, current = request_json(
            self.base,
            "/v1/auth/session",
            headers={"Cookie": new_cookie},
        )
        assert current_response.status == 200
        assert current["csrf_token"] == refreshed["csrf_token"]

    def test_session_refresh_requires_cookie_csrf_and_rejects_revoked_device(self) -> None:
        cookie, csrf = self.bootstrap_session()
        missing_csrf = expect_error(
            self.base,
            "/v1/auth/session/refresh",
            method="POST",
            payload={},
            headers={"Cookie": cookie, "Content-Type": "application/json"},
        )
        assert missing_csrf.code == 401

        credential_bypass = expect_error(
            self.base,
            "/v1/auth/session/refresh",
            method="POST",
            payload={},
            headers={
                "Cookie": cookie,
                "Authorization": f"Bearer {self.credential}",
                "X-JARVIS-Device-ID": self.device_id,
                "X-JARVIS-Identity-ID": self.identity.identity_id,
                "Content-Type": "application/json",
            },
        )
        assert credential_bypass.code == 401

        self.loop.run_until_complete(self.runtime.identity.revoke_device(self.device_id))
        revoked = expect_error(
            self.base,
            "/v1/auth/session/refresh",
            method="POST",
            payload={},
            headers={
                "Cookie": cookie,
                "X-JARVIS-CSRF": csrf,
                "Content-Type": "application/json",
            },
        )
        assert revoked.code == 401

    def test_pending_approval_projection_contains_backend_run_correlation_and_is_redacted(self) -> None:
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device_id)
        conversation = self.runtime.repository.create_conversation(self.identity.owner_id, self.device_id, None)
        message = self.runtime.repository.create_message(conversation.id, session.id, None, self.device_id, "user", "approval")
        run = self.runtime.repository.create_run(conversation.id, session.id, self.device_id, message.id, "corr-closure-approval")
        self.runtime.repository.update_message_run_id(message.id, run.id)
        approval_id = "approval-closure-projection"
        self.loop.run_until_complete(
            self.runtime.approval.request(
                ApprovalRequest(
                    approval_id,
                    "tool.computer.action",
                    self.identity.owner_id,
                    self.device_id,
                    "consequential tool execution",
                    datetime.now(UTC),
                    datetime.now(UTC) + timedelta(minutes=10),
                    {"token": "must-not-leak", "preview": "safe target"},
                )
            )
        )
        self.runtime.repository.insert_tool_call(
            "tool-call-closure-projection",
            run.id,
            "computer.action",
            {"token": "must-not-leak"},
            "digest",
            "awaiting_approval",
            approval_id,
        )
        state = self.loop.run_until_complete(
            self.application.experience_state(self.identity.owner_id)
        )
        approval = next(item for item in state["approvals"] if item["approval_id"] == approval_id)
        assert approval["run_id"] == run.id
        assert "must-not-leak" not in json.dumps(approval)

    def test_run_activity_is_run_scoped_and_excludes_raw_tool_arguments(self) -> None:
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device_id)
        conversation = self.runtime.repository.create_conversation(self.identity.owner_id, self.device_id, None)
        message = self.runtime.repository.create_message(conversation.id, session.id, None, self.device_id, "user", "activity")
        run = self.runtime.repository.create_run(conversation.id, session.id, self.device_id, message.id, "corr-closure-activity")
        other = self.runtime.repository.create_run(conversation.id, session.id, self.device_id, message.id, "corr-closure-other")
        self.runtime.repository.insert_tool_call("tool-call-closure-activity", run.id, "computer.action", {"secret": "private"}, "digest", "started")
        self.runtime.repository.insert_tool_call("tool-call-closure-other", other.id, "browser.read", {"secret": "other-private"}, "digest", "completed")

        activity = self.application.run_activity(run.id, self.identity.owner_id)
        assert [item["tool_call_id"] for item in activity["tools"]] == ["tool-call-closure-activity"]
        assert "private" not in json.dumps(activity)
        assert "other-private" not in json.dumps(activity)
        assert self.application.run_activity(run.id, "owner-not-bound") is None

    def test_queued_message_start_is_idempotent_for_the_same_client_message(self) -> None:
        first = self.loop.run_until_complete(
            self.runtime.agent.prepare_text(
                "queue this once",
                self.identity,
                self.device,
                client_message_id="closure-queued-idempotency",
            )
        )
        second = self.loop.run_until_complete(
            self.runtime.agent.prepare_text(
                "queue this once",
                self.identity,
                self.device,
                client_message_id="closure-queued-idempotency",
            )
        )
        assert first.run_id == second.run_id
        assert second.replayed is True
        assert second.state.value == "queued"
        assert len(self.runtime.repository.messages(first.conversation_id)) == 1

    def test_client_message_id_cannot_replay_another_owners_run(self) -> None:
        other_owner_id = self.runtime.repository.create_owner("Other Closure Owner")
        other_identity_id = self.runtime.repository.create_identity(
            other_owner_id, "Other Closure Identity", "human", ("owner",)
        )
        other_device_id = self.runtime.repository.create_device(
            other_owner_id,
            "Other Closure Browser",
            "desktop",
            "windows",
            ("computer.observe",),
            ("tool.request",),
        )
        other_identity = self.loop.run_until_complete(
            self.runtime.identity.get_identity(other_identity_id)
        )
        other_device = self.loop.run_until_complete(
            self.runtime.identity.device(other_device_id)
        )
        assert other_identity is not None
        assert other_device is not None
        session = self.runtime.repository.create_session(other_identity.owner_id, other_device.device_id)
        conversation = self.runtime.repository.create_conversation(other_identity.owner_id, other_device.device_id, None)
        message = self.runtime.repository.create_message(
            conversation.id,
            session.id,
            None,
            other_device.device_id,
            "user",
            "other owner message",
            "closure-cross-owner-idempotency",
        )
        run = self.runtime.repository.create_run(
            conversation.id,
            session.id,
            other_device.device_id,
            message.id,
            "closure-cross-owner-correlation",
        )
        self.runtime.repository.update_message_run_id(message.id, run.id)

        with pytest.raises(ValueError, match="client message owner binding mismatch"):
            self.loop.run_until_complete(
                self.runtime.agent.prepare_text(
                    "must not replay",
                    self.identity,
                    self.device,
                    client_message_id="closure-cross-owner-idempotency",
                )
            )

    def test_approval_denial_resumes_the_correlated_run_at_most_once(self) -> None:
        responses = [
            LLMResponse(
                "request-closure-approval-1",
                "",
                "qwen3.5:4b",
                "tool_calls",
                ({"function": {"name": "echo.consequential", "arguments": {"message": "closure"}}},),
                provider="mock",
            ),
        ]

        async def generate(request: Any, *_args: object, **_kwargs: object) -> LLMResponse:
            response = responses.pop(0)
            return LLMResponse(
                request.request_id,
                response.text,
                request.model,
                response.finish_reason,
                response.tool_calls,
                response.usage,
                "mock",
            )

        async def decide() -> object:
            try:
                return await self.application.resume_approval(
                    approval_id,
                    paused.run_id,
                    self.identity,
                    self.device,
                    approved=False,
                    decided_by=self.identity.identity_id,
                )
            except ValueError as exc:
                return exc

        with patch.object(self.runtime.models, "generate", side_effect=generate):
            paused = self.loop.run_until_complete(
                self.runtime.agent.process_text("please echo", self.identity, self.device)
            )
            assert paused.state.value == "paused"
            approval_id = paused.pending_approval_id
            assert approval_id is not None
            first = self.runtime.repository.tool_call_by_approval(approval_id)
            assert first is not None

            async def resume_both() -> list[object]:
                return list(await asyncio.gather(decide(), decide()))

            results = self.loop.run_until_complete(resume_both())

        successful = [item for item in results if isinstance(item, dict)]
        rejected = [item for item in results if isinstance(item, ValueError)]
        assert len(successful) == 1
        assert len(rejected) == 1
        assert self.runtime.repository.run(paused.run_id).status == "failed"
        assert self.runtime.repository.tool_call(first["id"])["status"] == "denied"

    def test_async_message_start_returns_run_before_blocking_model_and_cancel_uses_same_agent_runtime(self) -> None:
        cookie, csrf = self.bootstrap_session()
        entered = threading.Event()
        release = threading.Event()

        async def blocked_generate(*_args: object, **_kwargs: object) -> object:
            entered.set()
            await asyncio.to_thread(release.wait, 5)
            raise asyncio.CancelledError

        with patch.object(self.runtime.models, "generate", side_effect=blocked_generate):
            started_at = time.monotonic()
            response, started = request_json(
                self.base,
                "/v1/messages/start",
                method="POST",
                payload={"text": "block until cancelled", "client_message_id": "closure-async-1"},
                headers={
                    "Cookie": cookie,
                    "X-JARVIS-CSRF": csrf,
                    "Content-Type": "application/json",
                },
            )
            elapsed = time.monotonic() - started_at
            assert response.status == 202
            assert elapsed < 1.0
            assert started["run_id"]
            assert started["state"] == "queued"
            assert entered.wait(2)

            cancel_response, cancelled = request_json(
                self.base,
                f"/v1/runs/{started['run_id']}/cancel",
                method="POST",
                payload={},
                headers={
                    "Cookie": cookie,
                    "X-JARVIS-CSRF": csrf,
                    "Content-Type": "application/json",
                },
            )
            assert cancel_response.status == 200
            assert cancelled["run_id"] == started["run_id"]
            release.set()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                current = self.runtime.repository.run(started["run_id"])
                if current is not None and current.status == "cancelled":
                    break
                time.sleep(0.02)
            assert self.runtime.repository.run(started["run_id"]).status == "cancelled"


async def create_runtime_async():
    runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
    await runtime.start()
    return runtime
