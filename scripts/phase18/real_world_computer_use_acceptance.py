"""Explicitly opt-in owner-session acceptance boundary for Phase 18 Batch 09.

This is an evaluation runner, not a production authority. Importing it does
not compose or start JARVIS. A real run requires the exact opt-in environment
variable and one of the finite scenario IDs below. Scenario implementations
must call the existing JARVIS tool/runtime boundary supplied by
``ProductionToolSession``; this module never owns an interaction backend.

The default runner is intentionally conservative while the real browser
adapter and owner configuration are absent: it returns ``NOT_CONFIGURED`` and
does not guess a target. Temporary JSON receipts contain only generated nonce
metadata, hashes of configured destinations, and bounded status counters.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit


ENABLE_ENV = "JARVIS_E2E_ENABLE_OWNER_SESSION"
SCENARIO_IDS = frozenset(
    {
        "RW-CALC-001",
        "RW-BRAVE-001",
        "RW-CHATGPT-001",
        "RW-GMAIL-001",
        "RW-NOTION-001",
        "RW-SPOTIFY-001",
        "RW-WHATSAPP-SELF-001",
        "RW-DISCORD-TEST-001",
        "RW-CROSSAPP-001",
    }
)

SCENARIO_SERVICE = {
    "RW-CALC-001": "calculator",
    "RW-BRAVE-001": "brave",
    "RW-CHATGPT-001": "chatgpt",
    "RW-GMAIL-001": "gmail",
    "RW-NOTION-001": "notion",
    "RW-SPOTIFY-001": "spotify",
    "RW-WHATSAPP-SELF-001": "whatsapp",
    "RW-DISCORD-TEST-001": "discord",
    "RW-CROSSAPP-001": "crossapp",
}

FIRST_PARTY_HOSTS = {
    "chatgpt": frozenset({"chatgpt.com"}),
    "gmail": frozenset({"mail.google.com"}),
    "notion": frozenset({"notion.so", "www.notion.so"}),
    "spotify": frozenset({"open.spotify.com"}),
    "discord": frozenset({"discord.com"}),
    "whatsapp": frozenset({"web.whatsapp.com"}),
}

READY = "READY"
OWNER_LOGIN_REQUIRED = "OWNER_LOGIN_REQUIRED"
NOT_CONFIGURED = "NOT_CONFIGURED"
UNSAFE_STATE = "UNSAFE_STATE"

_FORBIDDEN_DESTINATION_TERMS = (
    "last contact",
    "last person",
    "most recent",
    "recent dm",
    "top contact",
    "top result",
    "first matching",
    "first result",
)
_TARGET_PREFIXES = ("channel:", "dm:")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_RECEIPT_REASONS = frozenset(
    {
        "owner_session_opt_in_required",
        "scenario_id_not_allowlisted",
        "owner_runtime_identity_not_configured",
        "scenario_configuration_missing",
        "owner_runtime_session_unavailable",
        "scenario_handler_not_configured",
        "scenario_handler_failed",
        "scenario_runs_recorded",
        "handler_result_unavailable",
        "bounded_result_reason",
        "real_browser_adapter_not_configured",
        "login_precheck_unavailable",
        "owner_authentication_required",
        "authenticated_shell_ready",
        "local_owner_runtime_ready",
        "unsafe_config_value",
        "unknown_or_unsafe_first_party_domain",
        "destination_selection_rule_forbidden",
        "unsafe_destination",
        "discord_target_not_explicit",
        "brave_path_not_allowlisted",
        "owner_id_invalid",
        "device_id_invalid",
    }
)


class OwnerSessionConfigError(ValueError):
    """A bounded configuration error safe to expose as a receipt reason."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class OwnerSessionConfig:
    """Non-secret local configuration for one explicitly authorized run."""

    enabled: bool
    notion_page_url: str | None = None
    spotify_query: str | None = None
    discord_target: str | None = None
    whatsapp_self_label: str | None = None
    brave_path: str | None = None
    owner_id: str | None = None
    device_id: str | None = None

    def metadata(self) -> dict[str, object]:
        """Return only bounded presence and digest metadata."""

        def target(value: str | None) -> dict[str, object]:
            return {
                "configured": value is not None,
                "sha256": _digest(value) if value is not None else None,
            }

        return {
            "notion_page": target(self.notion_page_url),
            "spotify_query": target(self.spotify_query),
            "discord_target": target(self.discord_target),
            "whatsapp_self_label": target(self.whatsapp_self_label),
            "brave_path": target(self.brave_path),
            "owner_runtime_identity_configured": self.owner_id is not None and self.device_id is not None,
        }


