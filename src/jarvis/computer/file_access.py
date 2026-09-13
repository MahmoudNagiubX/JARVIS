"""Product-owned, fail-closed approved-root file access policy (GAP-0503).

Subordinate to `PolicyPermissionEngine` - this is not a second permission
authority. It answers exactly one question for every concrete path a
computer file action (`inspect_file`/`search_files`/`open_file`/
`open_folder`) is about to touch:

    is this path within an owner-approved root, not a sensitive path,
    and not an escape (symlink/junction/`..`) outside that root?

With no configured roots, every path-requiring operation is denied
(`file_root_not_configured`) - an intentional security tightening, never a
silent fallback to unrestricted access.
"""

from __future__ import annotations

import fnmatch
import os
import stat as _stat
from dataclasses import dataclass, field
from pathlib import Path

MAX_ROOTS = 20
MAX_SEARCH_MATCHES = 100
MAX_SEARCH_CANDIDATES_SCANNED = 5_000
# R18B03-001: bounded traversal depth for the pre-descent search walker -
# defense in depth alongside the bounded canonical-directory visited set,
# even though a normal (non-reparse) directory tree cannot be cyclic.
MAX_SEARCH_DEPTH = 32

# Credential/key-store directory names, denied wherever they appear as a
# path component - defense in depth even nested under an approved root.
_SENSITIVE_DIR_NAMES = frozenset({".ssh", ".gnupg", ".aws", ".azure", ".kube"})

# Exact (casefolded) filenames that are always sensitive, aside from the
# broader ".env"/".env.*" family handled separately below (R18B03-002) -
# ".env.example" is deliberately excluded there, it is a safe template.
_SENSITIVE_FILE_NAMES = frozenset({"login data", "cookies", "web data"})
_ENV_SAFE_TEMPLATE_NAME = ".env.example"
_SENSITIVE_FILE_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".ppk")
_SENSITIVE_FILE_STEMS = frozenset({"id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"})
# Path substrings (already casefolded, backslash-normalized) recognizable as
# OS credential/security stores.
_SENSITIVE_PATH_SUBSTRINGS = (
    "\\windows\\system32\\config\\",
    "\\microsoft\\credentials\\",
    "\\microsoft\\protect\\",
    "\\microsoft\\crypto\\",
)

# Root-level environment variables that must never themselves be *approved
# as a root* - each names a location broad enough that approving it defeats
# confinement entirely (Section 8.2 of the Batch 03 task).
_FORBIDDEN_ROOT_ENV_VARS = ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "WINDIR", "SYSTEMROOT", "PROGRAMFILES", "PROGRAMFILES(X86)")
_FORBIDDEN_ROOT_DIRECT_CHILD_NAMES = frozenset({"windows", "programdata", "program files", "program files (x86)", "users"})


@dataclass(frozen=True, slots=True)
class FileAccessDecision:
    allowed: bool
    reason_code: str | None = None
    resolved_path: Path | None = None


def _is_forbidden_root(path: Path) -> bool:
    """A configured root may not itself be an entire drive, the user's home
    directory, or one of the other classic overly-broad system locations -
    approving any of these would defeat root confinement (Section 8.2)."""
    if path.parent == path:  # a bare drive root, e.g. C:\
        return True
    try:
        if path == Path.home().resolve():
            return True
    except OSError:
        pass
    if len(path.parts) == 2 and path.parts[-1].casefold() in _FORBIDDEN_ROOT_DIRECT_CHILD_NAMES:
        return True
    for env_var in _FORBIDDEN_ROOT_ENV_VARS:
        value = os.environ.get(env_var)
        if not value:
            continue
        try:
            if path == Path(value).resolve():
                return True
        except OSError:
            continue
    return False


def _is_env_secret_name(name_casefold: str) -> bool:
    """True for ``.env`` and the ``.env.*`` family (R18B03-002), except the
    explicitly-safe template ``.env.example``. Matches on the literal ``.env``
    stem followed by nothing or a ``.`` separator only, so ``.environment``
    (no separator after the ``.env`` prefix) is never caught by this rule."""
    if name_casefold == _ENV_SAFE_TEMPLATE_NAME:
        return False
    return name_casefold == ".env" or name_casefold.startswith(".env.")


