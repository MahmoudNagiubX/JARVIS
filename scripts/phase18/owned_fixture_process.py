"""Bounded process boundary for Phase 18 owned physical fixtures.

This development-only helper is intentionally narrower than a general
process launcher. It accepts only the four repository-owned Win32 fixture
hosts, invokes them with the current Python interpreter, and cleans up only
the exact ``Popen`` object returned by the launch.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parent
ALLOWED_FIXTURE_NAMES = frozenset({
    "uia_fixture_host.py",
    "uia_text_fixture_host.py",
    "uia_ocr_fixture_host.py",
    "uia_recovery_fixture_host.py",
})
POSITIONED_FIXTURE_NAMES = frozenset({
    "uia_fixture_host.py",
    "uia_text_fixture_host.py",
    "uia_ocr_fixture_host.py",
})
STDIN_PIPE_FIXTURE_NAMES = frozenset({"uia_recovery_fixture_host.py"})


class OwnedFixtureError(ValueError):
    """Raised when a physical fixture request leaves the owned boundary."""


def resolve_owned_fixture(script_path: str | Path) -> Path:
    """Resolve and validate one allowlisted fixture script.

    Path containment is component-wise, after canonicalization. The
    explicit filename allowlist prevents an arbitrary script placed beside
    the fixtures from becoming a physical target.
    """
    candidate = Path(script_path).resolve(strict=False)
    root = FIXTURE_ROOT.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise OwnedFixtureError("fixture_path_outside_phase18") from exc
    if candidate.parent != root or candidate.name not in ALLOWED_FIXTURE_NAMES:
        raise OwnedFixtureError("fixture_path_not_allowlisted")
    if not candidate.is_file():
        raise OwnedFixtureError("fixture_path_missing")
    return candidate


def launch_owned_fixture(
    script_path: str | Path,
    *,
    nonce: str,
    x: int | None = None,
    y: int | None = None,
    stdin_pipe: bool = False,
) -> subprocess.Popen:
    """Launch an allowlisted fixture with bounded, typed arguments only."""
    script = resolve_owned_fixture(script_path)
    try:
        normalized_nonce = str(uuid.UUID(nonce))
    except (AttributeError, TypeError, ValueError) as exc:
        raise OwnedFixtureError("fixture_nonce_must_be_uuid") from exc
    if (x is None) != (y is None):
        raise OwnedFixtureError("fixture_position_requires_x_and_y")
    if x is not None and (type(x) is not int or type(y) is not int):
        raise OwnedFixtureError("fixture_position_must_be_integer")
    if x is not None and script.name not in POSITIONED_FIXTURE_NAMES:
        raise OwnedFixtureError("fixture_position_not_supported")
    if stdin_pipe and script.name not in STDIN_PIPE_FIXTURE_NAMES:
        raise OwnedFixtureError("fixture_stdin_pipe_not_supported")

    argv = [sys.executable, str(script), "--nonce", normalized_nonce]
    if x is not None and y is not None:
        argv.extend(("--x", str(x), "--y", str(y)))
    return subprocess.Popen(
        argv,
        stdin=subprocess.PIPE if stdin_pipe else subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        text=stdin_pipe,
    )


def terminate_owned_fixture(proc: subprocess.Popen, *, timeout: float = 5.0) -> bool:
    """Terminate exactly ``proc`` and use its exact-PID kill fallback.

    ``Popen`` methods operate on the child object returned by this module;
    there is deliberately no image-name lookup or broad process termination.
    """
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=timeout)
    return proc.poll() is not None
