"""Validation utilities for private Core LAN URLs and network endpoints."""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

_HOSTNAME_PATTERN = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*$")

_ALLOWED_IPV4_PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
)

_ALLOWED_IPV6_PRIVATE_NETWORKS = (
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)

MAX_TRUSTED_LAN_CIDRS = 8
MAX_TRUSTED_LAN_CIDR_LENGTH = 64
PRIVATE = "PRIVATE"
EXPLICIT_LOCAL_TRUST_OVERRIDE = "EXPLICIT_LOCAL_TRUST_OVERRIDE"
LOOPBACK = "LOOPBACK"
BLOCKED = "BLOCKED"
_NETWORK_MODES = frozenset({"live-distributed", "local", "test"})


class NetworkValidationError(ValueError):
    """Raised when a Core or node network URL fails private LAN validation."""


def validate_trusted_lan_cidrs(trusted_lan_cidrs: Sequence[str] | None = ()) -> tuple[str, ...]:
    """Validate bounded, explicit local-network overrides and normalize them."""

    if trusted_lan_cidrs is None:
        return ()
    if isinstance(trusted_lan_cidrs, (str, bytes)):
        raise NetworkValidationError("trusted_lan_cidrs_must_be_a_sequence")
    values = tuple(trusted_lan_cidrs)
    if len(values) > MAX_TRUSTED_LAN_CIDRS:
        raise NetworkValidationError("too_many_trusted_lan_cidrs")
    normalized: list[str] = []
    networks: set[ipaddress.IPv4Network | ipaddress.IPv6Network] = set()
    for raw in values:
        if not isinstance(raw, str) or not raw.strip() or len(raw.strip()) > MAX_TRUSTED_LAN_CIDR_LENGTH:
            raise NetworkValidationError("invalid_trusted_lan_cidr")
        try:
            network = ipaddress.ip_network(raw.strip(), strict=False)
        except ValueError as exc:
            raise NetworkValidationError("invalid_trusted_lan_cidr") from exc
        if network.prefixlen == 0 or network.is_unspecified or network.is_multicast:
            raise NetworkValidationError("dangerous_trusted_lan_cidr")
        loopback_network = ipaddress.ip_network("127.0.0.0/8" if network.version == 4 else "::1/128")
        if network.overlaps(loopback_network):
            raise NetworkValidationError("loopback_trusted_lan_cidr_forbidden")
        if network in networks:
            continue
        networks.add(network)
        normalized.append(str(network))
    return tuple(normalized)


def classify_ip(ip_str: str, trusted_lan_cidrs: Sequence[str] | None = ()) -> str:
    """Classify an address under the default policy plus explicit local overrides."""

    networks = tuple(ipaddress.ip_network(cidr) for cidr in validate_trusted_lan_cidrs(trusted_lan_cidrs))
    try:
        address = ipaddress.ip_address(ip_str)
    except ValueError:
        return BLOCKED
    if address.is_loopback:
        return LOOPBACK
    if address.version == 4 and any(address in network for network in _ALLOWED_IPV4_PRIVATE_NETWORKS):
        return PRIVATE
    if address.version == 6 and any(address in network for network in _ALLOWED_IPV6_PRIVATE_NETWORKS):
        return PRIVATE
    if any(address in network for network in networks):
        return EXPLICIT_LOCAL_TRUST_OVERRIDE
    return BLOCKED


def trusted_network_mode(trusted_lan_cidrs: Sequence[str] | None = ()) -> str:
    """Return a safe diagnostic label without exposing the configured addresses."""

    return EXPLICIT_LOCAL_TRUST_OVERRIDE if validate_trusted_lan_cidrs(trusted_lan_cidrs) else "DEFAULT_PRIVATE_LAN"


def validate_bind_host(
    host: str,
    trusted_lan_cidrs: Sequence[str] | None = (),
    *,
    allow_wildcard: bool = False,
) -> None:
    """Validate a node listener host under the shared trust policy."""

    if host in {"0.0.0.0", "::", ""}:
        if not allow_wildcard:
            raise NetworkValidationError("wildcard_bind_requires_explicit_opt_in")
        return
    if host in {"localhost", "localhost.localdomain"} or classify_ip(host, trusted_lan_cidrs) == LOOPBACK:
        return
    if classify_ip(host, trusted_lan_cidrs) in {PRIVATE, EXPLICIT_LOCAL_TRUST_OVERRIDE}:
        return
    raise NetworkValidationError(f"public_or_invalid_bind_host:{host}")


def _default_resolve(hostname: str) -> list[str]:
    try:
        info = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        return [item[4][0] for item in info]
    except Exception as exc:
        raise NetworkValidationError(f"hostname_resolution_failed:{exc}") from exc


