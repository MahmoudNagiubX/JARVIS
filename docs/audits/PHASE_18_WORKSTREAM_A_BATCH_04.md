# PHASE 18 — WORKSTREAM A — BATCH 04
## File-Search Boundary Hardening → Grounded Drag + Owned Text Fixture → Local Visual OCR Grounding

**Task:** `tasks/CLOUD_CODE_MASTER_PHASE_18_WORKSTREAM_A_BATCH_04.md`
**Branch:** `feature/phase-18-computer-use-v2`
**Status:** IN PROGRESS — Milestone 0 complete, Milestones 1/2 not yet started.

This is the single report for the whole batch (per Section 11 of the task file); it is appended to, not duplicated, as later milestones complete.

---

## 1. Starting state

- Branch: `feature/phase-18-computer-use-v2`
- Starting HEAD: `7188c712563a9340112da1b86fcd218d71898af1` — matched the task file's expected starting HEAD exactly; branch was in sync with `origin/feature/phase-18-computer-use-v2`, `git status --short` clean, no unexplained divergence.

---

## 2. Independent review finding against Batch 03

Two hardening findings identified after independent review of the Batch 03 file-access confinement work, both addressed in Milestone 0 below:

| ID | Summary | Disposition |
| --- | --- | --- |
| R18B03-001 | `FileAccessPolicy.filter_search_results()` re-checked each candidate only *after* `Path.rglob()` had already been free to descend through a symlink/junction/reparse point before filtering happened — safe for model-visible output (a candidate outside the root was never *returned*), but not a genuine pre-descent traversal boundary, and no depth bound or live scan/result bounding existed during the walk itself. | Fixed — replaced with `FileAccessPolicy.iter_search_candidates(root, pattern)`, a bounded, iterative, pre-descent walker (see §3.2 below). |
| R18B03-002 | `_SENSITIVE_FILE_NAMES`'s exact-match set (`.env`, `.env.local`, `.env.development`, `.env.production`, `.env.test`) missed common variants such as `.env.staging`, `.env.development.local`, `.env.production.local`, `.env.test.local`, and any other `.env.<suffix>`. | Fixed — `.env`/`.env.*` is now matched as a wildcard family (excluding the explicitly-safe `.env.example` template), without over-matching `.environment` (see §3.3 below). |

---

## 3. Milestone 0 — File-search boundary hardening

**Commit:** `MILESTONE_0_COMMIT` (recorded in §3.6 below after push)

### 3.1 Root cause

`_search_files()` (`src/jarvis/computer/service.py`) called `root.rglob(pattern)` and passed the resulting generator into `FileAccessPolicy.filter_search_results(root, candidates)`, which validated each candidate's *resolved* path only after `rglob()` had already been allowed to enumerate it. Because `rglob()` follows directory symlinks/junctions by default, the underlying OS-level directory walk could physically descend into a reparse point whose target lies outside the approved root before the per-candidate filter ever ran — the model never saw an out-of-root result (the filter denies it), but the traversal itself was not bounded at the directory level, had no depth limit, and had to materialize/iterate an effectively unbounded generator before bounds were applied per-candidate.

### 3.2 Pre-descent bounded walker (R18B03-001)

`FileAccessPolicy.filter_search_results()` was replaced by `FileAccessPolicy.iter_search_candidates(root, pattern)` (`src/jarvis/computer/file_access.py`) — an iterative (stack-based, not recursive), pre-descent walker:

1. **Classify before descending.** For every directory entry found via `os.scandir()`, `_is_reparse_point(path)` classifies it *before* any decision to enter it, using `os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT` — verified empirically against a real `mklink /J` junction (see §3.4): the junction's `st_file_attributes` correctly carries the reparse-point bit, whereas `Path.is_symlink()` reports `False` for it and would have under-classified it as an ordinary directory. Classification fails closed: if `os.lstat()` itself raises `OSError`, the entry is treated as a reparse point (never descended).
2. **Default reparse policy: never follow directory reparse points at all**, even when the entry's target is still inside the approved root. This is deliberately stricter than "follow if still inside root" — simpler, deterministic, and avoids cycle/mount ambiguity entirely — per the task's own recommended simplification.
3. **File symlinks remain usable, narrowly.** A file (not directory) symlink is only returned as a match if its fully resolved target is still inside `root`, is genuinely a file (`Path.is_file()`), and passes the sensitivity policy — never trusted from its unresolved name alone.
4. **Canonicalize and re-verify containment for every real subdirectory before pushing it onto the walk stack** — `entry_path.resolve()` must land inside `root` (`relative_to(root)`), or the directory is never descended (fails closed, counted in the bounded `filtered` count).
5. **Sensitive subtrees are pruned, not filtered post-hoc** — a directory named `.ssh`/`.gnupg`/`.aws`/`.azure`/`.kube` is never descended, so no child (hidden or not) inside it can ever reach the output.
6. **Bounds are enforced live, one directory listing at a time** — `MAX_SEARCH_CANDIDATES_SCANNED` (5000, unchanged) and `MAX_SEARCH_MATCHES` (100, unchanged) are checked before each entry is processed, never after an unbounded list is built. A new `MAX_SEARCH_DEPTH = 32` bounds recursion depth.
7. **Cycle safety.** A bounded canonical-directory `visited` set (casefolded resolved path strings) is kept as defense in depth, even though a directory tree that never follows reparse points cannot itself be cyclic.

