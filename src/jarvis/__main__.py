"""Run JARVIS locally without implicit model or network side effects."""

from __future__ import annotations

import asyncio
import argparse
import json
import os
from pathlib import Path
import re
import struct
import zlib

from .api.core import CoreApplication
from .api.http import CoreHttpServer
from .bootstrap import running_runtime
from .config import JarvisConfig
from .contracts import LLMInputMedia, LLMMessage, LLMRequest, LLMRole
from .models.routing import ModelRoute
from .models.probes import LocalModelCapabilityProbe
from .persistence.backup import SQLiteBackupService
from .persistence.db import SQLiteDatabase


def _cloud_key_store_action(provider: str, *, delete: bool = False) -> int:
    """Set/delete one cloud key through the existing current-user store.

    The value is read with a hidden prompt and is never accepted as a command
    argument, copied to ``os.environ``, or included in the result.
    """

    from getpass import getpass

    from .desktop.secret_store import SecretStoreUnavailable, cloud_secret_key, platform_secret_store

    try:
        key_name = cloud_secret_key(provider)
        store = platform_secret_store()
    except (OSError, SecretStoreUnavailable, ValueError):
        print(json.dumps({"provider": provider, "state": "unavailable"}, ensure_ascii=False))
        return 1

    if delete:
        try:
            store.delete(key_name)
        except (OSError, SecretStoreUnavailable):
            print(json.dumps({"provider": provider, "state": "unavailable"}, ensure_ascii=False))
            return 1
        print(json.dumps({"provider": provider, "state": "missing_key"}, ensure_ascii=False))
        return 0

    value = ""
    try:
        try:
            value = getpass(f"Enter {provider} API key (hidden): ").strip()
        except (EOFError, KeyboardInterrupt):
            print(json.dumps({"provider": provider, "state": "missing_key"}, ensure_ascii=False))
            return 1
        if not value:
            print(json.dumps({"provider": provider, "state": "missing_key"}, ensure_ascii=False))
            return 1
        store.set(key_name, value)
    except (OSError, SecretStoreUnavailable, ValueError):
        print(json.dumps({"provider": provider, "state": "unavailable"}, ensure_ascii=False))
        return 1
    finally:
        # This removes the Python reference; the platform store owns the
        # protected copy after a successful write.
        value = ""
    print(json.dumps({"provider": provider, "state": "configured"}, ensure_ascii=False))
    return 0


def _cloud_key_states() -> tuple[dict[str, str], int]:
    """Return product-safe cloud credential states without exposing values."""

    from .desktop.secret_store import SecretStoreUnavailable, cloud_provider_secret_states, platform_secret_store

    try:
        states = cloud_provider_secret_states(platform_secret_store())
    except (OSError, SecretStoreUnavailable):
        states = {"groq": "unavailable", "gemini": "unavailable"}
        return states, 1
    return states, 0


def _secure_provider_keys_for_runtime() -> dict[str, str] | None:
    """Prefer configured protected keys for a fresh normal CLI runtime.

    Returning ``None`` when the store has no cloud values preserves the
    process-only acceptance helper contract. Once either protected value is
    present, the complete mapping is supplied so missing entries cannot fall
    back to a stale environment value.
    """

    from .desktop.secret_store import SecretStoreUnavailable, platform_secret_store, read_cloud_provider_keys

    try:
        values = read_cloud_provider_keys(platform_secret_store())
    except (OSError, SecretStoreUnavailable):
        return None
    return values if any(values.values()) else None


def _normal_runtime_config() -> JarvisConfig:
    """Use the same persisted non-secret settings authority as the desktop."""

    from .desktop.config import resolve_runtime_config

    return resolve_runtime_config()


