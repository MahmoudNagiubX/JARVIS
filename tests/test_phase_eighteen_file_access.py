"""Milestone 1 (Phase 18 Workstream A, Batch 03): GAP-0503 approved-root
file access confinement.

Covers `FileAccessPolicy` directly (root confinement, prefix-confusion
resistance, symlink/junction escape resistance, sensitive-path denial) and
its integration into the real `ComputerActionService` ->
`WindowsNativeComputerController` path for `inspect_file`/`search_files`/
`open_file`/`open_folder` - all using only temporary directories this test
creates and cleans up itself, never owner files.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jarvis.computer.file_access import FileAccessPolicy


def _make_junction(link: Path, target: Path) -> bool:
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True, text=True, check=False,
    )
    return result.returncode == 0 and link.exists()


class FileAccessPolicyRootConfinementTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="jarvis_fa_")
        self.tmp = Path(self._tmp.name)
        self.allowed = self.tmp / "Data"
        self.allowed.mkdir()
        self.sibling = self.tmp / "Database"
        self.sibling.mkdir()
        (self.allowed / "normal.txt").write_text("hello", encoding="utf-8")
        sub = self.allowed / "sub"
        sub.mkdir()
        (sub / "note.txt").write_text("hello", encoding="utf-8")
        (self.sibling / "file.txt").write_text("hello", encoding="utf-8")
        self.policy = FileAccessPolicy.from_config_roots((str(self.allowed),))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_file_inside_allowed_root_is_allowed(self) -> None:
        decision = self.policy.evaluate(str(self.allowed / "normal.txt"))
        self.assertTrue(decision.allowed)

    def test_folder_inside_allowed_root_is_allowed(self) -> None:
        decision = self.policy.evaluate(str(self.allowed / "sub"))
        self.assertTrue(decision.allowed)

    def test_sibling_prefix_confusion_is_denied(self) -> None:
        # "Database" must never be treated as inside "Data" via a naive
        # string-prefix check.
        decision = self.policy.evaluate(str(self.sibling / "file.txt"))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "file_path_outside_allowed_root")

    def test_dotdot_traversal_denied_after_resolve(self) -> None:
        decision = self.policy.evaluate(str(self.allowed / ".." / "Database" / "file.txt"))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "file_path_outside_allowed_root")

    def test_absolute_path_outside_root_denied(self) -> None:
        decision = self.policy.evaluate(str(self.tmp / "elsewhere.txt"))
        self.assertFalse(decision.allowed)

    def test_no_roots_configured_denies_fail_closed(self) -> None:
        policy = FileAccessPolicy()
        decision = policy.evaluate(str(self.allowed / "normal.txt"))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "file_root_not_configured")

    def test_duplicate_root_normalization(self) -> None:
        policy = FileAccessPolicy.from_config_roots((str(self.allowed), str(self.allowed) + "\\", str(self.allowed)))
        self.assertEqual(len(policy.roots), 1)

    def test_forbidden_broad_roots_rejected(self) -> None:
        policy = FileAccessPolicy.from_config_roots(("C:\\", str(Path.home())))
        self.assertEqual(policy.roots, ())


class FileAccessPolicyLinkEscapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="jarvis_fa_link_")
        self.tmp = Path(self._tmp.name)
        self.allowed = self.tmp / "Data"
        self.allowed.mkdir()
        self.outside = self.tmp / "Outside"
        self.outside.mkdir()
        (self.outside / "secret.txt").write_text("nope", encoding="utf-8")
        self.link = self.allowed / "escape_link"
        self.have_junction = _make_junction(self.link, self.outside)
        self.policy = FileAccessPolicy.from_config_roots((str(self.allowed),))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_junction_escape_target_is_denied(self) -> None:
        if not self.have_junction:
            self.skipTest("directory junction creation unavailable in this environment")
        decision = self.policy.evaluate(str(self.link / "secret.txt"))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "file_path_outside_allowed_root")

    def test_search_does_not_follow_escape_link(self) -> None:
        # R18B03-001 req #1: a junction whose target is outside the approved
        # root is never traversed by the pre-descent walker.
        if not self.have_junction:
            self.skipTest("directory junction creation unavailable in this environment")
        matches, _filtered = self.policy.iter_search_candidates(self.allowed, "*")
        self.assertFalse(any("secret.txt" in m for m in matches))

    def test_walker_never_yields_external_secret_even_transiently(self) -> None:
        # R18B03-001 req #2: the external secret must never appear even as a
        # transient candidate - the walker must never descend into the
        # junction at all, so nothing beyond it can ever be scanned.
        if not self.have_junction:
            self.skipTest("directory junction creation unavailable in this environment")
        matches, filtered = self.policy.iter_search_candidates(self.allowed, "*")
        self.assertFalse(any("Outside" in m or "secret" in m.casefold() for m in matches))
        self.assertGreaterEqual(filtered, 1)

    def test_junction_directory_inside_root_is_not_descended(self) -> None:
        # R18B03-001 req #3: even a reparse point whose target is INSIDE the
        # approved root is never descended - the default policy refuses to
        # follow directory symlinks/junctions/reparse points at all.
        real_inside = self.allowed / "real_inside"
        real_inside.mkdir()
        (real_inside / "reachable_directly.txt").write_text("hi", encoding="utf-8")
        junction_inside = self.allowed / "junction_to_inside"
        if not _make_junction(junction_inside, real_inside):
            self.skipTest("directory junction creation unavailable in this environment")
        matches, filtered = self.policy.iter_search_candidates(self.allowed, "*")
        self.assertTrue(any("reachable_directly.txt" in m for m in matches))
        self.assertFalse(any("junction_to_inside" in m and "reachable_directly.txt" in m for m in matches))
        self.assertGreaterEqual(filtered, 1)

    def test_cycle_cannot_cause_unbounded_walk(self) -> None:
        # R18B03-001 req #4: a junction that would create a directory cycle
        # (pointing back to an ancestor) must not be followed, so the walker
        # terminates normally instead of looping.
        sub = self.allowed / "sub_for_cycle"
        sub.mkdir()
        cyclic_junction = sub / "back_to_root"
        if not _make_junction(cyclic_junction, self.allowed):
            self.skipTest("directory junction creation unavailable in this environment")
        matches, filtered = self.policy.iter_search_candidates(self.allowed, "*")
        self.assertGreaterEqual(filtered, 1)
        self.assertLess(len(matches), 1000)


class FileAccessPolicySensitivePathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="jarvis_fa_sensitive_")
        self.tmp = Path(self._tmp.name)
        self.allowed = self.tmp / "Data"
        self.allowed.mkdir()
        self.policy = FileAccessPolicy.from_config_roots((str(self.allowed),))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, relative: str, content: str = "x") -> Path:
        path = self.allowed / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_ssh_private_key_denied(self) -> None:
        path = self._write(".ssh/id_rsa")
        decision = self.policy.evaluate(str(path))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "file_sensitive_path_denied")

    def test_env_file_denied(self) -> None:
        path = self._write(".env")
        decision = self.policy.evaluate(str(path))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "file_sensitive_path_denied")

    def test_env_example_is_allowed(self) -> None:
        path = self._write(".env.example")
        decision = self.policy.evaluate(str(path))
        self.assertTrue(decision.allowed)

    def test_env_staging_denied(self) -> None:
        path = self._write(".env.staging")
        decision = self.policy.evaluate(str(path))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "file_sensitive_path_denied")

    def test_env_development_local_denied(self) -> None:
        path = self._write(".env.development.local")
        decision = self.policy.evaluate(str(path))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "file_sensitive_path_denied")

    def test_env_production_local_denied(self) -> None:
        path = self._write(".env.production.local")
        decision = self.policy.evaluate(str(path))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "file_sensitive_path_denied")

    def test_env_test_local_denied(self) -> None:
        path = self._write(".env.test.local")
        decision = self.policy.evaluate(str(path))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "file_sensitive_path_denied")

    def test_dot_environment_unaffected_by_env_wildcard_rule(self) -> None:
        # ".environment" must not be caught by the ".env"/".env.*" rule - the
        # match is on the literal ".env" stem followed by nothing or a "."
        # separator, never a bare prefix-of-name substring match.
        path = self._write(".environment")
        decision = self.policy.evaluate(str(path))
        self.assertTrue(decision.allowed)

    def test_browser_login_data_denied(self) -> None:
        path = self._write("Login Data")
        decision = self.policy.evaluate(str(path))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "file_sensitive_path_denied")

    def test_normal_source_files_allowed(self) -> None:
        for name in ("main.py", "notes.txt"):
            path = self._write(name)
            decision = self.policy.evaluate(str(path))
            self.assertTrue(decision.allowed, name)

    def test_sensitive_child_omitted_from_search_with_filtered_count(self) -> None:
        self._write("normal.txt")
        self._write(".env")
        matches, filtered = self.policy.iter_search_candidates(self.allowed, "*")
        self.assertTrue(any("normal.txt" in m for m in matches))
        self.assertFalse(any(".env" in m for m in matches))
        self.assertGreaterEqual(filtered, 1)

    def test_sensitive_subtree_is_pruned(self) -> None:
        # R18B03-001 req #7/#8: an entire sensitive directory (e.g. .ssh) is
        # never descended, so no child inside it - hidden or not - can ever
        # appear in the output, and it is never even scanned entry-by-entry.
        self._write("normal.txt")
        self._write(".ssh/id_rsa")
        self._write(".ssh/hidden_secret_child.txt")
        matches, filtered = self.policy.iter_search_candidates(self.allowed, "*")
        self.assertTrue(any("normal.txt" in m for m in matches))
        self.assertFalse(any("id_rsa" in m for m in matches))
        self.assertFalse(any("hidden_secret_child" in m for m in matches))
        self.assertGreaterEqual(filtered, 1)

    def test_normal_nested_search_still_succeeds(self) -> None:
        self._write("top.txt")
        self._write("a/b/c/deep.txt")
        matches, _filtered = self.policy.iter_search_candidates(self.allowed, "*")
        self.assertTrue(any("top.txt" in m for m in matches))
        self.assertTrue(any("deep.txt" in m for m in matches))


class FileAccessPolicySearchBoundsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="jarvis_fa_bounds_")
        self.tmp = Path(self._tmp.name)
        self.allowed = self.tmp / "Data"
        self.allowed.mkdir()
        for index in range(10):
            (self.allowed / f"file_{index}.txt").write_text("x", encoding="utf-8")
        self.policy = FileAccessPolicy.from_config_roots((str(self.allowed),))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_scan_count_bound_is_enforced(self) -> None:
        # R18B03-001 req #5: bounds are enforced live during traversal, never
        # after an unbounded candidate list is built first.
        from jarvis.computer import file_access as file_access_module

        original = file_access_module.MAX_SEARCH_CANDIDATES_SCANNED
        file_access_module.MAX_SEARCH_CANDIDATES_SCANNED = 3
        try:
            matches, _filtered = self.policy.iter_search_candidates(self.allowed, "*")
            self.assertLessEqual(len(matches), 3)
        finally:
            file_access_module.MAX_SEARCH_CANDIDATES_SCANNED = original

    def test_result_count_bound_is_enforced(self) -> None:
        # R18B03-001 req #6.
        from jarvis.computer import file_access as file_access_module

        original = file_access_module.MAX_SEARCH_MATCHES
        file_access_module.MAX_SEARCH_MATCHES = 2
        try:
            matches, _filtered = self.policy.iter_search_candidates(self.allowed, "*")
            self.assertEqual(len(matches), 2)
        finally:
            file_access_module.MAX_SEARCH_MATCHES = original


class FileAccessServiceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Through the actual JARVIS ComputerActionService -> controller path,
    per Section 8.12 - a temporary directory is the one explicit approved
    root; never owner files."""

    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="jarvis_fa_integration_")
        self.tmp = Path(self._tmp.name)
        self.allowed = self.tmp / "allowed"
        self.allowed.mkdir()
        (self.allowed / "normal.txt").write_text("hello world", encoding="utf-8")
        sub = self.allowed / "sub"
        sub.mkdir()
        (sub / "note.txt").write_text("nested", encoding="utf-8")
        (self.allowed / ".env").write_text("SECRET=1", encoding="utf-8")
        self.outside = self.tmp / "outside"
        self.outside.mkdir()
        (self.outside / "outside.txt").write_text("owner-adjacent but not approved", encoding="utf-8")

        from jarvis.authority.identity.service import EnrollmentGrant
        from jarvis.bootstrap import create_runtime
        from jarvis.config import JarvisConfig

        self.runtime = create_runtime(JarvisConfig(
            environment="test", database_path=":memory:", file_access_roots=(str(self.allowed),),
        ))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("File Access Owner")
        enrollment = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                self.identity.owner_id, "File Access Device", "desktop", "windows",
                ("tool.request",), ("computer.observe", "computer.input"),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(enrollment.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()
        self._tmp.cleanup()

    async def test_inspect_normal_file_succeeds(self) -> None:
        from jarvis.contracts import ComputerAction

        result = await self.runtime.computer_actions.execute(
            ComputerAction("inspect_file", {"path": str(self.allowed / "normal.txt")}, False), self.identity, self.device,
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.output["content"], "hello world")

    async def test_search_normal_succeeds_and_excludes_env(self) -> None:
        from jarvis.contracts import ComputerAction

        result = await self.runtime.computer_actions.execute(
            ComputerAction("search_files", {"root": str(self.allowed), "pattern": "*"}, False), self.identity, self.device,
        )
        self.assertEqual(result.status, "succeeded")
        matches = result.output["matches"]
        self.assertTrue(any("normal.txt" in m for m in matches))
        self.assertTrue(any("note.txt" in m for m in matches))
        self.assertFalse(any(".env" in m for m in matches))
        self.assertGreaterEqual(result.output["filtered_count"], 1)

    async def test_inspect_env_denied(self) -> None:
        from jarvis.contracts import ComputerAction

        result = await self.runtime.computer_actions.execute(
            ComputerAction("inspect_file", {"path": str(self.allowed / ".env")}, False), self.identity, self.device,
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "file_sensitive_path_denied")

    async def test_inspect_outside_root_denied(self) -> None:
        from jarvis.contracts import ComputerAction

        result = await self.runtime.computer_actions.execute(
            ComputerAction("inspect_file", {"path": str(self.outside / "outside.txt")}, False), self.identity, self.device,
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "file_path_outside_allowed_root")

    async def test_search_outside_root_denied(self) -> None:
        from jarvis.contracts import ComputerAction

        result = await self.runtime.computer_actions.execute(
            ComputerAction("search_files", {"root": str(self.outside)}, False), self.identity, self.device,
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "file_path_outside_allowed_root")

    async def test_open_file_uses_policy_and_denies_outside_root(self) -> None:
        from jarvis.contracts import ComputerAction

        result = await self.runtime.computer_actions.execute(
            ComputerAction("open_file", {"path": str(self.outside / "outside.txt")}, False), self.identity, self.device,
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "file_path_outside_allowed_root")

    async def test_open_folder_uses_policy_and_denies_outside_root(self) -> None:
        from jarvis.contracts import ComputerAction

        result = await self.runtime.computer_actions.execute(
            ComputerAction("open_folder", {"path": str(self.outside)}, False), self.identity, self.device,
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "file_path_outside_allowed_root")

    async def test_canonical_audit_still_recorded_for_denied_file_action(self) -> None:
        from jarvis.contracts import ComputerAction, ToolContext

        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        correlation = "file-access-audit-correlation"
        await self.runtime.computer_actions.execute(
            ComputerAction("inspect_file", {"path": str(self.outside / "outside.txt")}, False),
            self.identity, self.device, session_id=session.id, correlation_id=correlation,
        )
        audited = {row["event_type"] for row in self.runtime.repository.audit(correlation)}
        self.assertIn("computer.permission_checked", audited)

    async def test_link_escape_denied_through_real_service_path(self) -> None:
        from jarvis.contracts import ComputerAction

        link = self.allowed / "escape_link"
        if not _make_junction(link, self.outside):
            self.skipTest("directory junction creation unavailable in this environment")
        result = await self.runtime.computer_actions.execute(
            ComputerAction("inspect_file", {"path": str(link / "outside.txt")}, False), self.identity, self.device,
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "file_path_outside_allowed_root")

    async def test_no_roots_configured_denies_every_path_action(self) -> None:
        from jarvis.authority.identity.service import EnrollmentGrant
        from jarvis.bootstrap import create_runtime
        from jarvis.config import JarvisConfig
        from jarvis.contracts import ComputerAction

        runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await runtime.start()
        try:
            identity = await runtime.identity.bootstrap_owner("No Root Owner")
            enrollment = await runtime.identity.create_enrollment(
                EnrollmentGrant(
                    identity.owner_id, "No Root Device", "desktop", "windows",
                    ("tool.request",), ("computer.observe", "computer.input"),
                )
            )
            issued = await runtime.identity.redeem_enrollment(enrollment.code)
            device = await runtime.identity.authenticate(issued.raw, issued.device_id)
            result = await runtime.computer_actions.execute(
                ComputerAction("inspect_file", {"path": str(self.allowed / "normal.txt")}, False), identity, device,
            )
            self.assertEqual(result.status, "denied")
            self.assertEqual(result.error_code, "file_root_not_configured")
        finally:
            await runtime.shutdown()


if __name__ == "__main__":
    unittest.main()
