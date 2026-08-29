"""Shared redaction helpers for logs and transport-facing diagnostics."""

from __future__ import annotations

from collections.abc import Mapping


SENSITIVE_KEYS = frozenset({
    "authorization", "api_key", "credential", "password", "raw_audio",
    "raw_frame", "secret", "token", "webhook", "cookie",
})


def redact(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): "[redacted]" if str(key).casefold() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value