def validate_private_core_url(
    url: str,
    mode: str = "live-distributed",
    resolver: Callable[[str], Sequence[str]] | None = None,
    trusted_lan_cidrs: Sequence[str] | None = (),
) -> str:
    """Validate that a Core URL points to an authorized private LAN origin.

    In live-distributed mode:
    - Rejects public IP addresses.
    - Rejects loopback addresses (127.0.0.1, ::1, localhost) to prevent false distributed testing.
    - Rejects URL credentials/userinfo.
    - Rejects unexpected query parameters or fragments.
    - Resolves hostnames explicitly and accepts only when all resolved addresses
      fall strictly within supported private/local ranges.

    In local / test mode:
    - Permits loopback addresses (127.0.0.1, ::1, localhost).
    - Still rejects public IPs and URL credentials.
    """
    if mode not in _NETWORK_MODES:
        raise NetworkValidationError("unsupported_network_mode")
    trusted_networks = validate_trusted_lan_cidrs(trusted_lan_cidrs)
    if not isinstance(url, str) or not url.strip():
        raise NetworkValidationError("core_url_empty")

    cleaned = url.strip()
    try:
        parsed = urlsplit(cleaned)
    except Exception as exc:
        raise NetworkValidationError(f"invalid_url_format:{exc}") from exc

    if parsed.scheme not in {"http", "https"}:
        raise NetworkValidationError("invalid_scheme_must_be_http_or_https")

    if parsed.username or parsed.password or "@" in parsed.netloc:
        raise NetworkValidationError("url_credentials_userinfo_forbidden")

    if parsed.query:
        raise NetworkValidationError("url_query_parameters_forbidden")

    if parsed.fragment:
        raise NetworkValidationError("url_fragment_forbidden")

    if parsed.path not in {"", "/"}:
        raise NetworkValidationError("unexpected_url_path")

    hostname = parsed.hostname
    if not hostname:
        raise NetworkValidationError("missing_hostname")

    port = parsed.port
    if port is not None and not (1 <= port <= 65535):
        raise NetworkValidationError("invalid_port_number")

    # Check if host is an IP address
    is_ip = False
    try:
        ip_obj = ipaddress.ip_address(hostname)
        is_ip = True
    except ValueError:
        pass

    if is_ip:
        if ip_obj.is_loopback:
            if mode == "live-distributed":
                raise NetworkValidationError("loopback_address_forbidden_in_live_distributed_mode")
            # Allowed in local/test mode
        elif classify_ip(hostname, trusted_networks) == BLOCKED:
            if ip_obj.version == 4:
                raise NetworkValidationError("public_or_unauthorized_ipv4_forbidden")
            if ip_obj.version == 6:
                raise NetworkValidationError("public_or_unauthorized_ipv6_forbidden")
    else:
        # Hostname check
        lower_host = hostname.casefold()
        if lower_host in {"localhost", "localhost.localdomain"}:
            if mode == "live-distributed":
                raise NetworkValidationError("localhost_forbidden_in_live_distributed_mode")
        elif not _HOSTNAME_PATTERN.match(hostname):
            raise NetworkValidationError("invalid_hostname_format")
        else:
            # Safe DNS proof check
            resolve_fn = resolver or _default_resolve
            try:
                resolved_ips = list(resolve_fn(hostname))
            except NetworkValidationError:
                raise
            except Exception as exc:
                raise NetworkValidationError(f"hostname_resolution_failed:{exc}") from exc

            if not resolved_ips:
                raise NetworkValidationError("hostname_resolved_to_no_addresses")

            for ip_str in resolved_ips:
                try:
                    res_ip = ipaddress.ip_address(ip_str)
                except ValueError as exc:
                    raise NetworkValidationError(f"invalid_resolved_ip:{ip_str}") from exc

                if res_ip.is_loopback:
                    if mode == "live-distributed":
                        raise NetworkValidationError("hostname_resolves_to_loopback_in_live_distributed_mode")
                elif classify_ip(ip_str, trusted_networks) == BLOCKED:
                    raise NetworkValidationError(f"hostname_resolves_to_public_ip:{ip_str}")

    port_str = f":{port}" if port is not None else ""
    return f"{parsed.scheme}://{hostname}{port_str}"


def is_private_ip(ip_str: str, trusted_lan_cidrs: Sequence[str] | None = ()) -> bool:
    """Check if an IP string is an RFC1918, link-local, or private IPv6 address."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    return classify_ip(str(ip), trusted_lan_cidrs) != BLOCKED