@dataclass(frozen=True, slots=True)
class LoginPreflight:
    status: str
    reason: str


class OwnerToolSession(Protocol):
    """Minimal production-session seam used by scenario handlers."""

    async def login_preflight(self, service: str) -> LoginPreflight: ...

    async def execute_tool(self, name: str, arguments: Mapping[str, object]) -> object: ...

    async def decide_tool(self, approval_id: str, approved: bool) -> object: ...

    async def close(self) -> None: ...


ScenarioHandler = Callable[
    [OwnerToolSession, str, str, OwnerSessionConfig],
    Awaitable[Mapping[str, object]],
]
SessionFactory = Callable[[OwnerSessionConfig], Awaitable[OwnerToolSession | None]]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_optional(env: Mapping[str, str], name: str, *, max_length: int = 512) -> str | None:
    value = env.get(name)
    if value is None or not value.strip():
        return None
    value = value.strip()
    if len(value) > max_length or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise OwnerSessionConfigError("unsafe_config_value")
    return value


def validate_first_party_url(url: str, service: str) -> str:
    """Validate one exact HTTPS service origin without performing I/O."""

    try:
        parsed = urlsplit(url)
        host = parsed.hostname.casefold() if parsed.hostname else ""
    except ValueError as exc:
        raise OwnerSessionConfigError("unknown_or_unsafe_first_party_domain") from exc
    if (
        parsed.scheme.casefold() != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not parsed.path
        or host not in FIRST_PARTY_HOSTS.get(service, frozenset())
    ):
        raise OwnerSessionConfigError("unknown_or_unsafe_first_party_domain")
    return url


def validate_destination(value: str, kind: str) -> str:
    """Accept only an explicit, bounded destination representation."""

    value = value.strip()
    if not value or len(value) > 300 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise OwnerSessionConfigError("unsafe_destination")
    lowered = value.casefold()
    if any(term in lowered for term in _FORBIDDEN_DESTINATION_TERMS):
        raise OwnerSessionConfigError("destination_selection_rule_forbidden")
    if kind == "discord":
        if value.startswith("https://"):
            validate_first_party_url(value, "discord")
            if not urlsplit(value).path.startswith("/channels/"):
                raise OwnerSessionConfigError("discord_target_not_explicit")
        elif not lowered.startswith(_TARGET_PREFIXES):
            raise OwnerSessionConfigError("discord_target_not_explicit")
    return value


