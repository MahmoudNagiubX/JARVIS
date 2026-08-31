from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
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
from jarvis.desktop.lifecycle import JarvisDesktopLifecycle


REPO_ROOT = Path(__file__).resolve().parents[1]


def _raw_request(base: str, path: str, *, method: str = "GET", payload: dict[str, object] | None = None, headers: dict[str, str] | None = None) -> tuple[Any, bytes]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(f"{base}{path}", method=method, data=body, headers=headers or {})
    with urlopen(request) as response:
        return response, response.read()


def _request(base: str, path: str, *, method: str = "GET", payload: dict[str, object] | None = None, headers: dict[str, str] | None = None) -> tuple[Any, dict[str, Any]]:
    response, body = _raw_request(base, path, method=method, payload=payload, headers=headers)
    return response, json.loads(body.decode("utf-8"))


def _expect_http_error(base: str, path: str, *, method: str, payload: dict[str, object] | None = None, headers: dict[str, str]) -> HTTPError:
    with pytest.raises(HTTPError) as raised:
        _request(base, path, method=method, payload=payload, headers=headers)
    return raised.value


class TestPhaseFourteenProductExperience:
    def setup_method(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.runtime = self.loop.run_until_complete(create_runtime_async())
        self.server = CoreHttpServer(CoreApplication(self.runtime), port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://{self.server.address[0]}:{self.server.address[1]}"

        self.identity = self.loop.run_until_complete(self.runtime.identity.bootstrap_owner("Phase Fourteen Owner"))
        enrollment = self.loop.run_until_complete(self.runtime.identity.create_enrollment(EnrollmentGrant(
            self.identity.owner_id,
            "Phase Fourteen Browser",
            "desktop",
            "windows",
            ("tool.request",),
            ("computer.observe", "perception.screen"),
        )))
        issued = self.loop.run_until_complete(self.runtime.identity.redeem_enrollment(enrollment.code))
        self.credential = issued.raw
        self.device_id = issued.device_id
        self.headers = {
            "Authorization": f"Bearer {self.credential}",
            "X-JARVIS-Device-ID": self.device_id,
            "X-JARVIS-Identity-ID": self.identity.identity_id,
        }

    def teardown_method(self) -> None:
        self.server.shutdown()
        self.loop.run_until_complete(self.runtime.shutdown())
        self.loop.close()

    def _bootstrap_session(self) -> tuple[str, str]:
        token = self.server.issue_desktop_bootstrap(
            self.credential,
            self.device_id,
            self.identity.identity_id,
        )
        response, session = _request(
            self.base,
            "/v1/auth/desktop-session",
            method="POST",
            payload={"bootstrap": token},
        )
        cookie = response.headers.get("Set-Cookie", "").split(";", 1)[0]
        assert cookie.startswith("jarvis_session=")
        assert "httponly" in response.headers.get("Set-Cookie", "").casefold()
        assert "credential" not in json.dumps(session).casefold()
        return cookie, str(session["csrf_token"])

    def test_command_center_is_a_local_static_shell_and_legacy_hud_stays_available(self) -> None:
        response, shell = _raw_request(self.base, "/v1/app")
        html = shell.decode("utf-8")
        assert response.headers.get_content_type() == "text/html"
        assert "JARVIS Command Center" in html
        assert "styles.css" in html and "app.js" in html
        assert "http://" not in html and "https://" not in html
        assert response.headers["Content-Security-Policy"]

        legacy, _legacy_html = _raw_request(self.base, "/v1/hud")
        assert legacy.headers.get_content_type() == "text/html"

        asset_response, app_js = _raw_request(self.base, "/v1/app/app.js")
        assert asset_response.headers["X-Content-Type-Options"] == "nosniff"
        app_source = app_js.decode("utf-8")
        assert "localStorage" not in app_source
        assert "http://" not in app_source and "https://" not in app_source

    def test_desktop_bootstrap_is_one_use_and_never_becomes_a_browser_credential(self) -> None:
        token = self.server.issue_desktop_bootstrap(self.credential, self.device_id, self.identity.identity_id)
        response, session = _request(
            self.base,
            "/v1/auth/desktop-session",
            method="POST",
            payload={"bootstrap": token},
        )
        assert response.status == 201
        assert "credential" not in response.headers.get("Set-Cookie", "").casefold()
        assert "credential" not in json.dumps(session).casefold()

        failed = _expect_http_error(
            self.base,
            "/v1/auth/desktop-session",
            method="POST",
            payload={"bootstrap": token},
            headers={"Content-Type": "application/json"},
        )
        assert failed.code == 401

    def test_desktop_bootstrap_creates_short_lived_http_only_session_and_reads_owner_state(self) -> None:
        cookie, _csrf = self._bootstrap_session()
        response, session = _request(self.base, "/v1/auth/session", headers={"Cookie": cookie})
        assert response.status == 200
        assert session["owner_id"] == self.identity.owner_id
        assert session["identity_id"] == self.identity.identity_id
        assert session["csrf_token"]

        state_response, state = _request(
            self.base,
            f"/v1/experience/state?owner_id={self.identity.owner_id}",
            headers={"Cookie": cookie},
        )
        assert state_response.status == 200
        assert state["owner_id"] == self.identity.owner_id
        assert "credential" not in json.dumps(state).casefold()

    def test_cookie_mutations_require_csrf_and_still_use_the_existing_agent_runtime(self) -> None:
        cookie, csrf = self._bootstrap_session()
        message = {"text": "Give me a local status summary.", "client_message_id": "phase14-message-1"}
        failed = _expect_http_error(
            self.base,
            "/v1/messages",
            method="POST",
            payload=message,
            headers={"Cookie": cookie, "Content-Type": "application/json"},
        )
        assert failed.code == 401

        response, result = _request(
            self.base,
            "/v1/messages",
            method="POST",
            payload=message,
            headers={
                "Cookie": cookie,
                "X-JARVIS-CSRF": csrf,
                "Content-Type": "application/json",
            },
        )
        assert response.status == 200
        assert result["conversation_id"]
        assert result["run_id"]
        assert result["response"]

        conversation_response, conversations = _request(
            self.base,
            f"/v1/conversations?owner_id={self.identity.owner_id}",
            headers={"Cookie": cookie},
        )
        assert conversation_response.status == 200
        assert any(item["id"] == result["conversation_id"] for item in conversations["conversations"])

        messages_response, messages = _request(
            self.base,
            f"/v1/conversations/{result['conversation_id']}/messages?owner_id={self.identity.owner_id}",
            headers={"Cookie": cookie},
        )
        assert messages_response.status == 200
        assert [item["role"] for item in messages["messages"]] == ["user", "assistant"]

        patch_failed = _expect_http_error(
            self.base,
            "/v1/memory/not-a-real-memory",
            method="PATCH",
            payload={"content": "must not mutate"},
            headers={"Cookie": cookie, "Content-Type": "application/json"},
        )
        assert patch_failed.code == 401

        origin_failed = _expect_http_error(
            self.base,
            "/v1/messages",
            method="POST",
            payload={"text": "cross-site attempt"},
            headers={
                "Cookie": cookie,
                "X-JARVIS-CSRF": csrf,
                "Origin": "http://evil.example",
                "Content-Type": "application/json",
            },
        )
        assert origin_failed.code == 401

    def test_cookie_owner_scope_rejects_wrong_owner_filters_and_conversations(self) -> None:
        cookie, _csrf = self._bootstrap_session()
        wrong_owner = "owner-not-bound-to-this-session"

        failed = _expect_http_error(
            self.base,
            f"/v1/conversations?owner_id={wrong_owner}",
            headers={"Cookie": cookie},
            method="GET",
        )
        assert failed.code == 401

        failed = _expect_http_error(
            self.base,
            f"/v1/conversations/{'conversation-not-owned'}/messages?owner_id={self.identity.owner_id}",
            headers={"Cookie": cookie},
            method="GET",
        )
        assert failed.code == 404

    def test_daily_open_hud_targets_the_command_center_route(self) -> None:
        opened: list[str] = []

        class FakeHudServer:
            address = ("127.0.0.1", 8787)

        lifecycle = JarvisDesktopLifecycle()
        lifecycle._hud_server = FakeHudServer()  # type: ignore[assignment]
        lifecycle._app_bootstrap_url = None  # type: ignore[attr-defined]
        with patch("jarvis.desktop.lifecycle.webbrowser.open", side_effect=lambda url: opened.append(url) or True):
            assert lifecycle.open_hud()
        assert opened == ["http://127.0.0.1:8787/app"]

    def test_daily_open_consumes_the_bootstrap_url_and_reuses_the_session_route(self) -> None:
        opened: list[str] = []

        class FakeHudServer:
            address = ("127.0.0.1", 8787)

        lifecycle = JarvisDesktopLifecycle()
        lifecycle._hud_server = FakeHudServer()  # type: ignore[assignment]
        lifecycle._app_bootstrap_url = "http://127.0.0.1:8787/app#bootstrap=one-use"  # type: ignore[attr-defined]
        with patch("jarvis.desktop.lifecycle.webbrowser.open", side_effect=lambda url: opened.append(url) or True):
            assert lifecycle.open_hud()
            assert lifecycle.open_hud()
        assert opened == [
            "http://127.0.0.1:8787/app#bootstrap=one-use",
            "http://127.0.0.1:8787/app",
        ]

    def test_frontend_build_is_deterministic_and_contains_only_local_assets(self) -> None:
        result = subprocess.run(
            [sys.executable, "ui/build_frontend.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        output = REPO_ROOT / "src" / "jarvis" / "ui_static"
        assert (output / "index.html").is_file()
        assert (output / "styles.css").is_file()
        assert (output / "app.js").is_file()
        for path in output.iterdir():
            text = path.read_text(encoding="utf-8")
            assert "http://" not in text and "https://" not in text
        first = {path.name: path.read_bytes() for path in output.iterdir()}
        second = subprocess.run(
            [sys.executable, "ui/build_frontend.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert second.returncode == 0, second.stderr
        assert first == {path.name: path.read_bytes() for path in output.iterdir()}
async def create_runtime_async():
    runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
    await runtime.start()
    return runtime
