"""Finite, fail-closed Batch 10 T6 owner-session acceptance boundary.

The runner is deliberately separate from model/tool orchestration. It accepts
only process-local non-secret configuration, uses the existing
``BrowserActionService`` for every browser action, and never reads or exports
cookies, tokens, credentials, profile databases, or raw screenshots.

Before the nonce send, the owner must provide both explicit opt-in and a
separate local confirmation flag. If the dedicated profile is not already
authenticated, the runner reports ``OWNER_LOGIN_REQUIRED`` and stops without
typing or clicking anything.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from jarvis.bootstrap import create_runtime
from jarvis.browser.profile import BrowserProfilePolicy, BrowserProfilePolicyError, validate_brave_executable_path
from jarvis.contracts import BrowserAction, BrowserResult, BrowserSessionMode, DeviceIdentity, Identity, ToolContext
from jarvis.config import JarvisConfig


OPT_IN_ENV = "JARVIS_BROWSER_V2_OWNER_ACCEPTANCE"
CONFIRM_ENV = "JARVIS_BROWSER_T6_CONFIRM_SEND"
OWNER_ID_ENV = "JARVIS_E2E_OWNER_ID"
DEVICE_ID_ENV = "JARVIS_E2E_DEVICE_ID"
EXECUTABLE_ENV = "JARVIS_BROWSER_EXECUTABLE_PATH"
PROFILE_ENV = "JARVIS_BROWSER_PROFILE_ROOT"
URL_ENV = "JARVIS_BROWSER_T6_URL"

PARTIAL = "BROWSER_V2_PARTIAL"
READY = "BROWSER_V2_OWNER_SESSION_READY"
OWNER_LOGIN_REQUIRED = "OWNER_LOGIN_REQUIRED"

REQUIRED_CAPABILITIES = frozenset({
    "browser.open_url",
    "browser.read_page",
    "browser.inspect_accessibility_tree",
    "browser.type",
    "browser.click",
})


@dataclass(frozen=True, slots=True)
class OwnerAcceptanceConfig:
    enabled: bool
    confirm_send: bool
    executable_path: str | None
    profile_root: str | None
    owner_id: str | None
    device_id: str | None
    url: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "OwnerAcceptanceConfig":
        values = os.environ if env is None else env
        return cls(
            enabled=values.get(OPT_IN_ENV) == "1",
            confirm_send=values.get(CONFIRM_ENV) == "1",
            executable_path=values.get(EXECUTABLE_ENV, "").strip() or None,
            profile_root=values.get(PROFILE_ENV, "").strip() or None,
            owner_id=values.get(OWNER_ID_ENV, "").strip() or None,
            device_id=values.get(DEVICE_ID_ENV, "").strip() or None,
            url=values.get(URL_ENV, "https://chatgpt.com/").strip(),
        )

    def safe_metadata(self) -> dict[str, object]:
        return {
            "owner_identity_configured": self.owner_id is not None,
            "device_configured": self.device_id is not None,
            "executable_configured": self.executable_path is not None,
            "dedicated_profile_configured": self.profile_root is not None,
            "send_confirmation_configured": self.confirm_send,
            "target_origin": _origin(self.url),
        }


def _origin(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if not parsed.scheme or not hostname:
        return None
    port = port or (443 if parsed.scheme.casefold() == "https" else 80)
    return f"{parsed.scheme.casefold()}://{hostname.casefold()}:{port}"


def _status(result: object) -> str:
    value = getattr(result, "status", "failed")
    return str(getattr(value, "value", value))


def _error(result: object) -> str | None:
    value = getattr(result, "error_code", None)
    return value if isinstance(value, str) else None


def _output(result: object) -> Mapping[str, object]:
    value = getattr(result, "output", {})
    return value if isinstance(value, Mapping) else {}


def _result(reason: str, config: OwnerAcceptanceConfig, *, status: str = PARTIAL, **extra: object) -> dict[str, object]:
    return {
        "schema": "phase18-b10-owner-browser-v1",
        "status": status,
        "reason": reason,
        "target_metadata": config.safe_metadata(),
        "security_counters": {
            "wrong_targets": 0,
            "duplicate_actions": 0,
            "unapproved_actions": 0,
            "credential_interactions": 0,
            "raw_secrets_persisted": 0,
            "raw_screenshots_persisted": 0,
            "prompt_injection_escalations": 0,
            "private_network_requests_allowed": 0,
            "normal_profile_touches": 0,
        },
        **extra,
    }


def _validate_config(config: OwnerAcceptanceConfig) -> str | None:
    if not config.enabled:
        return "owner_session_opt_in_required"
    if not all((config.executable_path, config.profile_root, config.owner_id, config.device_id)):
        return "owner_identity_browser_profile_configuration_required"
    try:
        validate_brave_executable_path(config.executable_path)
        BrowserProfilePolicy.validate_dedicated_profile_path(Path(config.profile_root))
    except (BrowserProfilePolicyError, ValueError, OSError) as exc:
        return str(exc) if isinstance(exc, BrowserProfilePolicyError) else "dedicated_brave_configuration_invalid"
    try:
        parsed = urlsplit(config.url)
        hostname = parsed.hostname
    except ValueError:
        return "chatgpt_exact_first_party_url_required"
    if parsed.scheme.casefold() != "https" or hostname is None or hostname.casefold() != "chatgpt.com" or parsed.username or parsed.password:
        return "chatgpt_exact_first_party_url_required"
    return None


async def _load_owner(runtime: object, config: OwnerAcceptanceConfig) -> tuple[Identity | None, DeviceIdentity | None, str | None]:
    repository = runtime.repository
    identity_row = repository.first_identity(config.owner_id or "")
    identity_id = identity_row.get("id") if isinstance(identity_row, Mapping) else None
    identity = await runtime.identity.get_identity(identity_id) if isinstance(identity_id, str) else None
    device = await runtime.identity.device(config.device_id or "")
    if identity is None or device is None:
        return None, None, "owner_identity_or_device_not_found"
    if identity.owner_id != config.owner_id or device.owner_id != config.owner_id:
        return None, None, "owner_identity_device_mismatch"
    missing = REQUIRED_CAPABILITIES - device.capabilities
    if missing:
        return None, None, "owner_device_browser_capability_missing"
    return identity, device, None


async def _execute(runtime: object, action: BrowserAction, identity: Identity, device: DeviceIdentity) -> BrowserResult:
    return await runtime.browser_actions.execute(
        action,
        identity,
        device,
        session_id="phase18-b10-owner-browser",
        correlation_id=f"phase18-b10-owner-browser-{uuid4().hex[:12]}",
        session_mode=BrowserSessionMode.OWNER_PERSISTENT,
    )


def _authenticated_shell(observation: Mapping[str, object]) -> tuple[bool, str]:
    tree = observation.get("accessibility_tree")
    elements = tree.get("elements", ()) if isinstance(tree, Mapping) else ()
    if not isinstance(elements, (list, tuple)):
        return False, "authenticated_shell_uncertain"
    material = " ".join(str(observation.get(key, "")) for key in ("title", "main_text", "text")).casefold()
    login_markers = ("log in", "sign up", "create account", "continue with google")
    if any(marker in material for marker in login_markers):
        return False, OWNER_LOGIN_REQUIRED
    composer_candidates = [
        item for item in elements
        if isinstance(item, Mapping)
        and str(item.get("role", "")) in {"textbox", "searchbox"}
        and any(term in str(item.get("accessible_name", "")).casefold() for term in ("message", "ask", "prompt", "chat"))
    ]
    if len(composer_candidates) == 1:
        return True, "authenticated_shell_ready"
    return False, "authenticated_shell_uncertain"


def _one_target(observation: Mapping[str, object], *, role: str, terms: tuple[str, ...]) -> str | None:
    tree = observation.get("accessibility_tree")
    elements = tree.get("elements", ()) if isinstance(tree, Mapping) else ()
    matches = [
        item for item in elements
        if isinstance(item, Mapping)
        and item.get("role") == role
        and any(term in str(item.get("accessible_name", "")).casefold() for term in terms)
        and isinstance(item.get("element_ref"), str)
    ]
    if len(matches) != 1:
        return None
    return str(matches[0]["element_ref"])


async def _observe(runtime: object, identity: Identity, device: DeviceIdentity, url: str) -> tuple[BrowserResult, BrowserResult]:
    session_id_result = await _execute(runtime, BrowserAction("open_url", {"url": url}), identity, device)
    session_id = _output(session_id_result).get("session_id")
    if _status(session_id_result) != "succeeded" or not isinstance(session_id, str):
        return session_id_result, session_id_result
    tree_result = await _execute(runtime, BrowserAction("inspect_accessibility_tree", {"session_id": session_id}), identity, device)
    return session_id_result, tree_result


async def run_acceptance(env: Mapping[str, str] | None = None) -> dict[str, object]:
    config = OwnerAcceptanceConfig.from_env(env)
    validation_error = _validate_config(config)
    if validation_error is not None:
        return _result(validation_error, config)
    assert config.executable_path is not None and config.profile_root is not None
    base = JarvisConfig.from_env()
    runtime_config = replace(
        base,
        browser_backend="playwright",
        browser_executable_path=config.executable_path,
        browser_profile_root=config.profile_root,
        browser_owner_persistent_opt_in=True,
        browser_headless=False,
    )
    runtime = create_runtime(runtime_config)
    first_session_id: str | None = None
    nonce = uuid4().hex
    try:
        await runtime.start()
        identity, device, owner_error = await _load_owner(runtime, config)
        if owner_error is not None or identity is None or device is None:
            return _result(owner_error or "owner_identity_unavailable", config)
        opened, tree = await _observe(runtime, identity, device, config.url)
        if _status(opened) != "succeeded":
            return _result(_error(opened) or "browser_open_failed", config)
        first_session_id = _output(opened).get("session_id") if isinstance(_output(opened).get("session_id"), str) else None
        if first_session_id is None or _status(tree) != "succeeded":
            return _result(_error(tree) or "browser_shell_observation_failed", config)
        authenticated, shell_reason = _authenticated_shell(_output(tree))
        if not authenticated:
            return _result(shell_reason, config, session_id_present=True)
        if not config.confirm_send:
            return _result("owner_send_confirmation_required", config, session_id_present=True)
        composer_ref = _one_target(_output(tree), role="textbox", terms=("message", "ask", "prompt", "chat"))
        send_ref = _one_target(_output(tree), role="button", terms=("send",))
        if composer_ref is None:
            return _result("composer_target_missing_or_ambiguous", config, session_id_present=True)
        if send_ref is None:
            return _result("send_target_missing_or_ambiguous", config, session_id_present=True)
        prompt = f"Reply with exactly: {nonce}"
        typed = await _execute(runtime, BrowserAction("type", {"session_id": first_session_id, "element_ref": composer_ref, "text": prompt}), identity, device)
        if _status(typed) != "approval_required" or not getattr(typed, "approval_id", None):
            return _result(_error(typed) or "composer_approval_not_created", config, session_id_present=True)
        typed_done = await runtime.browser_actions.decide(typed.approval_id, True, identity.identity_id)
        if _status(typed_done) != "succeeded":
            return _result(_error(typed_done) or "composer_type_failed", config, session_id_present=True)
        clicked = await _execute(runtime, BrowserAction("click", {"session_id": first_session_id, "element_ref": send_ref}), identity, device)
        if _status(clicked) != "approval_required" or not getattr(clicked, "approval_id", None):
            return _result(_error(clicked) or "send_approval_not_created", config, session_id_present=True)
        clicked_done = await runtime.browser_actions.decide(clicked.approval_id, True, identity.identity_id)
        if _status(clicked_done) != "succeeded":
            return _result(_error(clicked_done) or "send_failed", config, session_id_present=True)
        await asyncio.sleep(5.0)
        readback = await _execute(runtime, BrowserAction("read_page", {"session_id": first_session_id}), identity, device)
        material = str(_output(readback).get("main_text", ""))
        nonce_occurrences = material.count(nonce)
        if _status(readback) != "succeeded" or nonce_occurrences < 2:
            return _result("nonce_response_not_verified", config, session_id_present=True, nonce_sha256=hashlib.sha256(nonce.encode()).hexdigest(), nonce_occurrences=nonce_occurrences)
        await runtime.shutdown()
        runtime = create_runtime(runtime_config)
        await runtime.start()
        identity, device, owner_error = await _load_owner(runtime, config)
        if owner_error is not None or identity is None or device is None:
            return _result(owner_error or "owner_identity_unavailable_after_reopen", config, nonce_sha256=hashlib.sha256(nonce.encode()).hexdigest(), nonce_occurrences=nonce_occurrences)
        reopened, reopened_tree = await _observe(runtime, identity, device, config.url)
        reopened_auth, reopened_reason = _authenticated_shell(_output(reopened_tree)) if _status(reopened_tree) == "succeeded" else (False, "authenticated_shell_reopen_failed")
        if _status(reopened) != "succeeded" or not reopened_auth:
            return _result(reopened_reason, config, nonce_sha256=hashlib.sha256(nonce.encode()).hexdigest(), nonce_occurrences=nonce_occurrences)
        return _result(
            "authenticated_shell_nonce_and_persistence_verified",
            config,
            status=READY,
            nonce_sha256=hashlib.sha256(nonce.encode()).hexdigest(),
            nonce_occurrences=nonce_occurrences,
            persistence_verified=True,
        )
    except Exception:
        return _result("owner_browser_acceptance_failed", config)
    finally:
        if getattr(runtime, "state", None) is not None:
            await runtime.shutdown()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run_acceptance()), sort_keys=True))
