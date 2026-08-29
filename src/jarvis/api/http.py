"""Dependency-free loopback HTTP transport for the core application."""

from __future__ import annotations

import asyncio
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from typing import Any

from .core import CoreApplication


class CoreHttpServer:
    """Small local API adapter; it never binds outside the loopback interface."""

    def __init__(self, application: CoreApplication, host: str = "127.0.0.1", port: int = 8787) -> None:
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("JARVIS HTTP server must remain loopback-only")
        self.application = application
        self.server = ThreadingHTTPServer((host, port), self._handler())

    @property
    def address(self) -> tuple[str, int]:
        return self.server.server_address[:2]

    def serve_forever(self) -> None:
        self.server.serve_forever()

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        application = self.application

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                parsed = urlparse(self.path)
                try:
                    if parsed.path == "/health":
                        self._respond(HTTPStatus.OK, asyncio.run(application.health()))
                    elif parsed.path == "/v1/events":
                        query = parse_qs(parsed.query)
                        correlation_id = query.get("correlation_id", [None])[0]
                        self._respond(HTTPStatus.OK, {"events": application.events(correlation_id)})
                    elif parsed.path == "/v1/events/stream":
                        query = parse_qs(parsed.query)
                        correlation_id = query.get("correlation_id", [None])[0]
                        self._stream(application.events(correlation_id))
                    elif parsed.path.startswith("/v1/approvals/"):
                        approval_id = parsed.path.rsplit("/", 1)[-1]
                        result = asyncio.run(application.approval(approval_id))
                        self._respond(HTTPStatus.OK if result else HTTPStatus.NOT_FOUND, result or {"error": "not_found"})
                    else:
                        self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                except Exception as exc:
                    self._respond(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": exc.__class__.__name__})

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
                parsed = urlparse(self.path)
                try:
                    body = self._body()
                    if parsed.path == "/v1/messages":
                        principal = asyncio.run(application.authenticate_principal(
                            str(body["credential"]), str(body["device_id"]), str(body["identity_id"])
                        ))
                        if principal is None:
                            self._respond(HTTPStatus.UNAUTHORIZED, {"error": "principal_not_found"})
                            return
                        result = asyncio.run(application.send_message(
                            str(body["text"]), principal.identity, principal.device,
                            session_id=body.get("session_id"),
                            conversation_id=body.get("conversation_id"),
                            client_message_id=body.get("client_message_id"),
                        ))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if parsed.path.startswith("/v1/approvals/"):
                        approval_id = parsed.path.rsplit("/", 1)[-1]
                        principal = asyncio.run(application.authenticate_principal(
                            str(body["credential"]), str(body["device_id"]), str(body["identity_id"])
                        ))
                        if principal is None:
                            self._respond(HTTPStatus.UNAUTHORIZED, {"error": "principal_not_found"})
                            return
                        result = asyncio.run(application.resume_approval(
                            approval_id, str(body["run_id"]), principal.identity, principal.device,
                            bool(body["approved"]), str(body.get("decided_by", principal.identity.identity_id)),
                        ))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if parsed.path.startswith("/v1/runs/") and parsed.path.endswith("/cancel"):
                        run_id = parsed.path.split("/")[-2]
                        principal = asyncio.run(application.authenticate_principal(
                            str(body["credential"]), str(body["device_id"]), str(body["identity_id"])
                        ))
                        if principal is None:
                            self._respond(HTTPStatus.UNAUTHORIZED, {"error": "principal_not_found"})
                            return
                        result = asyncio.run(application.cancel(run_id, principal.identity, principal.device))
                        self._respond(HTTPStatus.OK if result else HTTPStatus.NOT_FOUND, result or {"error": "not_found"})
                        return
                    self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                except (KeyError, TypeError, ValueError) as exc:
                    self._respond(HTTPStatus.BAD_REQUEST, {"error": str(exc) or exc.__class__.__name__})
                except Exception as exc:
                    self._respond(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": exc.__class__.__name__})

            def _body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 1_000_000:
                    raise ValueError("request body must be a non-empty JSON object")
                decoded = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(decoded, dict):
                    raise ValueError("request body must be a JSON object")
                return decoded

            def _respond(self, status: HTTPStatus, payload: Any) -> None:
                encoded = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _stream(self, events: list[dict[str, Any]]) -> None:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                for event in events:
                    encoded = json.dumps(event, default=str, ensure_ascii=False).encode("utf-8")
                    self.wfile.write(b"data: " + encoded + b"\n\n")
                self.wfile.flush()

            def log_message(self, format: str, *args: object) -> None:
                del format, args

        return Handler