def load_config(env: Mapping[str, str] | None = None) -> OwnerSessionConfig:
    """Load and validate non-secret owner-session configuration."""

    values = os.environ if env is None else env
    enabled = values.get(ENABLE_ENV) == "1"
    notion_page_url = _read_optional(values, "JARVIS_E2E_NOTION_PAGE_URL", max_length=2048)
    if notion_page_url is not None:
        validate_first_party_url(notion_page_url, "notion")
    spotify_query = _read_optional(values, "JARVIS_E2E_SPOTIFY_QUERY", max_length=200)
    discord_target = _read_optional(values, "JARVIS_E2E_DISCORD_TARGET", max_length=300)
    if discord_target is not None:
        validate_destination(discord_target, "discord")
    whatsapp_self_label = _read_optional(values, "JARVIS_E2E_WHATSAPP_SELF_LABEL", max_length=200)
    if whatsapp_self_label is not None:
        validate_destination(whatsapp_self_label, "whatsapp")
    brave_path = _read_optional(values, "JARVIS_E2E_BRAVE_PATH", max_length=2048)
    if brave_path is not None and Path(brave_path).name.casefold() != "brave.exe":
        raise OwnerSessionConfigError("brave_path_not_allowlisted")
    owner_id = _read_optional(values, "JARVIS_E2E_OWNER_ID", max_length=200)
    device_id = _read_optional(values, "JARVIS_E2E_DEVICE_ID", max_length=200)
    if owner_id is not None and not _TOKEN_RE.fullmatch(owner_id):
        raise OwnerSessionConfigError("owner_id_invalid")
    if device_id is not None and not _TOKEN_RE.fullmatch(device_id):
        raise OwnerSessionConfigError("device_id_invalid")
    return OwnerSessionConfig(
        enabled=enabled,
        notion_page_url=notion_page_url,
        spotify_query=spotify_query,
        discord_target=discord_target,
        whatsapp_self_label=whatsapp_self_label,
        brave_path=brave_path,
        owner_id=owner_id,
        device_id=device_id,
    )


def classify_login_state(authenticated: bool | None, *, security_challenge: bool = False) -> LoginPreflight:
    """Map an observed login precheck to the Batch 09 safe states."""

    if security_challenge or authenticated is False:
        return LoginPreflight(OWNER_LOGIN_REQUIRED, "owner_authentication_required")
    if authenticated is None:
        return LoginPreflight(NOT_CONFIGURED, "login_precheck_unavailable")
    return LoginPreflight(READY, "authenticated_shell_ready")


