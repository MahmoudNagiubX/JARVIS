"""Authenticated, bounded LAN node transport adapter for distributed satellites and nodes."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..network.validation import is_private_ip
from .core import CoreApplication

logger = logging.getLogger(__name__)


class CoreNodeHttpServer:
    """Separate, minimal authenticated HTTP server for physical nodes and satellites.

    Exposes ONLY bounded node routes:
    - Enrollment redemption
    - Satellite connect / heartbeat / poll / result / disconnect
    - Venom health / heartbeat
    - Room voice endpoint registration, utterance, and barge-in

    Strictly BLOCKS UI assets, memory, browser, communications, approvals admin,
    and all general user application routes.
    """

    def __init__(
        self,
        application: CoreApplication,
        host: str = "127.0.0.1",
        port: int = 8788,
        *,
        allow_wildcard_bind: bool = False,
        max_request_bytes: int = 1_000_000,
    ) -> None:
        self.application = application
        self.host = host
        self.port = port
        self.allow_wildcard_bind = allow_wildcard_bind
        self.max_request_bytes = max_request_bytes
        self._validate_bind_host(host, allow_wildcard_bind)
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None
        self._ready = Event()

    @staticmethod
    def _validate_bind_host(host: str, allow_wildcard: bool) -> None:
        if host in {"0.0.0.0", "::", ""}:
            if not allow_wildcard:
                raise ValueError("wildcard_bind_requires_explicit_opt_in")
            return
        if host in {"127.0.0.1", "::1", "localhost"}:
            return
        if is_private_ip(host):
            return
        raise ValueError(f"public_or_invalid_bind_host:{host}")

    def start(self) -> None:
        if self._server is not None:
            return

        app = self.application
        max_bytes = self.max_request_bytes

        class _NodeHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                # Suppress noisy logging in tests
                pass

            def _respond(self, status: HTTPStatus, payload: Mapping[str, object] | None = None) -> None:
                body = json.dumps(payload or {}, default=str).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def _body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", 0))
                if length > max_bytes:
                    raise ValueError("request_body_too_large")
                raw = self.rfile.read(length) if length > 0 else b"{}"
                if not raw:
                    return {}
                try:
                    data = json.loads(raw.decode("utf-8"))
                    return data if isinstance(data, dict) else {}
                except Exception as exc:
                    raise ValueError("invalid_json_body") from exc

            def _authenticated(self, values: dict[str, Any]) -> Any:
                values = dict(values)
                authorization = self.headers.get("Authorization", "")
                if "credential" not in values and authorization.casefold().startswith("bearer "):
                    values["credential"] = authorization[7:].strip()
                values.setdefault("device_id", self.headers.get("X-JARVIS-Device-ID") or self.headers.get("X-Device-ID"))
                values.setdefault("identity_id", self.headers.get("X-JARVIS-Identity-ID") or self.headers.get("X-Identity-ID"))
                required = ("credential", "device_id", "identity_id")
                if any(not values.get(key) for key in required):
                    raise PermissionError("credential_device_and_identity_required")
                principal = asyncio.run(app.authenticate_principal(
                    str(values["credential"]), str(values["device_id"]), str(values["identity_id"])
                ))
                if principal is None:
                    raise PermissionError("principal_not_found")
                return principal

            @staticmethod
            def _normalize_route(path: str) -> str:
                route = path.removeprefix("/v1")
                return route.rstrip("/") or "/"

            def _check_client_ip(self) -> bool:
                client_ip = self.client_address[0]
                if not is_private_ip(client_ip):
                    self._respond(HTTPStatus.FORBIDDEN, {"error": "non_private_client_rejected"})
                    return False
                return True

            def do_GET(self) -> None:  # noqa: N802
                if not self._check_client_ip():
                    return
                parsed = urlparse(self.path)
                route = self._normalize_route(parsed.path)

                try:
                    if route in {"/satellites/commands", "/nodes/satellite/commands"}:
                        raw_query = parse_qs(parsed.query)
                        query_values = {k: v[-1] if isinstance(v, list) and v else v for k, v in raw_query.items()}
                        principal = self._authenticated(query_values)
                        session_id = str(query_values.get("session_id", "")).strip()
                        raw_wait = query_values.get("wait_seconds")
                        try:
                            wait_seconds = float(raw_wait) if raw_wait is not None else 0.0
                        except (ValueError, TypeError):
                            wait_seconds = 0.0
                        wait_seconds = max(0.0, min(wait_seconds, 25.0))
                        res = asyncio.run(app.satellite_poll(principal, session_id, wait_seconds))
                        self._respond(HTTPStatus.OK, res)
                    elif route in {"/venom/health", "/nodes/venom/health"}:
                        self._respond(HTTPStatus.OK, app.venom_detailed_health())
                    elif route in {"/health", "/nodes/health"}:
                        self._respond(HTTPStatus.OK, asyncio.run(app.health()))
                    else:
                        self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                except PermissionError:
                    self._respond(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                except KeyError:
                    self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                except (ValueError, TypeError) as exc:
                    self._respond(HTTPStatus.BAD_REQUEST, {"error": str(exc) or exc.__class__.__name__})
                except Exception as exc:
                    self._respond(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": exc.__class__.__name__, "message": str(exc)})

            def do_POST(self) -> None:  # noqa: N802
                if not self._check_client_ip():
                    return
                parsed = urlparse(self.path)
                route = self._normalize_route(parsed.path)

                try:
                    body = self._body()
                    if route in {"/devices/enroll", "/nodes/enrollment/redeem"}:
                        result = asyncio.run(app.enroll_device(body))
                        status = HTTPStatus.OK if result.get("accepted") else HTTPStatus.BAD_REQUEST
                        self._respond(status, result)
                    elif route in {"/satellites/connect", "/nodes/satellite/connect"}:
                        principal = self._authenticated(body)
                        result = asyncio.run(app.satellite_connect(principal, body))
                        self._respond(HTTPStatus.OK, result)
                    elif route in {"/satellites/heartbeat", "/nodes/satellite/heartbeat"}:
                        principal = self._authenticated(body)
                        result = asyncio.run(app.satellite_heartbeat(principal, body))
                        self._respond(HTTPStatus.OK, result)
                    elif route in {"/satellites/results", "/nodes/satellite/results"}:
                        principal = self._authenticated(body)
                        result = asyncio.run(app.satellite_result(principal, body))
                        self._respond(HTTPStatus.OK, result)
                    elif route in {"/satellites/disconnect", "/nodes/satellite/disconnect"}:
                        principal = self._authenticated(body)
                        result = asyncio.run(app.satellite_disconnect(principal, str(body.get("session_id", ""))))
                        self._respond(HTTPStatus.OK, result)
                    elif route in {"/nodes/venom/heartbeat", "/venom/heartbeat"}:
                        principal = self._authenticated(body)
                        result = asyncio.run(app.venom_heartbeat(principal, body))
                        self._respond(HTTPStatus.OK, result)
                    elif route in {"/rooms/endpoints", "/nodes/rooms/register_endpoint"}:
                        principal = self._authenticated(body)
                        result = asyncio.run(app.register_room_voice_endpoint(principal, body))
                        self._respond(HTTPStatus.OK, result)
                    elif route in {"/voice/room/utterance", "/nodes/voice/utterance"}:
                        principal = self._authenticated(body)
                        result = asyncio.run(app.handle_room_voice_utterance(
                            body,
                            identity=principal.identity,
                            device=principal.device,
                        ))
                        self._respond(HTTPStatus.OK, result)
                    elif route in {"/voice/room/barge_in", "/nodes/voice/barge_in"}:
                        principal = self._authenticated(body)
                        result = asyncio.run(app.room_voice_barge_in(
                            body,
                            principal=principal,
                        ))
                        self._respond(HTTPStatus.OK, result)
                    else:
                        self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                except PermissionError:
                    self._respond(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                except KeyError:
                    self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                except (ValueError, TypeError) as exc:
                    self._respond(HTTPStatus.BAD_REQUEST, {"error": str(exc) or exc.__class__.__name__})
                except Exception as exc:
                    self._respond(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": exc.__class__.__name__, "message": str(exc)})

        self._server = ThreadingHTTPServer((self.host, self.port), _NodeHandler)
        self.port = self._server.server_port
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._ready.set()

    def wait_ready(self, timeout: float = 5.0) -> bool:
        return self._ready.wait(timeout)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._ready.clear()
