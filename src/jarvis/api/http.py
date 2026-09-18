"""Dependency-free loopback HTTP transport for the core application."""

from __future__ import annotations

import asyncio
import json
import queue
import time
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import Any

from .core import CoreApplication
from .auth import DesktopSessionService, StreamTicketService
from ..experience.projections import ExperienceProjection
from ..experience.websocket import accept_key, close_frame, ping_frame, text_frame


def _execute_background_message(application: CoreApplication, run_id: str, identity: Any, device: Any) -> None:
    """Finish a queued message through the existing AgentRuntime authority."""

    try:
        asyncio.run(application.execute_message(run_id, identity, device))
    except Exception:
        # AgentRuntime persists terminal failures; the HTTP request has already
        # returned the durable run id and clients observe the resulting state.
        return


class CoreHttpServer:
    """Small local API adapter; it never binds outside the loopback interface."""

    PUBLIC_GET_ROUTES = frozenset({"/health", "/hud", "/experience/hud"})
    _STREAM_GET_ROUTES = frozenset({"/experience/events", "/experience/events/ws", "/events/stream"})
    _APP_STATIC_ROOT = Path(__file__).resolve().parents[1] / "ui_static"

    def __init__(self, application: CoreApplication, host: str = "127.0.0.1", port: int = 8787) -> None:
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("JARVIS HTTP server must remain loopback-only")
        self.application = application
        self.stream_tickets = StreamTicketService()
        self.desktop_sessions = DesktopSessionService()
        self._message_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="jarvis-message")
        self.server = ThreadingHTTPServer((host, port), self._handler())

    @property
    def address(self) -> tuple[str, int]:
        return self.server.server_address[:2]

    def serve_forever(self) -> None:
        self.server.serve_forever()

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._message_executor.shutdown(wait=False, cancel_futures=True)

    def issue_desktop_bootstrap(self, credential: str, device_id: str, identity_id: str) -> str:
        """Issue a one-use browser handoff without exposing a device credential in a URL."""

        return self.desktop_sessions.issue_bootstrap(credential, device_id, identity_id)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        application = self.application
        ticket_service = self.stream_tickets
        desktop_sessions = self.desktop_sessions
        message_executor = self._message_executor
        public_get_routes = self.PUBLIC_GET_ROUTES
        stream_get_routes = self._STREAM_GET_ROUTES

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                parsed = urlparse(self.path)
                route = self._route(parsed.path)
                try:
                    query = parse_qs(parsed.query)
                    if "credential" in query:
                        raise PermissionError("query_credentials_not_allowed")
                    values = {key: items[0] for key, items in query.items() if items}
                    # Public shells expose no runtime state. Every other
                    # ordinary GET authenticates before route dispatch; stream
                    # routes authenticate through their ticket-aware boundary.
                    principal = None
                    if route not in public_get_routes and route not in stream_get_routes and not self._is_public_app_route(route):
                        principal = self._authenticated(values)
                    if route == "/health":
                        self._respond(HTTPStatus.OK, asyncio.run(application.health()))
                    elif route == "/computer/apps":
                        refresh = query.get("refresh", ["false"])[0].casefold() == "true"
                        self._respond(HTTPStatus.OK, asyncio.run(application.installed_applications(refresh=refresh)))
                    elif route == "/satellites/commands":
                        principal = self._authenticated(values)
                        self._respond(
                            HTTPStatus.OK,
                            asyncio.run(application.satellite_poll(
                                principal,
                                str(values.get("session_id", "")),
                                float(values.get("wait_seconds", 20)),
                            )),
                        )
                    elif route in {"/hud", "/experience/hud"}:
                        self.send_response(HTTPStatus.OK)
                        encoded = application.experience_hud().encode("utf-8")
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(encoded)))
                        self.end_headers()
                        self.wfile.write(encoded)
                    elif route == "/app" or route == "/app/index.html":
                        self._serve_app_asset("index.html")
                    elif route.startswith("/app/"):
                        self._serve_app_asset(route.removeprefix("/app/"))
                    elif route == "/experience/state":
                        self._respond(HTTPStatus.OK, asyncio.run(application.experience_state(self._authenticated(values).identity.owner_id)))
                    elif route == "/experience/system":
                        self._respond(HTTPStatus.OK, asyncio.run(application.experience_system(self._authenticated(values).identity.owner_id)))
                    elif route == "/experience/timeline":
                        limit = int(query.get("limit", [100])[0])
                        self._respond(HTTPStatus.OK, {"events": application.experience_timeline(self._authenticated(values).identity.owner_id, limit)})
                    elif route == "/experience/events":
                        principal = self._stream_principal(query, "experience.events")
                        self._stream([asyncio.run(application.experience_state(principal.identity.owner_id))])
                    elif route == "/experience/events/ws":
                        self._websocket(query)
                    elif route == "/experience/clients":
                        self._respond(HTTPStatus.OK, {"clients": application.list_clients(self._authenticated(values).identity.owner_id)})
                    elif route == "/presence":
                        self._respond(HTTPStatus.OK, asyncio.run(application.presence(principal.identity.owner_id)))
                    elif route == "/attention":
                        self._respond(HTTPStatus.OK, asyncio.run(application.attention(principal.identity.owner_id)))
                    elif route == "/personal-operations/modes":
                        self._respond(HTTPStatus.OK, {"modes": asyncio.run(application.personal_modes(principal.identity.owner_id))})
                    elif route == "/focus":
                        self._respond(HTTPStatus.OK, asyncio.run(application.focus_state(principal.identity.owner_id)))
                    elif route == "/communications/follow-ups":
                        self._respond(HTTPStatus.OK, {"follow_ups": asyncio.run(application.communication_followups(principal.identity.owner_id, query.get("active_only", ["false"])[0].casefold() == "true"))})
                    elif route == "/communications/auto-send-rules":
                        self._respond(HTTPStatus.OK, {"rules": asyncio.run(application.communication_auto_send_rules(principal.identity.owner_id))})
                    elif route == "/home/context":
                        principal = self._authenticated(values)
                        self._respond(HTTPStatus.OK, asyncio.run(application.home_context(principal.identity, principal.device)))
                    elif route == "/routines":
                        self._respond(HTTPStatus.OK, {"routines": application.routines()})
                    elif route == "/events":
                        correlation_id = query.get("correlation_id", [None])[0]
                        principal = self._authenticated({})
                        self._respond(HTTPStatus.OK, {"events": application.events(correlation_id, principal.identity.owner_id)})
                    elif route == "/events/stream":
                        correlation_id = query.get("correlation_id", [None])[0]
                        principal = self._stream_principal(query, "events")
                        self._stream(application.events(correlation_id, principal.identity.owner_id))
                    elif route.startswith("/approvals/"):
                        approval_id = route.rsplit("/", 1)[-1]
                        principal = self._authenticated({})
                        result = asyncio.run(application.approval(approval_id, principal.identity.owner_id))
                        self._respond(HTTPStatus.OK if result else HTTPStatus.NOT_FOUND, result or {"error": "not_found"})
                    elif route == "/memory":
                        self._respond(HTTPStatus.OK, {"memories": asyncio.run(application.list_memory(
                            self._owner(query), text=query.get("q", [""])[0], category=query.get("category", [None])[0],
                            source=query.get("source", [None])[0], tags=tuple(query.get("tag", [])),
                            include_archived=query.get("include_archived", ["false"])[0].casefold() == "true",
                            limit=int(query.get("limit", [50])[0]),
                        ))})
                    elif route.startswith("/memory/"):
                        memory_id = route.rsplit("/", 1)[-1]
                        result = asyncio.run(application.get_memory(self._owner(query), memory_id))
                        self._respond(HTTPStatus.OK if result else HTTPStatus.NOT_FOUND, result or {"error": "not_found"})
                    elif route == "/world-state":
                        self._respond(HTTPStatus.OK, asyncio.run(application.world_state(
                            self._owner(query), key_prefix=query.get("key_prefix", [None])[0],
                            include_expired=query.get("include_expired", ["false"])[0].casefold() == "true",
                        )))
                    elif route == "/world-state/conflicts":
                        self._respond(HTTPStatus.OK, {"conflicts": asyncio.run(application.world_conflicts(self._owner(query)))})
                    elif route == "/goals":
                        self._respond(HTTPStatus.OK, {"goals": asyncio.run(application.list_goals(self._owner(query), tuple(query.get("status", []))))})
                    elif route == "/proactive/findings":
                        self._respond(HTTPStatus.OK, {"findings": asyncio.run(application.proactive_findings(
                            self._owner(query), query.get("active_only", ["false"])[0].casefold() == "true"
                        ))})
                    elif route == "/personalization/profile":
                        self._respond(HTTPStatus.OK, asyncio.run(application.personalization_profile(self._owner(query))))
                    elif route == "/context":
                        principal = self._authenticated({key: values[0] for key, values in query.items() if values})
                        self._respond(HTTPStatus.OK, asyncio.run(application.context(
                            principal.identity, principal.device, query.get("q", [""])[0]
                        )))
                    elif route == "/devices":
                        self._respond(HTTPStatus.OK, {"devices": asyncio.run(application.list_devices(self._owner(query)))})
                    elif route.startswith("/devices/") and route.endswith("/capabilities"):
                        parts = route.strip("/").split("/")
                        result = asyncio.run(application.device_capabilities(self._owner(query), parts[1]))
                        self._respond(HTTPStatus.OK, result)
                    elif route.startswith("/devices/"):
                        device_id = route.rsplit("/", 1)[-1]
                        result = asyncio.run(application.get_device(self._owner(query), device_id))
                        self._respond(HTTPStatus.OK if result else HTTPStatus.NOT_FOUND, result or {"error": "not_found"})
                    elif route == "/home/entities":
                        principal = self._authenticated({key: values[0] for key, values in query.items() if values})
                        self._respond(HTTPStatus.OK, {"entities": asyncio.run(application.home_entities(principal.identity, principal.device))})
                    elif route == "/communications/channels":
                        self._respond(HTTPStatus.OK, {"channels": asyncio.run(application.communication_channels())})
                    elif route == "/communications/messages":
                        self._respond(HTTPStatus.OK, {"messages": asyncio.run(application.communication_messages(
                            self._owner(query), channel=query.get("channel", [None])[0], query=query.get("q", [None])[0]
                        ))})
                    elif route.startswith("/communications/intelligence/"):
                        thread_id = route.rsplit("/", 1)[-1]
                        result = asyncio.run(application.get_communication_intelligence(self._owner(query), thread_id))
                        self._respond(HTTPStatus.OK if result else HTTPStatus.NOT_FOUND, result or {"error": "not_found"})
                    elif route == "/notifications":
                        self._respond(HTTPStatus.OK, {"notifications": asyncio.run(application.list_notifications(
                            self._owner(query), query.get("active_only", ["false"])[0].casefold() == "true"
                        ))})
                    elif route == "/capabilities":
                        self._respond(HTTPStatus.OK, {"capabilities": application.capabilities(principal.device.device_id if principal else None)})
                    elif route == "/research/runs":
                        self._respond(HTTPStatus.OK, {"runs": application.research_list(self._authenticated(values).identity.owner_id)})
                    elif route.startswith("/research/runs/") and route.endswith("/evidence"):
                        parts = route.strip("/").split("/")
                        evidence = application.research_evidence(self._authenticated(values).identity.owner_id, parts[2])
                        self._respond(HTTPStatus.OK, {"evidence": evidence})
                    elif route.startswith("/research/runs/"):
                        run = application.research_get(self._authenticated(values).identity.owner_id, route.rsplit("/", 1)[-1])
                        self._respond(HTTPStatus.OK if run else HTTPStatus.NOT_FOUND, run or {"error": "not_found"})
                    elif route == "/engineering/providers":
                        self._respond(HTTPStatus.OK, {"providers": application.engineering_providers()})
                    elif route.startswith("/engineering/sessions/"):
                        result = application.engineering_get_session(self._authenticated(values).identity.owner_id, route.rsplit("/", 1)[-1])
                        self._respond(HTTPStatus.OK if result else HTTPStatus.NOT_FOUND, result or {"error": "not_found"})
                    elif route == "/perception/capabilities":
                        self._respond(HTTPStatus.OK, application.perception_capabilities())
                    elif route == "/perception/context":
                        self._respond(HTTPStatus.OK, asyncio.run(application.perception_context(principal.identity, principal.device, values)))
                    elif route.startswith("/perception/observations/"):
                        observation_id = route.rsplit("/", 1)[-1]
                        latest_values = {"observation_id": observation_id}
                        if "target_device_id" in values:
                            latest_values["target_device_id"] = values["target_device_id"]
                        if "session_id" in values:
                            latest_values["session_id"] = values["session_id"]
                        self._respond(HTTPStatus.OK, asyncio.run(application.perception_latest(principal.identity, principal.device, latest_values)))
                    elif route == "/workers/developer/providers":
                        self._respond(HTTPStatus.OK, {"providers": application.developer_providers()})
                    elif route == "/missions":
                        self._respond(HTTPStatus.OK, {"missions": asyncio.run(application.list_missions(self._owner(query)))})
                    elif route.startswith("/missions/"):
                        parts = route.strip("/").split("/")
                        if len(parts) == 3 and parts[2] == "evidence":
                            self._respond(HTTPStatus.OK, {"evidence": asyncio.run(application.mission_evidence(self._owner(query), parts[1]))})
                        else:
                            result = asyncio.run(application.get_mission(self._owner(query), parts[1]))
                            self._respond(HTTPStatus.OK if result else HTTPStatus.NOT_FOUND, result or {"error": "not_found"})
                    elif route == "/skills":
                        self._respond(HTTPStatus.OK, {"skills": application.list_skills(include_disabled=True)})
                    elif route.startswith("/skills/") and route.endswith("/versions"):
                        self._respond(HTTPStatus.OK, {"versions": application.skill_versions(route.strip("/").split("/")[1])})
                    elif route.startswith("/skills/"):
                        result = application.get_skill(route.rsplit("/", 1)[-1], include_disabled=True)
                        self._respond(HTTPStatus.OK if result else HTTPStatus.NOT_FOUND, result or {"error": "not_found"})
                    elif route == "/workspace/projects":
                        self._respond(HTTPStatus.OK, {"projects": asyncio.run(application.workspace_projects(self._owner(query)))})
                    elif route.startswith("/workspace/projects/"):
                        parts = route.strip("/").split("/")
                        if len(parts) == 4 and parts[3] == "inspect":
                            self._respond(HTTPStatus.OK, asyncio.run(application.workspace_inspect(self._owner(query), parts[2])))
                        else:
                            self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                    elif route == "/intelligence/findings":
                        self._respond(HTTPStatus.OK, {"findings": asyncio.run(application.intelligence_findings(self._owner(query), query.get("active_only", ["false"])[0].casefold() == "true"))})
                    elif route == "/briefings":
                        self._respond(HTTPStatus.OK, {"briefings": asyncio.run(application.list_briefings(self._owner(query), query.get("type", [None])[0]))})
                    elif route == "/automations":
                        self._respond(HTTPStatus.OK, {"automations": asyncio.run(application.list_automations(self._owner(query)))})
                    elif route == "/evaluations":
                        self._respond(HTTPStatus.OK, {"evaluations": asyncio.run(application.list_evaluations(self._owner(query)))})
                    elif route == "/auth/session":
                        session = self._desktop_session()
                        if session is None:
                            raise PermissionError("desktop_session_required")
                        self._respond(HTTPStatus.OK, {
                            "owner_id": session.owner_id,
                            "identity_id": session.identity_id,
                            "device_id": session.device_id,
                            "csrf_token": session.csrf_token,
                            "expires_at": session.expires_at.isoformat(),
                        })
                    elif route.startswith("/runs/") and route.endswith("/activity"):
                        run_id = route.strip("/").split("/")[1]
                        principal = self._authenticated(values)
                        result = application.run_activity(run_id, principal.identity.owner_id)
                        self._respond(HTTPStatus.OK if result else HTTPStatus.NOT_FOUND, result or {"error": "not_found"})
                    elif route.startswith("/runs/"):
                        run_id = route.strip("/").split("/")[1]
                        principal = self._authenticated(values)
                        result = application.run_status(run_id, principal.identity.owner_id)
                        self._respond(HTTPStatus.OK if result else HTTPStatus.NOT_FOUND, result or {"error": "not_found"})
                    elif route == "/conversations":
                        self._respond(HTTPStatus.OK, {"conversations": asyncio.run(application.list_conversations(self._owner(query)))})
                    elif route.startswith("/conversations/") and route.endswith("/messages"):
                        parts = route.strip("/").split("/")
                        result = asyncio.run(application.conversation_messages(self._owner(query), parts[1]))
                        self._respond(HTTPStatus.OK if result is not None else HTTPStatus.NOT_FOUND, {"messages": result or []} if result is not None else {"error": "not_found"})
                    elif route == "/nodes/venom/health":
                        self._respond(HTTPStatus.OK, application.venom_detailed_health())
                    elif route == "/nodes/venom/plan":
                        self._respond(HTTPStatus.OK, application.venom_plan())
                    elif route == "/rooms":
                        self._respond(HTTPStatus.OK, {"rooms": asyncio.run(application.list_rooms(self._owner(query)))})
                    elif route.startswith("/rooms/"):
                        room_id = route.rsplit("/", 1)[-1]
                        result = asyncio.run(application.get_room(self._owner(query), room_id))
                        self._respond(HTTPStatus.OK if result else HTTPStatus.NOT_FOUND, result or {"error": "not_found"})
                    elif route == "/fabric/diagnostics":
                        self._respond(HTTPStatus.OK, asyncio.run(application.fabric_diagnostics(self._owner(query))))
                    else:
                        self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                except PermissionError:
                    self._respond(HTTPStatus.UNAUTHORIZED, {"error": "principal_not_found"})
                except (KeyError, TypeError, ValueError) as exc:
                    self._respond(HTTPStatus.BAD_REQUEST, {"error": str(exc) or exc.__class__.__name__})
                except Exception as exc:
                    self._respond(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": exc.__class__.__name__})

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
                parsed = urlparse(self.path)
                route = self._route(parsed.path)
                try:
                    body = self._body()
                    if route == "/auth/desktop-session":
                        bootstrap = desktop_sessions.consume_bootstrap(str(body.get("bootstrap", "")))
                        if bootstrap is None:
                            raise PermissionError("invalid_desktop_bootstrap")
                        principal = asyncio.run(application.authenticate_principal(
                            bootstrap.credential, bootstrap.device_id, bootstrap.identity_id,
                        ))
                        if principal is None:
                            raise PermissionError("desktop_bootstrap_principal_not_found")
                        session = desktop_sessions.create_session(principal)
                        self._respond(
                            HTTPStatus.CREATED,
                            {
                                "owner_id": session.owner_id,
                                "identity_id": session.identity_id,
                                "device_id": session.device_id,
                                "csrf_token": session.csrf_token,
                                "expires_at": session.expires_at.isoformat(),
                            },
                            {"Set-Cookie": self._session_cookie(session.token, session.expires_at)},
                        )
                        return
                    if route == "/auth/session/refresh":
                        current = self._desktop_session()
                        if current is None:
                            raise PermissionError("desktop_session_required")
                        principal = self._authenticated({}, require_session=True)
                        refreshed = desktop_sessions.refresh_session(current.token, principal)
                        if refreshed is None:
                            raise PermissionError("desktop_session_refresh_failed")
                        self._respond(
                            HTTPStatus.OK,
                            {
                                "owner_id": refreshed.owner_id,
                                "identity_id": refreshed.identity_id,
                                "device_id": refreshed.device_id,
                                "csrf_token": refreshed.csrf_token,
                                "expires_at": refreshed.expires_at.isoformat(),
                            },
                            {"Set-Cookie": self._session_cookie(refreshed.token, refreshed.expires_at)},
                        )
                        return
                    if route == "/satellites/connect":
                        principal = self._authenticated(body)
                        self._respond(HTTPStatus.CREATED, asyncio.run(application.satellite_connect(principal, body)))
                        return
                    if route == "/satellites/heartbeat":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.satellite_heartbeat(principal, body))
                        self._respond(HTTPStatus.OK if result.get("accepted") else HTTPStatus.UNAUTHORIZED, result)
                        return
                    if route == "/satellites/results":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.satellite_result(principal, body))
                        self._respond(HTTPStatus.OK if result.get("accepted") else HTTPStatus.BAD_REQUEST, result)
                        return
                    if route == "/satellites/disconnect":
                        principal = self._authenticated(body)
                        self._respond(HTTPStatus.OK, asyncio.run(application.satellite_disconnect(principal, str(body.get("session_id", "")))))
                        return
                    if route == "/auth/stream-ticket":
                        principal = self._authenticated(body)
                        ticket = ticket_service.issue(principal, str(body.get("scope", "events")))
                        self._respond(HTTPStatus.CREATED, {"stream_ticket": ticket.token, "scope": ticket.scope, "expires_at": ticket.expires_at.isoformat()})
                        return
                    if route == "/computer/apps/refresh":
                        self._authenticated(body)
                        self._respond(HTTPStatus.OK, asyncio.run(application.installed_applications(refresh=True)))
                        return
                    if route.startswith("/computer/apps/"):
                        parts = route.strip("/").split("/")
                        if len(parts) == 4 and parts[3] == "enabled":
                            self._authenticated(body)
                            enabled = body.get("enabled")
                            if not isinstance(enabled, bool):
                                raise ValueError("application_enabled_must_be_boolean")
                            self._respond(HTTPStatus.OK, asyncio.run(application.set_installed_application_enabled(parts[2], enabled)))
                            return
                        if len(parts) == 4 and parts[3] == "surface":
                            self._authenticated(body)
                            surface = body.get("surface")
                            if not isinstance(surface, str):
                                raise ValueError("application_surface_required")
                            self._respond(HTTPStatus.OK, asyncio.run(application.set_installed_application_surface(parts[2], surface)))
                            return
                    if route == "/messages":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.send_message(
                            str(body["text"]), principal.identity, principal.device,
                            session_id=body.get("session_id"),
                            conversation_id=body.get("conversation_id"),
                            client_message_id=body.get("client_message_id"),
                        ))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/messages/start":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.start_message(
                            str(body["text"]), principal.identity, principal.device,
                            session_id=body.get("session_id"),
                            conversation_id=body.get("conversation_id"),
                            client_message_id=body.get("client_message_id"),
                        ))
                        if result.get("state") == "queued" and not result.get("replayed"):
                            message_executor.submit(
                                _execute_background_message,
                                application,
                                str(result["run_id"]),
                                principal.identity,
                                principal.device,
                            )
                        self._respond(HTTPStatus.ACCEPTED, result)
                        return
                    if route == "/personal-operations/mode":
                        principal = self._authenticated(body)
                        ttl = body.get("ttl_seconds")
                        result = asyncio.run(application.set_personal_mode(principal.identity.owner_id, str(body["mode"]), ttl_seconds=float(ttl) if ttl is not None else None, source=str(body.get("source", "user"))))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/personal-operations/run":
                        principal = self._authenticated(body)
                        values = body.get("values", {})
                        self._respond(HTTPStatus.OK, asyncio.run(application.personal_operation(principal.identity.owner_id, str(body["operation"]), values if isinstance(values, dict) else {}, identity=principal.identity, device=principal.device)))
                        return
                    if route == "/focus/start":
                        principal = self._authenticated(body)
                        self._respond(HTTPStatus.OK, asyncio.run(application.focus_start(principal.identity.owner_id, body)))
                        return
                    if route == "/focus/end":
                        principal = self._authenticated(body)
                        self._respond(HTTPStatus.OK, asyncio.run(application.focus_end(principal.identity.owner_id, body)))
                        return
                    if route.startswith("/communications/follow-ups/") and route.endswith("/acknowledge"):
                        principal = self._authenticated(body)
                        followup_id = route.strip("/").split("/")[2]
                        self._respond(HTTPStatus.OK, asyncio.run(application.acknowledge_communication_followup(principal.identity.owner_id, followup_id)))
                        return
                    if route == "/communications/follow-ups":
                        principal = self._authenticated(body)
                        self._respond(HTTPStatus.CREATED, asyncio.run(application.create_communication_followup(principal.identity.owner_id, body)))
                        return
                    if route == "/communications/auto-send-rules":
                        principal = self._authenticated(body)
                        self._respond(HTTPStatus.CREATED, asyncio.run(application.create_communication_auto_send_rule(principal.identity.owner_id, body)))
                        return
                    if route.startswith("/routines/") and route.endswith("/run"):
                        principal = self._authenticated(body)
                        routine_id = route.strip("/").split("/")[1]
                        self._respond(HTTPStatus.OK, asyncio.run(application.run_routine(routine_id, principal.identity, principal.device, dry_run=bool(body.get("dry_run", True)))))
                        return
                    if route.startswith("/approvals/"):
                        approval_id = route.rsplit("/", 1)[-1]
                        principal = self._authenticated(body)
                        result = asyncio.run(application.resume_approval(
                            approval_id, str(body["run_id"]), principal.identity, principal.device,
                            bool(body["approved"]), principal.identity.identity_id,
                        ))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route.startswith("/runs/") and route.endswith("/cancel"):
                        run_id = route.split("/")[-2]
                        principal = self._authenticated(body)
                        result = asyncio.run(application.cancel(run_id, principal.identity, principal.device))
                        self._respond(HTTPStatus.OK if result else HTTPStatus.NOT_FOUND, result or {"error": "not_found"})
                        return
                    if route == "/missions":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.create_mission(principal.identity.owner_id, body))
                        self._respond(HTTPStatus.CREATED, result)
                        return
                    if route.startswith("/missions/"):
                        parts = route.strip("/").split("/")
                        if len(parts) == 3 and parts[2] in {"start", "pause", "resume", "cancel"}:
                            principal = self._authenticated(body)
                            result = asyncio.run(application.mission_action(principal.identity.owner_id, parts[1], parts[2], principal.identity, principal.device, approval_granted=bool(body.get("approval_granted", False))))
                            self._respond(HTTPStatus.OK, result)
                            return
                    if route.startswith("/skill-executions/") and route.endswith("/resume"):
                        principal = self._authenticated(body)
                        execution_id = route.strip("/").split("/")[1]
                        self._respond(HTTPStatus.OK, asyncio.run(application.resume_skill(execution_id, principal.identity, principal.device)))
                        return
                    if route.startswith("/skills/executions/") and route.endswith("/resume"):
                        principal = self._authenticated(body)
                        execution_id = route.strip("/").split("/")[2]
                        self._respond(HTTPStatus.OK, asyncio.run(application.resume_skill(execution_id, principal.identity, principal.device)))
                        return
                    if route.startswith("/skills/"):
                        parts = route.strip("/").split("/")
                        if len(parts) == 3 and parts[2] in {"enable", "disable"}:
                            self._authenticated(body)
                            self._respond(HTTPStatus.OK, asyncio.run(application.set_skill_enabled(parts[1], parts[2] == "enable")))
                            return
                        if len(parts) == 3 and parts[2] == "execute":
                            principal = self._authenticated(body)
                            values = body.get("values", body)
                            self._respond(HTTPStatus.OK, asyncio.run(application.execute_skill(parts[1], values if isinstance(values, dict) else {}, principal.identity, principal.device)))
                            return
                    if route == "/workspace/projects":
                        principal = self._authenticated(body)
                        self._respond(HTTPStatus.CREATED, asyncio.run(application.workspace_register(principal.identity.owner_id, str(body.get("repo_path", body.get("path", ""))), body.get("project_id") if isinstance(body.get("project_id"), str) else None)))
                        return
                    if route == "/briefings/generate":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.generate_briefing(principal.identity.owner_id, str(body.get("type", "morning"))))
                        self._respond(HTTPStatus.CREATED if result else HTTPStatus.NO_CONTENT, result or {})
                        return
                    if route == "/intelligence/detect":
                        principal = self._authenticated(body)
                        self._respond(HTTPStatus.OK, {"findings": asyncio.run(application.detect_intelligence(principal.identity.owner_id))})
                        return
                    if route.startswith("/intelligence/findings/") and route.endswith("/resolve"):
                        principal = self._authenticated(body)
                        finding_id = route.strip("/").split("/")[2]
                        self._respond(HTTPStatus.OK, asyncio.run(application.resolve_intelligence(principal.identity.owner_id, finding_id)))
                        return
                    if route == "/automations":
                        principal = self._authenticated(body)
                        self._respond(HTTPStatus.CREATED, asyncio.run(application.create_automation(principal.identity.owner_id, body, principal.identity, principal.device)))
                        return
                    if route.startswith("/automations/"):
                        parts = route.strip("/").split("/")
                        if len(parts) == 3 and parts[2] in {"enable", "disable"}:
                            principal = self._authenticated(body)
                            self._respond(HTTPStatus.OK, asyncio.run(application.set_automation_enabled(principal.identity.owner_id, parts[1], parts[2] == "enable")))
                            return
                    if route == "/evaluations/run":
                        principal = self._authenticated(body)
                        self._respond(HTTPStatus.OK, asyncio.run(application.run_evaluation(str(body["suite"]), principal.identity.owner_id)))
                        return
                    if route == "/experience/clients":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.connect_client(principal.identity, principal.device, body))
                        self._respond(HTTPStatus.CREATED, result)
                        return
                    if route.startswith("/experience/clients/") and route.endswith("/disconnect"):
                        principal = self._authenticated(body)
                        asyncio.run(application.disconnect_client(principal.identity, route.strip("/").split("/")[2]))
                        self._respond(HTTPStatus.NO_CONTENT, {})
                        return
                    if route == "/research/runs":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.research_start(principal.identity, principal.device, body))
                        self._respond(HTTPStatus.ACCEPTED, result)
                        return
                    if route.startswith("/research/runs/") and route.endswith("/cancel"):
                        principal = self._authenticated(body)
                        result = asyncio.run(application.research_cancel(principal.identity.owner_id, route.strip("/").split("/")[2]))
                        self._respond(HTTPStatus.OK if result else HTTPStatus.NOT_FOUND, result or {"error": "not_found"})
                        return
                    if route == "/engineering/sessions":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.engineering_session(principal.identity, principal.device, body))
                        self._respond(HTTPStatus.CREATED, result)
                        return
                    if route == "/engineering/actions":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.engineering_action(principal.identity, principal.device, body))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route.startswith("/engineering/approvals/"):
                        principal = self._authenticated(body)
                        result = asyncio.run(application.engineering_approval(principal.identity, route.rsplit("/", 1)[-1], bool(body.get("approved", False)), str(body.get("decided_by", principal.identity.identity_id))))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/workers/developer/run":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.developer_run(principal.identity, principal.device, body))
                        status = HTTPStatus.ACCEPTED if result.get("result", {}).get("status") == "approval_required" else HTTPStatus.OK
                        self._respond(status, result)
                        return
                    if route.startswith("/workers/developer/approvals/"):
                        principal = self._authenticated(body)
                        result = asyncio.run(application.decide_developer_approval(
                            principal.identity,
                            principal.device,
                            route.rsplit("/", 1)[-1],
                            body.get("approved"),
                            str(body.get("decided_by", principal.identity.identity_id)),
                        ))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/perception/screen":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.perception_screen(principal.identity, principal.device, body))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/perception/context":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.perception_context(principal.identity, principal.device, body))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/perception/latest":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.perception_latest(principal.identity, principal.device, body))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/perception/window":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.perception_window(principal.identity, principal.device, str(body["window"])))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route.startswith("/computer/approvals/"):
                        principal = self._authenticated(body)
                        approval_id = route.rsplit("/", 1)[-1]
                        result = asyncio.run(application.decide_computer_action(
                            approval_id, bool(body["approved"]), principal.identity.identity_id,
                            principal.identity, principal.device,
                        ))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/computer/actions":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.computer_action(
                            principal.identity, principal.device, str(body["action"]),
                            body.get("parameters") if isinstance(body.get("parameters"), dict) else {},
                            dry_run=bool(body.get("dry_run", True)),
                            target_device_id=body.get("target_device_id") if isinstance(body.get("target_device_id"), str) else None,
                        ))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route.startswith("/browser/approvals/"):
                        principal = self._authenticated(body)
                        approval_id = route.rsplit("/", 1)[-1]
                        result = asyncio.run(application.decide_browser_action(
                            approval_id, bool(body["approved"]), str(body.get("decided_by", principal.identity.identity_id))
                        ))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/browser/actions":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.browser_action(
                            principal.identity, principal.device, str(body["action"]),
                            body.get("parameters") if isinstance(body.get("parameters"), dict) else {},
                            dry_run=bool(body.get("dry_run", True)),
                        ))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route.startswith("/home/approvals/"):
                        principal = self._authenticated(body)
                        approval_id = route.rsplit("/", 1)[-1]
                        result = asyncio.run(application.decide_home_approval(
                            approval_id, bool(body["approved"]), principal.identity.owner_id
                        ))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/home/actions":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.home_action(
                            principal.identity, principal.device, str(body["entity_id"]), str(body["action"]),
                            body.get("parameters") if isinstance(body.get("parameters"), dict) else {},
                            dry_run=bool(body.get("dry_run", True)),
                        ))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/communications/drafts":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.communication_draft(
                            principal.identity.owner_id, str(body["channel"]), str(body["recipient"]), str(body["content"]),
                            body.get("reply_to") if isinstance(body.get("reply_to"), str) else None,
                        ))
                        self._respond(HTTPStatus.CREATED, result)
                        return
                    if route.startswith("/communications/intelligence/"):
                        principal = self._authenticated(body)
                        thread_id = route.rsplit("/", 1)[-1]
                        ids = tuple(item for item in body.get("message_ids", ()) if isinstance(item, str))
                        self._respond(HTTPStatus.CREATED, asyncio.run(application.communication_intelligence(principal.identity.owner_id, thread_id, ids)))
                        return
                    if route == "/communications/send/decide":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.decide_communication_send(
                            principal.identity.owner_id, str(body["approval_id"]), bool(body["approved"]),
                            str(body.get("decided_by", principal.identity.identity_id)),
                        ))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/communications/send":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.communication_send(
                            principal.identity, principal.device, str(body["channel"]), str(body["recipient"]), str(body["content"]),
                            important=bool(body.get("important", False)),
                        ))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/notifications":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.create_notification(principal.identity.owner_id, body))
                        self._respond(HTTPStatus.CREATED, result)
                        return
                    if route.startswith("/notifications/") and route.endswith("/deliver"):
                        principal = self._authenticated(body)
                        notification_id = route.strip("/").split("/")[1]
                        result = asyncio.run(application.deliver_notification(principal.identity.owner_id, notification_id, body))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route.startswith("/notifications/") and route.endswith("/dismiss"):
                        principal = self._authenticated(body)
                        notification_id = route.strip("/").split("/")[1]
                        result = asyncio.run(application.dismiss_notification(principal.identity.owner_id, notification_id))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/memory":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.create_memory(
                            principal.identity.owner_id, str(body["content"]), str(body.get("category", "fact")),
                            structured_data=body.get("structured_data") if isinstance(body.get("structured_data"), dict) else None,
                            source=str(body.get("source", "user")), source_reference=str(body.get("source_reference", "api")),
                            confidence=float(body.get("confidence", 1.0)), sensitivity=str(body.get("sensitivity", "personal")),
                            tags=tuple(item for item in body.get("tags", []) if isinstance(item, str)),
                        ))
                        self._respond(HTTPStatus.CREATED, result)
                        return
                    if route == "/memory/search":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.list_memory(
                            principal.identity.owner_id, text=str(body.get("text", body.get("q", ""))),
                            category=body.get("category") if isinstance(body.get("category"), str) else None,
                            source=body.get("source") if isinstance(body.get("source"), str) else None,
                            tags=tuple(item for item in body.get("tags", []) if isinstance(item, str)),
                            include_archived=bool(body.get("include_archived", False)), limit=int(body.get("limit", 50)),
                        ))
                        self._respond(HTTPStatus.OK, {"memories": result})
                        return
                    if route == "/memory/forget-category":
                        principal = self._authenticated(body)
                        count = asyncio.run(application.forget_memory_category(principal.identity.owner_id, str(body["category"])))
                        self._respond(HTTPStatus.OK, {"deleted": count, "category": str(body["category"])})
                        return
                    if route.startswith("/memory/"):
                        parts = route.strip("/").split("/")
                        if len(parts) == 3 and parts[2] in {"pin", "archive"}:
                            principal = self._authenticated(body)
                            enabled = bool(body.get("enabled", True))
                            if parts[2] == "pin":
                                result = asyncio.run(application.pin_memory(principal.identity.owner_id, parts[1], enabled))
                            else:
                                result = asyncio.run(application.archive_memory(principal.identity.owner_id, parts[1], enabled))
                            self._respond(HTTPStatus.OK, result)
                            return
                    if route == "/goals":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.create_goal(principal.identity.owner_id, body))
                        self._respond(HTTPStatus.CREATED, result)
                        return
                    if route.startswith("/goals/"):
                        parts = route.strip("/").split("/")
                        if len(parts) == 3 and parts[2] in {"pause", "resume", "cancel", "complete", "activate"}:
                            principal = self._authenticated(body)
                            result = asyncio.run(application.control_goal(principal.identity.owner_id, parts[1], parts[2]))
                            self._respond(HTTPStatus.OK, result)
                            return
                    if route.startswith("/proactive/findings/") and route.endswith("/acknowledge"):
                        principal = self._authenticated(body)
                        finding_id = route.split("/")[-2]
                        result = asyncio.run(application.acknowledge_finding(principal.identity.owner_id, finding_id))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/devices/enroll/ticket":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.issue_device_enrollment_ticket(principal.identity.owner_id, body))
                        self._respond(HTTPStatus.CREATED, result)
                        return
                    if route == "/devices/enroll":
                        result = asyncio.run(application.enroll_device(body))
                        self._respond(HTTPStatus.OK if result.get("accepted") else HTTPStatus.BAD_REQUEST, result)
                        return
                    if route.startswith("/devices/") and route.endswith("/revoke"):
                        principal = self._authenticated(body)
                        device_id = route.strip("/").split("/")[1]
                        result = asyncio.run(application.revoke_device(principal.identity.owner_id, device_id))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route.startswith("/devices/") and route.endswith("/degraded"):
                        principal = self._authenticated(body)
                        device_id = route.strip("/").split("/")[1]
                        reason = str(body.get("reason", "degraded"))
                        result = asyncio.run(application.mark_device_degraded(principal.identity.owner_id, device_id, reason=reason))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/voice/room/utterance":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.handle_room_voice_utterance(body, owner_id=principal.identity.owner_id))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/voice/room/barge_in":
                        principal = self._authenticated(body)
                        result = asyncio.run(application.room_voice_barge_in(body, owner_id=principal.identity.owner_id))
                        self._respond(HTTPStatus.OK, result)
                        return
                    self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                except PermissionError:
                    self._respond(HTTPStatus.UNAUTHORIZED, {"error": "principal_not_found"})
                except (KeyError, TypeError, ValueError) as exc:
                    self._respond(HTTPStatus.BAD_REQUEST, {"error": str(exc) or exc.__class__.__name__})
                except Exception as exc:
                    self._respond(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": exc.__class__.__name__})

            def do_PATCH(self) -> None:  # noqa: N802 - stdlib handler API
                parsed = urlparse(self.path)
                route = self._route(parsed.path)
                try:
                    body = self._body()
                    principal = self._authenticated(body)
                    owner_id = principal.identity.owner_id
                    if route.startswith("/memory/"):
                        values = {key: value for key, value in body.items() if key not in {"credential", "device_id", "identity_id"}}
                        result = asyncio.run(application.update_memory(owner_id, route.rsplit("/", 1)[-1], values))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route.startswith("/goals/"):
                        goal_id = route.rsplit("/", 1)[-1]
                        result = asyncio.run(application.update_goal(owner_id, goal_id, body))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route == "/personalization/profile":
                        values = body.get("values", {key: value for key, value in body.items() if key not in {"credential", "device_id", "identity_id", "source"}})
                        if not isinstance(values, dict):
                            raise ValueError("personalization values must be an object")
                        result = asyncio.run(application.update_personalization(owner_id, values, str(body.get("source", "user"))))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route.startswith("/communications/auto-send-rules/"):
                        rule_id = route.strip("/").split("/")[-1]
                        values = {key: value for key, value in body.items() if key not in {"credential", "device_id", "identity_id"}}
                        result = asyncio.run(application.update_communication_auto_send_rule(owner_id, rule_id, values))
                        self._respond(HTTPStatus.OK, result)
                        return
                    if route.startswith("/automations/"):
                        rule_id = route.strip("/").split("/")[1]
                        if "enabled" in body:
                            result = asyncio.run(application.set_automation_enabled(owner_id, rule_id, bool(body["enabled"])))
                            self._respond(HTTPStatus.OK, result)
                            return
                    self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                except PermissionError:
                    self._respond(HTTPStatus.UNAUTHORIZED, {"error": "principal_not_found"})
                except KeyError:
                    self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                except (TypeError, ValueError) as exc:
                    self._respond(HTTPStatus.BAD_REQUEST, {"error": str(exc) or exc.__class__.__name__})
                except Exception as exc:
                    self._respond(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": exc.__class__.__name__})

            def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler API
                parsed = urlparse(self.path)
                route = self._route(parsed.path)
                try:
                    body = self._body()
                    principal = self._authenticated(body)
                    if route.startswith("/memory/"):
                        asyncio.run(application.delete_memory(principal.identity.owner_id, route.rsplit("/", 1)[-1]))
                        self._respond(HTTPStatus.NO_CONTENT, {})
                        return
                    self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                except PermissionError:
                    self._respond(HTTPStatus.UNAUTHORIZED, {"error": "principal_not_found"})
                except KeyError:
                    self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                except (TypeError, ValueError) as exc:
                    self._respond(HTTPStatus.BAD_REQUEST, {"error": str(exc) or exc.__class__.__name__})
                except Exception as exc:
                    self._respond(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": exc.__class__.__name__})

            @staticmethod
            def _route(path: str) -> str:
                route = path.removeprefix("/v1")
                return route.rstrip("/") or "/"

            @staticmethod
            def _is_public_app_route(route: str) -> bool:
                return route == "/app" or route.startswith("/app/")

            def _desktop_session(self) -> Any | None:
                return desktop_sessions.get_session(self._cookie("jarvis_session"))

            def _cookie(self, name: str) -> str | None:
                parsed = SimpleCookie()
                try:
                    parsed.load(self.headers.get("Cookie", ""))
                except Exception:
                    return None
                morsel = parsed.get(name)
                return morsel.value if morsel is not None else None

            @staticmethod
            def _session_cookie(token: str, expires_at: Any) -> str:
                max_age = max(1, int((expires_at - datetime.now(UTC)).total_seconds()))
                return f"jarvis_session={token}; Max-Age={max_age}; HttpOnly; SameSite=Strict; Path=/"

            def _serve_app_asset(self, relative: str) -> None:
                root = CoreHttpServer._APP_STATIC_ROOT.resolve()
                candidate = (root / relative).resolve()
                if not candidate.is_relative_to(root) or not candidate.is_file():
                    self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                    return
                content_types = {
                    ".css": "text/css; charset=utf-8",
                    ".html": "text/html; charset=utf-8",
                    ".js": "text/javascript; charset=utf-8",
                    ".jpeg": "image/jpeg",
                    ".jpg": "image/jpeg",
                    ".png": "image/png",
                    ".webp": "image/webp",
                }
                payload = candidate.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_types.get(candidate.suffix, "application/octet-stream"))
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
                )
                self.end_headers()
                self.wfile.write(payload)

            def _websocket(self, query: dict[str, list[str]]) -> None:
                """Serve a bounded authenticated local fan-out connection.

                The stdlib HTTP server has no WebSocket dependency. This keeps
                the protocol boundary useful for local clients while applying
                explicit limits; deployment hosts may replace this transport
                with a full ASGI adapter without changing the experience API.
                """

                ticket = query.get("stream_ticket", [None])[0]
                if ticket:
                    issued = ticket_service.consume(ticket, "experience.events.ws")
                    if issued is None:
                        raise PermissionError("invalid_stream_ticket")
                    principal = asyncio.run(application.principal(issued.identity_id, issued.device_id))
                    if principal is None or principal.identity.owner_id != issued.owner_id:
                        raise PermissionError("stream_ticket_principal_revoked")
                else:
                    principal = self._authenticated({})
                key = self.headers.get("Sec-WebSocket-Key", "")
                if self.headers.get("Upgrade", "").casefold() != "websocket":
                    raise ValueError("WebSocket Upgrade header is required")
                if "upgrade" not in self.headers.get("Connection", "").casefold():
                    raise ValueError("WebSocket Connection header is required")
                accepted = accept_key(key)
                topics = tuple(query.get("topic", ())) or ("system_health",)
                if len(topics) > 12:
                    raise ValueError("WebSocket subscription limit exceeded")
                session = asyncio.run(application.connect_client(principal.identity, principal.device, {"subscriptions": topics, "ui_profile": "websocket"}))
                outbound: queue.Queue[dict[str, object]] = queue.Queue(maxsize=128)

                def on_event(event: Any) -> None:
                    owner = event.payload.get("owner_id")
                    if owner != principal.identity.owner_id:
                        return
                    topic = event.category.value
                    if topic not in topics and not (topic == "system" and "system_health" in topics):
                        return
                    item = {"type": "event", "event": ExperienceProjection._event_item(event)}
                    try:
                        outbound.put_nowait(item)
                    except queue.Full:
                        try:
                            outbound.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            outbound.put_nowait({"type": "control", "error": "backpressure"})
                        except queue.Full:
                            pass

                subscription = application.runtime.event_bus.subscribe("*", on_event)
                self.send_response(HTTPStatus.SWITCHING_PROTOCOLS)
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accepted)
                self.end_headers()
                self.close_connection = True
                try:
                    try:
                        self.connection.sendall(text_frame({"type": "state", "data": asyncio.run(application.experience_state(principal.identity.owner_id))}))
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                    deadline = time.monotonic() + 30.0
                    next_ping = time.monotonic() + 10.0
                    while time.monotonic() < deadline:
                        try:
                            self.connection.sendall(text_frame(outbound.get(timeout=0.25)))
                        except queue.Empty:
                            if time.monotonic() >= next_ping:
                                self.connection.sendall(ping_frame())
                                next_ping = time.monotonic() + 10.0
                        except (BrokenPipeError, ConnectionResetError, OSError):
                            break
                    try:
                        self.connection.sendall(close_frame())
                    except OSError:
                        pass
                finally:
                    application.runtime.event_bus.unsubscribe(subscription)
                    try:
                        asyncio.run(application.disconnect_client(principal.identity, session["client_session_id"]))
                    except Exception:
                        pass

            def _owner(self, query: dict[str, list[str]]) -> str:
                requested = query.get("owner_id", [None])[0]
                principal = self._authenticated({})
                if requested and requested != principal.identity.owner_id:
                    raise PermissionError("owner_authentication_required")
                return principal.identity.owner_id

            def _authenticated(self, values: dict[str, Any], *, require_session: bool = False) -> Any:
                values = dict(values)
                if self.command == "GET":
                    if "credential" in values:
                        raise PermissionError("query_credentials_not_allowed")
                    # GET query parameters are resource filters, never
                    # principal material. Device/identity stay header-bound.
                    values.pop("device_id", None)
                    values.pop("identity_id", None)
                if not require_session:
                    authorization = self.headers.get("Authorization", "")
                    if "credential" not in values and authorization.casefold().startswith("bearer "):
                        values["credential"] = authorization[7:].strip()
                    values.setdefault("device_id", self.headers.get("X-JARVIS-Device-ID") or self.headers.get("X-Device-ID"))
                    values.setdefault("identity_id", self.headers.get("X-JARVIS-Identity-ID") or self.headers.get("X-Identity-ID"))
                    required = ("credential", "device_id", "identity_id")
                    if not any(not values.get(key) for key in required):
                        principal = asyncio.run(application.authenticate_principal(
                            str(values["credential"]), str(values["device_id"]), str(values["identity_id"])
                        ))
                        if principal is None:
                            raise PermissionError("principal_not_found")
                        return principal
                session = self._desktop_session()
                if session is None:
                    raise PermissionError("credential_device_and_identity_required")
                if self.command != "GET":
                    self._validate_origin()
                if self.command != "GET" and self.headers.get("X-JARVIS-CSRF") != session.csrf_token:
                    raise PermissionError("csrf_required")
                principal = asyncio.run(application.principal(session.identity_id, session.device_id))
                if principal is None or principal.identity.owner_id != session.owner_id:
                    desktop_sessions.revoke_session(session.token)
                    raise PermissionError("desktop_session_principal_not_found")
                return principal

            def _validate_origin(self) -> None:
                origin = self.headers.get("Origin")
                if not origin:
                    return
                parsed = urlparse(origin)
                if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                    raise PermissionError("origin_not_allowed")
                try:
                    port = parsed.port
                except ValueError as exc:
                    raise PermissionError("origin_not_allowed") from exc
                if port != self.server.server_port:
                    raise PermissionError("origin_not_allowed")

            def _stream_principal(self, query: dict[str, list[str]], scope: str) -> Any:
                token = query.get("stream_ticket", [None])[0]
                if token:
                    issued = ticket_service.consume(token, scope)
                    if issued is None:
                        raise PermissionError("invalid_stream_ticket")
                    principal = asyncio.run(application.principal(issued.identity_id, issued.device_id))
                    if principal is None or principal.identity.owner_id != issued.owner_id:
                        raise PermissionError("stream_ticket_principal_revoked")
                    return principal
                return self._authenticated({})

            def _body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 1_000_000:
                    raise ValueError("request body must be a non-empty JSON object")
                decoded = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(decoded, dict):
                    raise ValueError("request body must be a JSON object")
                return decoded

            def _respond(self, status: HTTPStatus, payload: Any, headers: dict[str, str] | None = None) -> None:
                encoded = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
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
