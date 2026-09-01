"""One fail-closed URL policy for every product-owned browser path."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from ipaddress import IPv4Address, IPv6Address
from urllib.parse import urlsplit


class BrowserURLPolicyError(ValueError):
    """A browser URL or redirect failed the product boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


Resolver = Callable[[str, int], Iterable[str | IPv4Address | IPv6Address]]


class BrowserURLPolicy:
    """Validate schemes, authority, and resolved destinations before I/O."""

    MAX_REDIRECTS = 5
    _ALLOWED_SCHEMES = frozenset({"http", "https"})

    def __init__(self, resolver: Resolver | None = None) -> None:
        self._resolver = resolver or self._resolve

    def validate(self, value: str, *, resolve_dns: bool = True) -> str:
        if not isinstance(value, str) or not value or len(value) > 4_096 or "\x00" in value:
            raise BrowserURLPolicyError("url_invalid")
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise BrowserURLPolicyError("url_invalid") from exc
        if parsed.scheme.casefold() not in self._ALLOWED_SCHEMES:
            raise BrowserURLPolicyError("url_scheme_not_allowed")
        if parsed.username is not None or parsed.password is not None:
            raise BrowserURLPolicyError("url_userinfo_not_allowed")
        if not hostname:
            raise BrowserURLPolicyError("url_host_required")
        normalized_host = hostname.rstrip(".").casefold()
        if normalized_host == "localhost" or normalized_host.endswith(".localhost"):
            raise BrowserURLPolicyError("url_localhost_not_allowed")
        if port is not None and not 1 <= port <= 65_535:
            raise BrowserURLPolicyError("url_port_not_allowed")
        if self._unsafe_address(hostname):
            raise BrowserURLPolicyError("url_destination_not_allowed")
        if resolve_dns:
            try:
                addresses = tuple(self._resolver(hostname, port or 80))
            except (OSError, socket.gaierror, ValueError) as exc:
                raise BrowserURLPolicyError("url_dns_resolution_failed") from exc
            if not addresses or any(self._unsafe_address(address) for address in addresses):
                raise BrowserURLPolicyError("url_destination_not_allowed")
        return value

    @staticmethod
    def _resolve(hostname: str, port: int) -> tuple[str, ...]:
        return tuple({str(item[4][0]) for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)})

    @staticmethod
    def _unsafe_address(value: str | IPv4Address | IPv6Address) -> bool:
        try:
            address = value if isinstance(value, (IPv4Address, IPv6Address)) else ipaddress.ip_address(value)
        except ValueError:
            return False
        return not address.is_global or address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified
