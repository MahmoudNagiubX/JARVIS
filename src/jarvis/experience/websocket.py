"""Minimal authenticated WebSocket framing for the local experience stream."""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from collections.abc import Mapping


WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def accept_key(client_key: str) -> str:
    if not client_key.strip():
        raise ValueError("Sec-WebSocket-Key is required")
    try:
        decoded = base64.b64decode(client_key, validate=True)
    except Exception as exc:
        raise ValueError("invalid Sec-WebSocket-Key") from exc
    if len(decoded) != 16:
        raise ValueError("invalid Sec-WebSocket-Key length")
    return base64.b64encode(hashlib.sha1((client_key + WEBSOCKET_GUID).encode("ascii")).digest()).decode("ascii")


def text_frame(payload: Mapping[str, object] | str) -> bytes:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    data = text.encode("utf-8")
    length = len(data)
    if length < 126:
        header = bytes((0x81, length))
    elif length < 65_536:
        header = bytes((0x81, 126)) + struct.pack("!H", length)
    else:
        header = bytes((0x81, 127)) + struct.pack("!Q", length)
    return header + data


def ping_frame() -> bytes:
    return b"\x89\x00"


def close_frame() -> bytes:
    return b"\x88\x00"