def _is_reparse_point(path: Path) -> bool:
    """True for a symlink OR a Windows junction/other reparse point,
    classified WITHOUT following it (`os.lstat`). Empirically verified: a
    real `mklink /J` junction sets `FILE_ATTRIBUTE_REPARSE_POINT` on
    `st_file_attributes` even though `Path.is_symlink()` reports False for
    it - so the attribute bit, not `is_symlink()` alone, is the correct
    pre-descent classifier on Windows. Fails closed (treated as a reparse
    point, therefore never descended) if the entry cannot be classified at
    all, and falls back to `is_symlink()` where `st_file_attributes` is
    unavailable (non-Windows)."""
    try:
        st = os.lstat(path)
    except OSError:
        return True
    attrs = getattr(st, "st_file_attributes", None)
    if attrs is not None:
        return bool(attrs & _stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return path.is_symlink()


def _is_sensitive(path: Path) -> bool:
    parts_casefold = {part.casefold() for part in path.parts}
    if parts_casefold & _SENSITIVE_DIR_NAMES:
        return True
    name_casefold = path.name.casefold()
    if name_casefold in _SENSITIVE_FILE_NAMES:
        return True
    if _is_env_secret_name(name_casefold):
        return True
    if name_casefold.endswith(_SENSITIVE_FILE_SUFFIXES):
        return True
    if path.stem.casefold() in _SENSITIVE_FILE_STEMS:
        return True
    path_casefold = str(path).casefold()
    return any(substring in path_casefold for substring in _SENSITIVE_PATH_SUBSTRINGS)


@dataclass(slots=True)
class FileAccessPolicy:
    roots: tuple[Path, ...] = field(default_factory=tuple)

    @classmethod
    def from_config_roots(cls, raw_roots: tuple[str, ...]) -> "FileAccessPolicy":
        normalized: list[Path] = []
        seen: set[str] = set()
        for raw in raw_roots:
            if not isinstance(raw, str) or not raw.strip():
                continue
            try:
                resolved = Path(raw).expanduser().resolve()
            except OSError:
                continue
            key = str(resolved).casefold()
            if key in seen:
                continue
            if _is_forbidden_root(resolved):
                continue
            if not resolved.is_dir():
                continue
            seen.add(key)
            normalized.append(resolved)
            if len(normalized) >= MAX_ROOTS:
                break
        return cls(tuple(normalized))

    def configured(self) -> bool:
        return bool(self.roots)

    def status(self) -> dict[str, object]:
        """Bounded, model-safe status - never the actual root strings."""
        return {"configured": self.configured(), "root_count": len(self.roots)}

    def _containing_root(self, resolved: Path) -> Path | None:
        for root in self.roots:
            try:
                resolved.relative_to(root)
                return root
            except ValueError:
                continue
        return None

    def evaluate(self, raw_path: str) -> FileAccessDecision:
        if not self.roots:
            return FileAccessDecision(False, "file_root_not_configured")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return FileAccessDecision(False, "file_path_escape_denied")
        try:
            # Path.resolve() on Windows follows symlinks/junctions to their
            # real target (via GetFinalPathNameByHandleW when the path
            # exists) - a path that physically resolves outside an approved
            # root is denied below regardless of how it was reached.
            resolved = Path(raw_path).expanduser().resolve()
        except OSError:
            return FileAccessDecision(False, "file_path_escape_denied")
        if self._containing_root(resolved) is None:
            return FileAccessDecision(False, "file_path_outside_allowed_root")
        if _is_sensitive(resolved):
            return FileAccessDecision(False, "file_sensitive_path_denied")
        return FileAccessDecision(True, None, resolved)

    def evaluate_search_root(self, raw_root: str) -> FileAccessDecision:
        decision = self.evaluate(raw_root)
        if not decision.allowed:
            return decision
        assert decision.resolved_path is not None
        if not decision.resolved_path.is_dir():
            return FileAccessDecision(False, "file_path_outside_allowed_root")
        return decision

    def iter_search_candidates(self, root: Path, pattern: str) -> tuple[list[str], int]:
        """Pre-descent bounded walker (R18B03-001, streamed per R18B04-001).

        Unlike the original `Path.rglob()` + post-hoc-filter approach, this
        decides containment and reparse-safety BEFORE descending into each
        directory, and never materializes an unbounded candidate list first:
        candidate-scan and result-count bounds are enforced live, directly
        against the `os.scandir()` iterator for the current directory - not
        against a list built from it. The budget is checked BEFORE each
        `next()` call, so once `MAX_SEARCH_CANDIDATES_SCANNED` is reached the
        walker never requests another directory entry at all, from this
        directory or any other still on the stack, even if the current
        directory itself contains far more entries than the budget (R18B04-001
        - an independent-review finding against the Batch 04 version, which
        called `list(os.scandir(current))` and could still enumerate an
        arbitrarily large single directory before the budget was enforced).

        Default reparse policy: directory symlinks/junctions/reparse points
        are never followed during generic search at all (deliberately
        stricter than "follow if still inside root" - simpler, deterministic,
        avoids cycles/mount ambiguity entirely). A file symlink is only
        returned if its final resolved target is still inside `root`, is
        genuinely a file, and passes the sensitivity policy.

        Direct `inspect_file`/`open_file`/`open_folder` confinement (via
        `evaluate()`) is untouched by this method - it still resolves and
        checks the real target directly, unaffected by search-only policy.
        """
        matches: list[str] = []
        filtered = 0
        scanned = 0
        visited: set[str] = set()
        stack: list[tuple[Path, int]] = [(root, 0)]
        while stack:
            current, depth = stack.pop()
            current_key = str(current).casefold()
            if current_key in visited:
                continue
            visited.add(current_key)
            try:
                scandir_iterator = os.scandir(current)
            except OSError:
                continue
            with scandir_iterator:
                while True:
                    if len(matches) >= MAX_SEARCH_MATCHES:
                        return matches, filtered
                    if scanned >= MAX_SEARCH_CANDIDATES_SCANNED:
                        return matches, filtered
                    try:
                        entry = next(scandir_iterator)
                    except StopIteration:
                        break
                    scanned += 1
                    entry_path = Path(entry.path)
                    try:
                        is_dir_no_follow = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    reparse = _is_reparse_point(entry_path)
                    if reparse:
                        if is_dir_no_follow:
                            # Directory-shaped reparse point (junction or
                            # directory symlink) - never descended.
                            filtered += 1
                            continue
                        # File symlink - only usable if its resolved target
                        # stays inside root, is a real file, and is not
                        # sensitive; never trusted from the unresolved name
                        # alone.
                        try:
                            resolved_file = entry_path.resolve()
                        except OSError:
                            filtered += 1
                            continue
                        try:
                            resolved_file.relative_to(root)
                        except ValueError:
                            filtered += 1
                            continue
                        if not resolved_file.is_file():
                            filtered += 1
                            continue
                        if not fnmatch.fnmatch(entry.name.casefold(), pattern.casefold()):
                            continue
                        if _is_sensitive(resolved_file):
                            filtered += 1
                            continue
                        matches.append(str(resolved_file))
                        continue
                    if is_dir_no_follow:
                        if depth + 1 > MAX_SEARCH_DEPTH:
                            filtered += 1
                            continue
                        if entry.name.casefold() in _SENSITIVE_DIR_NAMES:
                            # Prune the entire sensitive subtree - never
                            # descended, so no hidden child can appear later.
                            filtered += 1
                            continue
                        try:
                            canonical_dir = entry_path.resolve()
                        except OSError:
                            continue
                        try:
                            canonical_dir.relative_to(root)
                        except ValueError:
                            # Would escape the approved root - fail closed,
                            # never descended.
                            filtered += 1
                            continue
                        stack.append((canonical_dir, depth + 1))
                        continue
                    # Plain file, no reparse involved.
                    if not fnmatch.fnmatch(entry.name.casefold(), pattern.casefold()):
                        continue
                    if _is_sensitive(entry_path):
                        filtered += 1
                        continue
                    matches.append(str(entry_path))
        return matches, filtered