def _make_probe_png_fixture(size: int = 64) -> bytes:
    """Build a normal deterministic RGB PNG without reading owner media."""

    if not 16 <= size <= 256:
        raise ValueError("probe PNG size out of bounds")

    scanlines = bytearray()
    for y in range(size):
        scanlines.append(0)
        for x in range(size):
            checker = ((x // 8) + (y // 8)) % 2
            red, green, blue = ((32, 128, 240) if checker else (240, 128, 32))
            if abs(x - size // 2) < 2 or abs(y - size // 2) < 2:
                red, green, blue = (248, 248, 248)
            scanlines.extend((red, green, blue))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(scanlines), level=9)) + chunk(b"IEND", b"")


_PROBE_PNG_FIXTURE = _make_probe_png_fixture()


def _safe_probe_token(value: object, fallback: str = "unknown") -> str:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", value):
        return value
    return fallback


def _safe_response_summary(value: object) -> dict[str, object] | None:
    """Copy only the bounded Gemini structural fields allowed in probe output."""

    if not isinstance(value, dict):
        return None
    http_status = value.get("http_status")
    candidate_count = value.get("candidate_count")
    parts_count = value.get("parts_count")
    if not isinstance(http_status, int) or not 100 <= http_status <= 599:
        return None
    if candidate_count is not None and (not isinstance(candidate_count, int) or candidate_count < 0 or candidate_count > 64):
        return None
    if parts_count is not None and (not isinstance(parts_count, int) or parts_count < 0 or parts_count > 256):
        return None
    top_level_fields = value.get("top_level_fields", [])
    if not isinstance(top_level_fields, list):
        return None
    safe_top_level_fields = [_safe_probe_token(field) for field in top_level_fields[:32]]
    if "unknown" in safe_top_level_fields:
        return None
    part_field_names = value.get("part_field_names", [])
    if not isinstance(part_field_names, list):
        return None
    safe_part_field_names: list[list[str]] = []
    for names in part_field_names[:32]:
        if not isinstance(names, list):
            return None
        safe_names = [_safe_probe_token(name) for name in names[:16]]
        if "unknown" in safe_names:
            return None
        safe_part_field_names.append(safe_names)
    usage = value.get("usageMetadata", {})
    if not isinstance(usage, dict):
        return None
    safe_usage: dict[str, int] = {}
    for key in ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount", "totalTokenCount"):
        token_count = usage.get(key)
        if token_count is not None:
            if not isinstance(token_count, int) or isinstance(token_count, bool) or not 0 <= token_count <= 1_000_000_000:
                return None
            safe_usage[key] = token_count
    prompt_feedback = value.get("promptFeedback", {})
    if not isinstance(prompt_feedback, dict):
        return None
    safe_prompt_feedback: dict[str, str] = {}
    if "blockReason" in prompt_feedback:
        block_reason = _safe_probe_token(prompt_feedback.get("blockReason"))
        if block_reason != "unknown":
            safe_prompt_feedback["blockReason"] = block_reason
    finish_reason = value.get("finish_reason")
    return {
        "http_status": http_status,
        "top_level_fields": safe_top_level_fields,
        "candidate_count": candidate_count,
        "finish_reason": _safe_probe_token(finish_reason) if finish_reason is not None else None,
        "content_exists": bool(value.get("content_exists", False)),
        "parts_count": parts_count,
        "part_field_names": safe_part_field_names,
        "usageMetadata": safe_usage,
        "promptFeedback": safe_prompt_feedback,
    }


def _safe_credential_status(value: object, *, environment_name: str) -> dict[str, object]:
    """Expose only presence/length/prefix metadata for a process-only key."""

    source = value if isinstance(value, dict) else {}
    present = source.get("present")
    length = source.get("length")
    prefix_valid = source.get("prefix_valid")
    if not isinstance(present, bool) or not isinstance(length, int) or not 0 <= length <= 4096 or not isinstance(prefix_valid, bool):
        secret = os.getenv(environment_name, "")
        prefix_pattern = r"gsk_[A-Za-z0-9_-]{16,}" if environment_name == "GROQ_API_KEY" else r"AIza[A-Za-z0-9_-]{16,}"
        return {
            "present": bool(secret),
            "length": min(len(secret), 4096),
            "prefix_valid": bool(re.fullmatch(prefix_pattern, secret)),
        }
    return {"present": present, "length": length, "prefix_valid": prefix_valid}


def _runtime_source_identity() -> dict[str, str]:
    """Identify the actual repo modules used by a provider probe, without secrets."""

    import jarvis as jarvis_package
    from .models import cloud as cloud_module

    def resolved_file(value: object) -> str:
        candidate = getattr(value, "__file__", None)
        if not isinstance(candidate, str) or not candidate:
            return "unknown"
        return str(Path(candidate).resolve())[:512]

    return {
        "jarvis_package_file": resolved_file(jarvis_package),
        "cloud_module_file": resolved_file(cloud_module),
        "probe_implementation_file": str(Path(__file__).resolve())[:512],
    }


def _safe_request_trace(value: object) -> list[dict[str, object]]:
    """Expose only bounded URL/method/header-presence facts from a provider trace."""

    if not isinstance(value, list):
        return []
    safe_trace: list[dict[str, object]] = []
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        method = item.get("method")
        phase = item.get("phase")
        accept_header = item.get("accept_header")
        user_agent = item.get("user_agent")
        key_length = item.get("key_length")
        timeout_seconds = item.get("timeout_seconds")
        if (
            not isinstance(url, str)
            or len(url) > 512
            or url not in {
                "https://api.groq.com/openai/v1/models",
                "https://api.groq.com/openai/v1/chat/completions",
            }
            or not isinstance(method, str)
            or not re.fullmatch(r"[A-Z]{3,8}", method)
            or not isinstance(phase, str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", phase)
            or not isinstance(accept_header, str)
            or len(accept_header) > 64
            or user_agent != "JARVIS/1.0"
            or not isinstance(key_length, int)
            or not 0 <= key_length <= 4096
            or not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not 0 < float(timeout_seconds) <= 180
        ):
            continue
        authorization_present = item.get("authorization_present")
        content_type_present = item.get("content_type_present")
        prefix_valid = item.get("prefix_valid")
        if not all(isinstance(flag, bool) for flag in (authorization_present, content_type_present, prefix_valid)):
            continue
        safe_trace.append({
            "phase": phase,
            "url": url,
            "method": method,
            "authorization_present": authorization_present,
            "accept_header": accept_header,
            "user_agent": user_agent,
            "content_type_present": content_type_present,
            "key_length": key_length,
            "prefix_valid": prefix_valid,
            "timeout_seconds": float(timeout_seconds),
        })
    return safe_trace


def _safe_groq_diagnostic(value: object) -> dict[str, object] | None:
    """Expose only the bounded Groq HTTP/body classification fields."""

    if not isinstance(value, dict):
        return None
    http_status = value.get("http_status")
    classification = value.get("classification")
    error_type = value.get("error_type")
    error_code = value.get("error_code")
    reason = value.get("reason")
    body_contains_1010 = value.get("body_contains_1010")
    body_contains_browser_signature_banned = value.get("body_contains_browser_signature_banned")
    response_format = value.get("response_format")
    if (
        not isinstance(http_status, int)
        or not 100 <= http_status <= 599
        or not isinstance(classification, str)
        or _safe_probe_token(classification) == "unknown"
        or not isinstance(reason, str)
        or _safe_probe_token(reason) == "unknown"
        or (error_type is not None and _safe_probe_token(error_type) == "unknown")
        or (error_code is not None and _safe_probe_token(error_code) == "unknown")
        or not isinstance(body_contains_1010, bool)
        or not isinstance(body_contains_browser_signature_banned, bool)
        or response_format not in {"groq_json", "cloudflare_html_or_text", "other_json", "text_or_non_json", "unknown"}
    ):
        return None
    return {
        "http_status": http_status,
        "classification": _safe_probe_token(classification),
        "error_type": _safe_probe_token(error_type) if error_type is not None else None,
        "error_code": _safe_probe_token(error_code) if error_code is not None else None,
        "reason": _safe_probe_token(reason),
        "body_contains_1010": body_contains_1010,
        "body_contains_browser_signature_banned": body_contains_browser_signature_banned,
        "response_format": response_format,
    }


def _safe_provider_failure(exc: Exception) -> dict[str, object]:
    """Return only typed, bounded provider metadata; never exception text."""

    summary = _safe_response_summary(getattr(exc, "summary", None))
    diagnostic = getattr(exc, "diagnostic", None)
    as_dict = getattr(diagnostic, "as_dict", None)
    if not callable(as_dict):
        reason = getattr(exc, "reason", None)
        failure: dict[str, object] = {"error": _safe_probe_token(reason, exc.__class__.__name__)}
        if summary is not None:
            failure["response_summary"] = summary
        return failure
    values = as_dict()
    if not isinstance(values, dict):
        return {"error": exc.__class__.__name__}
    if "error_type" in values or "error_code" in values:
        error_type = values.get("error_type")
        error_code = values.get("error_code")
        reason = values.get("reason")
        classification = values.get("classification")
        http_status = values.get("http_status")
        body_contains_1010 = values.get("body_contains_1010", False)
        body_contains_browser_signature_banned = values.get("body_contains_browser_signature_banned", False)
        response_format = values.get("response_format", "unknown")
        if (
            (error_type is not None and _safe_probe_token(error_type) == "unknown")
            or (error_code is not None and _safe_probe_token(error_code) == "unknown")
            or _safe_probe_token(reason) == "unknown"
            or _safe_probe_token(classification) == "unknown"
            or not isinstance(http_status, int)
            or not 100 <= http_status <= 599
            or not isinstance(body_contains_1010, bool)
            or not isinstance(body_contains_browser_signature_banned, bool)
            or response_format not in {"groq_json", "cloudflare_html_or_text", "other_json", "text_or_non_json", "unknown"}
        ):
            failure = {"error": exc.__class__.__name__}
            if summary is not None:
                failure["response_summary"] = summary
            return failure
        failure = {
            "error": _safe_probe_token(reason),
            "diagnostic": {
                "http_status": http_status,
                "classification": _safe_probe_token(classification),
                "error_type": _safe_probe_token(error_type) if error_type is not None else None,
                "error_code": _safe_probe_token(error_code) if error_code is not None else None,
                "reason": _safe_probe_token(reason),
                "body_contains_1010": body_contains_1010,
                "body_contains_browser_signature_banned": body_contains_browser_signature_banned,
                "response_format": response_format,
            },
        }
        if summary is not None:
            failure["response_summary"] = summary
        return failure
    status = values.get("google_status")
    reason = values.get("reason")
    classification = values.get("classification")
    http_status = values.get("http_status")
    google_code = values.get("google_code")
    if (
        (status is not None and _safe_probe_token(status) == "unknown")
        or _safe_probe_token(reason) == "unknown"
        or _safe_probe_token(classification) == "unknown"
        or not isinstance(http_status, int)
        or not 100 <= http_status <= 599
        or (google_code is not None and (not isinstance(google_code, int) or not 100 <= google_code <= 599))
    ):
        failure = {"error": exc.__class__.__name__}
        if summary is not None:
            failure["response_summary"] = summary
        return failure
    failure = {
        "error": _safe_probe_token(reason),
        "diagnostic": {
            "http_status": http_status,
            "google_code": google_code,
            "google_status": status,
            "classification": _safe_probe_token(classification),
            "reason": _safe_probe_token(reason),
        },
    }
    if summary is not None:
        failure["response_summary"] = summary
    return failure


def _probe_owner_action_required(reason: str) -> bool:
    return reason.startswith((
        "gemini_http_400_failed_prerequisite",
        "gemini_http_401_authentication_failure",
        "gemini_http_403_permission_failure",
        "gemini_http_404_model_or_resource_unavailable",
        "gemini_http_429_rate_limit_or_quota",
    ))


async def _run_provider_probe(runtime: object, provider_name: str) -> dict[str, object]:
    """Run one explicit cloud-provider acceptance call without exposing secrets."""

    routes = {"groq": ModelRoute.GENERAL_REASONING, "gemini": ModelRoute.VISION}
    if provider_name not in routes:
        raise ValueError("model provider probe must be groq or gemini")
    route = routes[provider_name]
    models = runtime.models
    selection = models.selection(route)
    architecture = models.architecture_snapshot()
    state = architecture.get(provider_name)
    state = state if isinstance(state, dict) else {}
    result: dict[str, object] = {
        "provider": provider_name,
        "model": selection.model,
        "state": state.get("state", "unknown"),
        "health_reason": state.get("reason", "provider_state_unavailable"),
        "generation_checked": False,
        "fallback_used": False,
        "result": "NOT_RUN",
        "source_identity": _runtime_source_identity(),
        "request_trace": [],
    }
    environment_name = "GROQ_API_KEY" if provider_name == "groq" else "GEMINI_API_KEY"
    credential_getter = getattr(models, "provider_credential_status", None)
    credential_status = None
    if callable(credential_getter):
        try:
            credential_status = credential_getter(provider_name)
        except Exception:
            credential_status = None
    result["credential"] = _safe_credential_status(credential_status, environment_name=environment_name)
    # Missing/disabled credentials are an owner boundary, not a provider call.
    if state.get("state") not in {"configured", "configured_unprobed"}:
        result["result"] = "OWNER_ACTION_REQUIRED" if state.get("state") == "missing_key" else "NOT_RUN"
        return result

    reset_trace = getattr(models, "reset_provider_request_trace", None)
    if callable(reset_trace):
        try:
            reset_trace(provider_name)
        except Exception:
            pass

    def attach_request_trace() -> None:
        trace_getter = getattr(models, "provider_request_trace", None)
        if callable(trace_getter):
            try:
                result["request_trace"] = _safe_request_trace(trace_getter(provider_name))
            except Exception:
                result["request_trace"] = []

    def attach_http_diagnostic(target: dict[str, object]) -> None:
        if provider_name != "groq":
            return
        diagnostic_getter = getattr(models, "provider_http_diagnostic", None)
        if callable(diagnostic_getter):
            try:
                diagnostic = _safe_groq_diagnostic(diagnostic_getter(provider_name))
            except Exception:
                diagnostic = None
            if diagnostic is not None:
                target["diagnostic"] = diagnostic

    if provider_name == "gemini":
        try:
            model_access = await models.health(route)
        except Exception as exc:
            result["model_access"] = {"result": "FAIL", "error": exc.__class__.__name__}
            attach_request_trace()
            result["result"] = "FAIL"
            return result
        access_reason = _safe_probe_token(getattr(model_access, "reason", None), "provider_health_failed")
        access_provider = _safe_probe_token(getattr(model_access, "provider", None))
        access_model = _safe_probe_token(getattr(model_access, "model", None))
        access_passed = bool(
            getattr(model_access, "available", False)
            and access_provider == provider_name
            and access_model == selection.model
        )
        result["health_reason"] = access_reason
        result["model_access"] = {
            "result": "PASS" if access_passed else "FAIL",
            "provider": access_provider,
            "model": access_model,
            "available": bool(getattr(model_access, "available", False)),
            "reason": access_reason,
        }
        if not access_passed:
            attach_request_trace()
            result["error"] = access_reason
            result["result"] = "OWNER_ACCOUNT_ACTION_REQUIRED" if _probe_owner_action_required(access_reason) else "FAIL"
            return result

        async def run_gemini_stage(request: LLMRequest) -> tuple[dict[str, object], LLMResponse | None]:
            try:
                response = await models.generate_direct(provider_name, request, route)
            except Exception as exc:
                return {"result": "FAIL", **_safe_provider_failure(exc)}, None
            actual_provider = _safe_probe_token(response.provider)
            actual_model = _safe_probe_token(response.model)
            nonempty = bool(isinstance(response.text, str) and response.text.strip()) or bool(response.tool_calls)
            passed = actual_provider == provider_name and actual_model == selection.model and nonempty
            stage = {
                "result": "PASS" if passed else "FAIL",
                "provider": actual_provider,
                "model": actual_model,
                "finish_reason": _safe_probe_token(response.finish_reason),
                "nonempty": nonempty,
                "fallback_used": actual_provider != provider_name,
            }
            summary_getter = getattr(models, "provider_response_summary", None)
            if callable(summary_getter):
                summary = _safe_response_summary(summary_getter(provider_name))
                if summary is not None:
                    stage["response_summary"] = summary
            if not passed:
                stage["error"] = "provider_model_or_content_mismatch"
            return stage, response

        text_request = LLMRequest(
            "model-provider-probe-gemini-text",
            (LLMMessage(LLMRole.USER, "Reply with one short word: READY."),),
            model=selection.model,
            max_output_tokens=256,
            timeout_seconds=20,
            provider_options={"gemini_thinking_level": "minimal"},
        )
        text_stage, text_response = await run_gemini_stage(text_request)
        result["text_generation"] = text_stage
        result["generation_checked"] = True
        if text_response is None or text_stage["result"] != "PASS":
            attach_request_trace()
            result.update({"result": "FAIL", **{key: value for key, value in text_stage.items() if key in {"error", "diagnostic"}}})
            return result

        vision_request = LLMRequest(
            "model-provider-probe-gemini-vision",
            (LLMMessage(
                LLMRole.USER,
                "Inspect this generated JARVIS fixture and reply with one short phrase.",
                (LLMInputMedia("image/png", _PROBE_PNG_FIXTURE),),
            ),),
            model=selection.model,
            max_output_tokens=256,
            timeout_seconds=20,
            provider_options={"gemini_thinking_level": "minimal"},
        )
        vision_stage, vision_response = await run_gemini_stage(vision_request)
        result["vision_generation"] = vision_stage
        if vision_response is None or vision_stage["result"] != "PASS":
            attach_request_trace()
            result.update({"result": "FAIL", **{key: value for key, value in vision_stage.items() if key in {"error", "diagnostic"}}})
            return result
        result.update({
            "actual_provider": vision_stage["provider"],
            "actual_model": vision_stage["model"],
            "fallback_used": bool(text_stage.get("fallback_used") or vision_stage.get("fallback_used")),
            "finish_reason": vision_stage["finish_reason"],
            "nonempty": bool(vision_stage["nonempty"]),
            "result": "PASS",
        })
        attach_request_trace()
        return result

    try:
        model_access = await models.health(route)
    except Exception as exc:
        result["model_access"] = {"result": "FAIL", **_safe_provider_failure(exc)}
        attach_request_trace()
        result["result"] = "FAIL"
        return result
    access_reason = _safe_probe_token(getattr(model_access, "reason", None), "provider_health_failed")
    access_provider = _safe_probe_token(getattr(model_access, "provider", None))
    access_model = _safe_probe_token(getattr(model_access, "model", None))
    access_passed = bool(
        getattr(model_access, "available", False)
        and access_provider == provider_name
        and access_model == selection.model
        and access_reason == "groq_ready"
    )
    result["health_reason"] = access_reason
    result["model_access"] = {
        "result": "PASS" if access_passed else "FAIL",
        "provider": access_provider,
        "model": access_model,
        "available": bool(getattr(model_access, "available", False)),
        "reason": access_reason,
    }
    attach_http_diagnostic(result["model_access"])
    if not access_passed:
        attach_request_trace()
        result["error"] = access_reason
        result["result"] = "FAIL"
        return result

    request = LLMRequest(
        "model-provider-probe-groq",
        (LLMMessage(LLMRole.USER, "Reply with one short sentence confirming a bounded reasoning probe."),),
        model=selection.model,
        max_output_tokens=64,
        timeout_seconds=20,
    )
    try:
        response = await models.generate_direct(provider_name, request, route)
    except Exception as exc:  # Do not print provider exception text or headers.
        stage = {
            "result": "FAIL",
            **_safe_provider_failure(exc),
        }
        result["text_generation"] = stage
        result.update({
            "generation_checked": True,
            "result": "FAIL",
            **{key: value for key, value in stage.items() if key in {"error", "diagnostic"}},
        })
        attach_request_trace()
        return result
    actual_provider = _safe_probe_token(response.provider)
    actual_model = _safe_probe_token(response.model)
    nonempty = bool(response.text.strip() or response.tool_calls)
    passed = actual_provider == provider_name and actual_model == selection.model and nonempty
    stage = {
        "result": "PASS" if passed else "FAIL",
        "provider": actual_provider,
        "model": actual_model,
        "fallback_used": actual_provider != provider_name,
        "finish_reason": _safe_probe_token(response.finish_reason),
        "nonempty": nonempty,
    }
    if not passed:
        stage["error"] = "provider_model_or_content_mismatch"
    result["text_generation"] = stage
    result.update({
        "generation_checked": True,
        "actual_provider": actual_provider,
        "actual_model": actual_model,
        "fallback_used": actual_provider != provider_name,
        "finish_reason": _safe_probe_token(response.finish_reason),
        "nonempty": nonempty,
        "result": "PASS" if passed else "FAIL",
    })
    if not passed:
        result["error"] = "provider_model_or_content_mismatch"
    attach_request_trace()
    return result


async def _main(args: argparse.Namespace) -> None:
    config = _normal_runtime_config()
    async with running_runtime(config, provider_api_keys=_secure_provider_keys_for_runtime()) as runtime:
        application = CoreApplication(runtime)
        print(f"JARVIS runtime ready: {runtime.runtime_id}")
        if args.text is not None:
            principal = await application.ensure_demo_principal()
            result = await application.send_message(args.text, principal.identity, principal.device)
            print(json.dumps(result, ensure_ascii=False))
        if args.model_smoke:
            if runtime.config.model_provider not in {"ollama", "gguf", "llama_cpp", "hybrid"}:
                print("MODEL SMOKE: NOT RUN (set an explicit local or hybrid model provider)")
            else:
                health = await runtime.models.health(ModelRoute.FAST_CONVERSATION)
                if not health.available:
                    print(f"MODEL SMOKE: NOT RUN ({health.reason})")
                else:
                    request = LLMRequest(
                        "cli-model-smoke",
                        (LLMMessage(LLMRole.USER, "Reply with the single word ready."),),
                        max_output_tokens=16,
                        timeout_seconds=10,
                    )
                    response = await runtime.models.generate(request, ModelRoute.FAST_CONVERSATION)
                    print(f"MODEL SMOKE: PASS ({response.model})")
        if args.model_probe:
            result = await LocalModelCapabilityProbe(runtime.models).run(
                ModelRoute.FAST_CONVERSATION,
                exercise_generation=args.model_exercise,
            )
            print(json.dumps(result.as_dict(), ensure_ascii=False))
        if args.model_architecture:
            print(json.dumps(runtime.models.architecture_snapshot(), ensure_ascii=False))
        if args.model_provider_probe:
            result = await _run_provider_probe(runtime, args.model_provider_probe)
            print(json.dumps(result, ensure_ascii=False))
        if args.status:
            print(json.dumps({
                "runtime": runtime.state.value,
                "database": runtime.config.database_path,
                "model_provider": runtime.config.model_provider,
                "model_primary": runtime.config.primary_model,
                "offline": runtime.offline.state.online is False,
                "event_count": runtime.repository.event_count(),
            }, ensure_ascii=False))
        node_server = None
        if args.serve_node:
            from .api.node_http import CoreNodeHttpServer
            node_server = CoreNodeHttpServer(
                application,
                host=args.node_host,
                port=args.node_port,
                allow_wildcard_bind=args.allow_wildcard_node_bind,
            )
            node_server.start()
            print(f"JARVIS Node HTTP adapter listening on http://{node_server.host}:{node_server.port}")

        try:
            if args.serve:
                server = CoreHttpServer(application, port=args.port)
                print(f"JARVIS HTTP API listening on http://127.0.0.1:{server.address[1]}")
                try:
                    await asyncio.to_thread(server.serve_forever)
                finally:
                    server.shutdown()
            elif args.serve_node:
                stop_event = asyncio.Event()
                await stop_event.wait()
        finally:
            if node_server is not None:
                node_server.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local JARVIS core runtime")
    parser.add_argument("--text", help="send one text message through the full runtime")
    parser.add_argument("--model-smoke", action="store_true", help="probe an already-running loopback model provider")
    parser.add_argument("--model-probe", action="store_true", help="inspect model health/capabilities without downloading")
    parser.add_argument("--model-exercise", action="store_true", help="send one bounded generation during --model-probe")
    parser.add_argument("--model-architecture", action="store_true", help="print the safe three-model architecture snapshot")
    parser.add_argument("--model-provider-probe", choices=("groq", "gemini"), help="run one explicit live provider acceptance call")
    parser.add_argument("--set-cloud-key", choices=("groq", "gemini"), help="store one cloud key using a hidden prompt")
    parser.add_argument("--delete-cloud-key", choices=("groq", "gemini"), help="delete one cloud key from the secure store")
    parser.add_argument("--cloud-key-status", action="store_true", help="show safe cloud key configured/missing states")
    parser.add_argument("--status", action="store_true", help="print runtime status")
    parser.add_argument("--serve", action="store_true", help="serve the loopback HTTP API")
    parser.add_argument("--port", type=int, default=8787, help="loopback HTTP port")
    parser.add_argument("--serve-node", action="store_true", help="serve the minimal authenticated node HTTP adapter")
    parser.add_argument("--node-host", default=os.getenv("JARVIS_NODE_HOST", "127.0.0.1"), help="node HTTP adapter bind host (default: 127.0.0.1)")
    parser.add_argument("--node-port", type=int, default=int(os.getenv("JARVIS_NODE_PORT", "8788")), help="node HTTP adapter bind port (default: 8788)")
    parser.add_argument("--allow-wildcard-node-bind", action="store_true", default=os.getenv("JARVIS_ALLOW_WILDCARD_NODE_BIND", "false").lower() in {"true", "1", "yes", "on"}, help="explicit opt-in to allow 0.0.0.0 or :: wildcard bind on node server")
    parser.add_argument("--backup", metavar="PATH", help="create an explicit SQLite backup")
    parser.add_argument("--verify-backup", metavar="PATH", help="verify an SQLite backup")
    parser.add_argument("--restore-backup", metavar="SOURCE", help="restore SOURCE to --restore-target")
    parser.add_argument("--restore-target", metavar="PATH", help="destination used with --restore-backup")
    parser.add_argument("--overwrite-restore", action="store_true", help="allow an explicit existing restore destination")
    args = parser.parse_args()
    cloud_actions = [bool(args.set_cloud_key), bool(args.delete_cloud_key), bool(args.cloud_key_status)]
    if sum(cloud_actions) > 1:
        parser.error("--set-cloud-key, --delete-cloud-key, and --cloud-key-status are mutually exclusive")
    maintenance = [bool(args.backup), bool(args.verify_backup), bool(args.restore_backup)]
    if any(cloud_actions) and any(maintenance):
        parser.error("cloud key actions cannot be combined with backup actions")
    if sum(maintenance) > 1:
        parser.error("--backup, --verify-backup, and --restore-backup are mutually exclusive")
    if args.restore_target and not args.restore_backup:
        parser.error("--restore-target requires --restore-backup")
    if args.overwrite_restore and not args.restore_backup:
        parser.error("--overwrite-restore requires --restore-backup")
    if args.set_cloud_key:
        raise SystemExit(_cloud_key_store_action(args.set_cloud_key))
    if args.delete_cloud_key:
        raise SystemExit(_cloud_key_store_action(args.delete_cloud_key, delete=True))
    if args.cloud_key_status:
        states, exit_code = _cloud_key_states()
        print(json.dumps(states, ensure_ascii=False, sort_keys=True))
        raise SystemExit(exit_code)
    if args.backup or args.verify_backup or args.restore_backup:
        config = JarvisConfig.from_env()
        if args.backup:
            source = Path(config.database_path).expanduser().resolve(strict=True)
            database = SQLiteDatabase(str(source))
            try:
                print(json.dumps(SQLiteBackupService(database).create(args.backup), ensure_ascii=False))
            finally:
                database.close()
        elif args.verify_backup:
            print(json.dumps(SQLiteBackupService.verify(args.verify_backup), ensure_ascii=False))
        else:
            if not args.restore_target:
                parser.error("--restore-backup requires --restore-target")
            print(json.dumps(SQLiteBackupService.restore(args.restore_backup, args.restore_target, overwrite=args.overwrite_restore), ensure_ascii=False))
        return
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