`_search_files()` in `service.py` now calls `self.file_access_policy.iter_search_candidates(root, pattern)` directly — it no longer constructs or passes a `Path.rglob()` generator at all. `ComputerActionService` still contains no traversal logic of its own; it only asks the policy for bounded candidates, matching the task's authority requirement.

Direct `inspect_file`/`open_file`/`open_folder` confinement via `FileAccessPolicy.evaluate()` is unaffected by this change (it still resolves and checks the real target path directly) and was not modified.

### 3.3 `.env.*` wildcard sensitivity (R18B03-002)

`_SENSITIVE_FILE_NAMES` no longer carries the individual `.env*` exact-match entries; a new `_is_env_secret_name(name_casefold)` helper matches `.env` or any `.env.<suffix>` (`name_casefold.startswith(".env.")`), explicitly excluding the safe template `.env.example`. Matching is anchored on the literal `.env` stem followed by nothing or a `.` separator, so `.environment` — which has no `.` immediately after `.env` — is never caught by this rule (verified by a dedicated test).

### 3.4 Empirical verification of pre-descent reparse classification

Before implementing, the reparse-point detection approach was verified against a real Windows junction (`cmd /c mklink /J`, temp directories only):

- `Path.is_symlink()` on the junction entry → `False` (junctions are not Win32 symlinks; using `is_symlink()` alone would under-classify them).
- `os.lstat(junction_path).st_file_attributes` → `1040` (`0x410` = `FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT`) → `& stat.FILE_ATTRIBUTE_REPARSE_POINT` correctly evaluates `True`.
- `os.scandir()`'s `DirEntry.is_dir(follow_symlinks=False)` on the same entry → `True` (the OS reports junctions as directory-shaped even without following), confirming the walker's "is this a directory or a file" branch and its "is this a reparse point" branch must be checked independently rather than assuming one implies the other.

This confirmed `st_file_attributes`'s reparse-point bit (not `is_symlink()`) is the correct pre-descent classifier on Windows, with a fallback to `Path.is_symlink()` when `st_file_attributes` is unavailable (non-Windows).

### 3.5 Tests

14 new tests added to `tests/test_phase_eighteen_file_access.py` (38 tests total in the file, all passing, all using only `tempfile.TemporaryDirectory()` fixtures — no owner files):

1. `test_search_does_not_follow_escape_link` (updated to the new API) — junction target outside root is not traversed.
2. `test_walker_never_yields_external_secret_even_transiently` — the external secret never appears even as a transient candidate.
3. `test_junction_directory_inside_root_is_not_descended` — a junction whose target is *inside* the root is still never descended (default no-follow policy).
4. `test_cycle_cannot_cause_unbounded_walk` — a self-referential junction cannot cause an unbounded walk.
5. `test_scan_count_bound_is_enforced` — `MAX_SEARCH_CANDIDATES_SCANNED` is enforced live.
6. `test_result_count_bound_is_enforced` — `MAX_SEARCH_MATCHES` is enforced live.
7. `test_sensitive_subtree_is_pruned` — an entire sensitive directory is pruned, including a hidden child name that never appears in output.
8. `test_normal_nested_search_still_succeeds` — ordinary multi-level nested search still works.
9. `test_env_staging_denied`, `test_env_development_local_denied`, `test_env_production_local_denied`, `test_env_test_local_denied` — `.env.*` variants denied.
10. `test_env_example_is_allowed` (already existing, re-verified) — safe template allowed.
11. `test_dot_environment_unaffected_by_env_wildcard_rule` — `.environment` is not caught by the `.env.*` rule.

### 3.6 Verification

- `python -m pytest tests/test_phase_eighteen_file_access.py -q` → **38 passed**.
- `python -m pytest tests -k "file_access or phase_eighteen" -q` → **205 passed, 515 deselected**.
- `python -m pytest tests -q` (full regression) → **720 passed, 36 subtests passed**.
- `python -m compileall src tests scripts -q` → clean, no errors.
- `git diff --check` → clean, no whitespace errors.
- `grep -rn "rglob" src/` → no remaining `rglob()` usage inside the confined file-search path (`src/jarvis/computer/`); the only other `rglob()` call sites in the repo (`desktop/assets.py`, `desktop/model.py`, `research/providers.py`) are unrelated, out-of-scope subsystems not governed by `FileAccessPolicy`.
- **Commit:** `MILESTONE_0_COMMIT`
- **Push:** `feature/phase-18-computer-use-v2` — recorded after push.

GAP-0503 updated from `RESOLVED` (path-confinement scope) to `RESOLVED_AFTER_REVIEW_HARDENING` (same scope — read/open/search path confinement only; file write/dialogs remain out of scope and unimplemented).