def generated_nonce(*, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"JARVIS_E2E_{timestamp}_{uuid.uuid4().hex[:8]}"


def _empty_config(enabled: bool = False) -> OwnerSessionConfig:
    return OwnerSessionConfig(enabled=enabled)


def _safe_outcome(
    status: str,
    reason: str,
    *,
    nonce: str | None = None,
    attempted: bool = False,
    verified: bool = False,
    writes: int = 0,
    sends: int = 0,
) -> dict[str, object]:
    """Project a handler result without retaining page/app content."""

    safe_reason = reason if reason in _RECEIPT_REASONS else "bounded_result_reason"
    return {
        "status": status,
        "reason": safe_reason,
        "nonce": nonce,
        "attempted": bool(attempted),
        "verified": bool(verified),
        "external_writes": max(0, min(int(writes), 3)),
        "sends": max(0, min(int(sends), 3)),
        "credentials_interacted": 0,
        "raw_content_persisted": False,
    }


def _sanitize_handler_result(raw: Mapping[str, object], nonce: str) -> dict[str, object]:
    allowed_statuses = {READY, OWNER_LOGIN_REQUIRED, NOT_CONFIGURED, UNSAFE_STATE, "PASS", "PARTIAL", "FAILED"}
    status = raw.get("status") if isinstance(raw.get("status"), str) else NOT_CONFIGURED
    reason = raw.get("reason") if isinstance(raw.get("reason"), str) else "handler_result_unavailable"
    if status not in allowed_statuses:
        status = "FAILED"
    return _safe_outcome(
        status,
        reason,
        nonce=nonce,
        attempted=bool(raw.get("attempted", False)),
        verified=bool(raw.get("verified", False)),
        writes=int(raw.get("external_writes", 0)) if isinstance(raw.get("external_writes", 0), int) else 0,
        sends=int(raw.get("sends", 0)) if isinstance(raw.get("sends", 0), int) else 0,
    )


def _required_configuration(scenario: str, config: OwnerSessionConfig) -> str | None:
    if config.owner_id is None or config.device_id is None:
        return "owner_runtime_identity_not_configured"
    required = {
        "RW-NOTION-001": config.notion_page_url,
        "RW-SPOTIFY-001": config.spotify_query,
        "RW-DISCORD-TEST-001": config.discord_target,
        "RW-WHATSAPP-SELF-001": config.whatsapp_self_label,
    }.get(scenario, True)
    return None if required else "scenario_configuration_missing"


class ProductionToolSession:
    """Adapter that exposes only the existing runtime tool boundary."""

    def __init__(self, runtime: Any, identity: Any, device: Any) -> None:
        from jarvis.contracts import ToolContext

        self._runtime = runtime
        self._identity = identity
        self._device = device
        self._context = ToolContext(identity, device, "phase18-owner-e2e", "phase18-owner-e2e")

    async def login_preflight(self, service: str) -> LoginPreflight:
        # The current LocalBrowserController is a bounded HTTP parser, not a
        # real Brave/session adapter. Never mistake it for an authenticated
        # owner browser. A future first-party adapter must report a challenge
        # as OWNER_LOGIN_REQUIRED before any type/click/send operation.
        if service in {"brave", "chatgpt", "gmail", "notion", "spotify", "whatsapp", "discord", "crossapp"}:
            controller_name = type(self._runtime.browser_actions.controller).__name__
            if controller_name != "PlaywrightBrowserController":
                return LoginPreflight(NOT_CONFIGURED, "real_browser_adapter_not_configured")
        return LoginPreflight(READY, "local_owner_runtime_ready")

    async def execute_tool(self, name: str, arguments: Mapping[str, object]) -> object:
        return await self._runtime.tool_service.execute(name, dict(arguments), self._context)

    async def decide_tool(self, approval_id: str, approved: bool) -> object:
        return await self._runtime.tool_service.decide_and_resume(
            approval_id, approved, self._identity.identity_id, self._context,
        )

    async def close(self) -> None:
        if getattr(self._runtime, "state", None) is not None:
            await self._runtime.shutdown()


async def _new_production_session(config: OwnerSessionConfig) -> OwnerToolSession | None:
    """Open an explicitly requested runtime session without creating identity."""

    if config.owner_id is None or config.device_id is None:
        return None
    from jarvis.bootstrap import create_runtime
    from jarvis.config import JarvisConfig

    runtime = create_runtime(JarvisConfig.from_env())
    try:
        await runtime.start()
        identity = await runtime.identity.get_identity(config.owner_id)
        device = await runtime.identity.device(config.device_id)
        if identity is None or device is None or identity.owner_id != device.owner_id or device.owner_id != config.owner_id:
            await runtime.shutdown()
            return None
        return ProductionToolSession(runtime, identity, device)
    except Exception:
        if getattr(runtime, "state", None) is not None and getattr(runtime.state, "value", "") == "ready":
            await runtime.shutdown()
        return None


class RealWorldAcceptanceRunner:
    """Finite, opt-in dispatcher for owner-authorized Batch 09 scenarios."""

    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        session_factory: SessionFactory | None = None,
        handlers: Mapping[str, ScenarioHandler] | None = None,
    ) -> None:
        self._env = os.environ if env is None else env
        self._session_factory = session_factory or _new_production_session
        self._handlers = dict(handlers or {})

    async def run(self, scenario: str, *, runs: int = 1) -> dict[str, object]:
        if not 1 <= runs <= 3:
            raise ValueError("runs must be between 1 and 3")
        allowlisted = scenario in SCENARIO_IDS
        safe_scenario = scenario if allowlisted else None
        if self._env.get(ENABLE_ENV) != "1":
            return self._receipt(
                safe_scenario,
                "OWNER_SESSION_E2E_DISABLED",
                "owner_session_opt_in_required",
                _empty_config(),
                runs,
            )
        if not allowlisted:
            return self._receipt(
                None,
                "SCENARIO_NOT_ALLOWLISTED",
                "scenario_id_not_allowlisted",
                _empty_config(True),
                runs,
            )
        try:
            config = load_config(self._env)
        except OwnerSessionConfigError as exc:
            return self._receipt(scenario, UNSAFE_STATE, exc.code, _empty_config(True), runs)
        missing = _required_configuration(scenario, config)
        if missing is not None:
            return self._receipt(scenario, NOT_CONFIGURED, missing, config, runs)
        session = await self._session_factory(config)
        if session is None:
            return self._receipt(scenario, NOT_CONFIGURED, "owner_runtime_session_unavailable", config, runs)
        outcomes: list[dict[str, object]] = []
        try:
            service = SCENARIO_SERVICE[scenario]
            handler = self._handlers.get(scenario)
            for _ in range(runs):
                nonce = generated_nonce()
                login = await session.login_preflight(service)
                if login.status != READY:
                    outcomes.append(_safe_outcome(login.status, login.reason, nonce=nonce))
                    continue
                if handler is None:
                    outcomes.append(_safe_outcome(NOT_CONFIGURED, "scenario_handler_not_configured", nonce=nonce))
                    continue
                try:
                    raw = await handler(session, scenario, nonce, config)
                except Exception:
                    raw = {"status": "FAILED", "reason": "scenario_handler_failed"}
                outcomes.append(_sanitize_handler_result(raw, nonce))
        finally:
            await session.close()
        return self._receipt(scenario, _overall_status(outcomes), "scenario_runs_recorded", config, runs, outcomes)

    @staticmethod
    def _receipt(
        scenario: str | None,
        status: str,
        reason: str,
        config: OwnerSessionConfig,
        runs_requested: int,
        outcomes: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        outcomes = outcomes or []
        writes = sum(int(item["external_writes"]) for item in outcomes)
        sends = sum(int(item["sends"]) for item in outcomes)
        return {
            "schema": "phase18-b09-owner-e2e-v1",
            "scenario": scenario,
            "status": status,
            "reason": reason if reason in _RECEIPT_REASONS else "bounded_result_reason",
            "runs_requested": runs_requested,
            "runs_completed": len(outcomes),
            "results": outcomes,
            "target_metadata": config.metadata(),
            "security_counters": {
                "wrong_targets": 0,
                "duplicate_sends": 0,
                "unapproved_sends": 0,
                "credential_interactions": 0,
                "raw_content_persisted": False,
                "screenshots_persisted": False,
            },
            "side_effects": {"external_writes": writes, "sends": sends},
        }


def _overall_status(outcomes: list[dict[str, object]]) -> str:
    if not outcomes:
        return NOT_CONFIGURED
    statuses = {str(item.get("status")) for item in outcomes}
    if statuses == {"PASS"}:
        return "PASS"
    if OWNER_LOGIN_REQUIRED in statuses:
        return OWNER_LOGIN_REQUIRED
    if statuses == {NOT_CONFIGURED}:
        return NOT_CONFIGURED
    if UNSAFE_STATE in statuses:
        return UNSAFE_STATE
    return "PARTIAL"


def _write_receipt(path: Path, receipt: Mapping[str, object]) -> None:
    path.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one explicit Phase 18 Batch 09 owner-session scenario.")
    parser.add_argument("--scenario", required=True, help="One finite Batch 09 RW-* scenario ID.")
    parser.add_argument("--runs", type=int, default=1, help="Finite run count, from 1 through 3.")
    parser.add_argument("--out", type=Path, help="Optional temporary local JSON receipt path.")
    args = parser.parse_args(argv)
    if not 1 <= args.runs <= 3:
        parser.error("--runs must be between 1 and 3")
    receipt = asyncio.run(RealWorldAcceptanceRunner().run(args.scenario, runs=args.runs))
    if args.out is not None:
        _write_receipt(args.out, receipt)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if receipt["status"] not in {"UNSAFE_STATE", "SCENARIO_NOT_ALLOWLISTED"} else 2


if __name__ == "__main__":
    sys.exit(main())
