# Phase 17 Last Real-Network Readiness Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the residual Phase 17 real-network and zero-touch readiness gaps without changing the accepted Option A architecture or beginning Phase 18/19.

**Architecture:** Keep NIGHTFURY as the single Core authority and reuse the existing `JarvisRuntime`, `CoreApplication`, `CoreHttpServer`, `CoreNodeHttpServer`, `WindowsSatelliteAgent`, `DeviceFabricService`, `DurableApprovalEngine`, and `VenomNode`. Add one canonical explicitly configured LAN trust policy and one bounded desktop-owned node-server lifecycle; harden existing boundaries with atomic claims and binding checks rather than adding authorities.

**Tech Stack:** Python 3.11+, stdlib `ipaddress`/`urllib`/`threading`, SQLite repository transactions, `unittest`/`pytest`, existing setuptools package build, systemd provisioner seams.

**Spec:** `C:\Users\mahmo\Downloads\JARVIS_PHASE_17_LAST_REAL_NETWORK_READINESS_CLOSURE.md`

## Global Constraints

- Required base is `db3f61a2a9442cb4c99c52b8b06702a2147d5254` or a legitimate descendant.
- Default trust is `SAFE PRIVATE/LOCAL ONLY`; `192.162.1.0/24` is accepted only through explicit `trusted_lan_cidrs`, labeled `EXPLICIT_LOCAL_TRUST_OVERRIDE`, and never as a source-code default.
- Reject `0.0.0.0/0`, `::/0`, multicast, unspecified, invalid, overlong, and overcounted trusted CIDRs.
- Keep one SQLite writer, one AgentRuntime, one VoiceCore, one EventBus, one scheduler, and one device fabric.
- Core Command Center remains loopback-only; the LAN server exposes bounded node routes only; no public Internet, cloud services, unrestricted shell, or hardcoded owner LAN addresses.
- Do not alter physical Venom state, ask for credentials, start Phase 18/19, reopen physical voice acceptance, or migrate SQLite.
- Secrets remain outside `DesktopProductConfig`; invalid settings fail closed or degrade safely.
- Preserve `docs/phase_reports/evidence/PHASE_10_JARVIS_VOICE_CORE.json` exactly and never stage it.

---

### Task 1: Add the residual readiness regression matrix

**Files:**
- Create: `tests/test_phase_seventeen_network_readiness_closure.py`
- Read: `tests/test_phase_seventeen_network_closure.py`, `tests/test_phase_seventeen_venom_provisioning.py`, `tests/test_phase_thirteen_zero_touch_productization.py`

**Interfaces:**
- Consumes the existing network, node HTTP, desktop, provisioning, device, and Home service APIs.
- Produces named failing tests for each residual requirement; tests use real services with only external OS/network operations replaced by narrow fakes.

- [x] **Step 1: Write tests that fail against the current residual behavior**

Cover these observable contracts:

```python
def test_owner_cidr_is_explicit_override_and_dangerous_cidrs_are_rejected(): ...
def test_windows_satellite_accepts_configured_owner_lan_and_blocks_public_url(): ...
def test_node_server_uses_the_same_trusted_lan_policy_for_bind_and_client_ip(): ...
def test_desktop_config_round_trips_bounded_node_settings_without_secrets(): ...
def test_desktop_start_automatically_starts_and_stops_one_node_server(): ...
def test_venom_provisioner_installs_and_import_smoke_checks_a_local_package(): ...
def test_venom_provisioner_reports_package_or_systemd_failure(): ...
def test_only_bound_server_device_can_publish_venom_heartbeat(): ...
def test_detailed_node_health_requires_authentication(): ...
def test_concurrent_home_approval_executes_one_external_action(): ...
def test_approve_deny_race_has_one_canonical_decision(): ...
def test_restart_after_decision_does_not_replay_raw_home_action(): ...
```

Use literal expected values (`ALLOW`, `BLOCK`, `EXPLICIT_LOCAL_TRUST_OVERRIDE`, HTTP status codes, and one transport call), not assertions that mirror production helpers.

- [x] **Step 2: Run only the new matrix to verify RED**

Run: `python -m pytest tests/test_phase_seventeen_network_readiness_closure.py -q`

Expected: failures identify missing readiness behavior, with no production edits made before this RED run.

---

### Task 2: Implement one canonical trusted-LAN policy and wire satellite/node transport

**Files:**
- Modify: `src/jarvis/network/validation.py`
- Modify: `src/jarvis/api/node_http.py`
- Modify: `src/jarvis/satellite_agent/agent.py`
- Test: `tests/test_phase_seventeen_network_readiness_closure.py`

**Interfaces:**
- `validate_private_core_url(url, mode="live-distributed", resolver=None, trusted_lan_cidrs=()) -> str` validates default safe local ranges plus explicit overrides.
- `is_private_ip(value, trusted_lan_cidrs=()) -> bool` accepts the same policy for client/bind checks.
- A public classification helper returns the policy label needed by diagnostics/tests without treating overrides as RFC1918 private space.
- `SatelliteAgentConfig` carries bounded `trusted_lan_cidrs`; `WindowsSatelliteAgent` delegates URL validation to the canonical policy.
- `CoreNodeHttpServer` accepts the same trusted CIDRs and uses them for bind/client validation.

- [x] **Step 1: Implement CIDR parsing/validation with bounded explicit overrides**

Reject malformed, wildcard, unspecified, multicast, overcounted, and overlong values. Preserve loopback local/test behavior and live-distributed rejection. Never add `192.162.0.0/16` to defaults.

- [x] **Step 2: Run the policy and satellite/node tests**

Run: `python -m pytest tests/test_phase_seventeen_network_readiness_closure.py -k "cidr or satellite or node_server" -q`

Expected: PASS.

- [x] **Step 3: Refactor only after green**

Remove the old satellite-only loopback validator and any node-server duplicate range checks, keeping one import path to the canonical policy.

---

### Task 3: Add safe desktop configuration and zero-touch node-server lifecycle

**Files:**
- Modify: `src/jarvis/desktop/config.py`
- Modify: `src/jarvis/desktop/lifecycle.py`
- Modify: `src/jarvis/desktop/diagnostics.py`
- Test: `tests/test_phase_seventeen_network_readiness_closure.py`

**Interfaces:**
- `DesktopProductConfig` gains bounded non-secret fields for distributed node transport: enable flag, bind host, port, and `trusted_lan_cidrs`; config version migration remains backward-compatible.
- `JarvisDesktopLifecycle` starts at most one `CoreNodeHttpServer` over the existing `CoreApplication(self.runtime)`, stores its server/thread, exposes safe diagnostics, and stops it before releasing the instance lock.
- Defaults remain loopback-safe and disabled unless explicitly configured; invalid config returns setup/degraded state without a wildcard bind.

- [x] **Step 1: Make the config/lifecycle tests RED**

Assert legacy version-1 settings load with safe defaults, credentials cannot be serialized, explicit owner CIDR round-trips, automatic start creates exactly one node server, second lifecycle is `already_running`, and stop closes the node server.

- [x] **Step 2: Implement the minimal config migration and lifecycle wiring**

Reuse the existing runtime and create exactly one `CoreApplication`; do not create a second runtime or expose existing UI routes on LAN.

- [x] **Step 3: Run the focused desktop tests**

Run: `python -m pytest tests/test_phase_seventeen_network_readiness_closure.py -k "desktop or config" -q`

Expected: PASS.

- [x] **Step 4: Verify existing desktop regressions**

Run: `python -m pytest tests/test_phase_thirteen_zero_touch_productization.py tests/test_phase_fourteen_v3_cinematic.py -q`

Expected: all existing tests remain green.

---

### Task 4: Make Venom provisioning prove a runnable offline package

**Files:**
- Modify: `scripts/venom/setup.py`
- Test: `tests/test_phase_seventeen_network_readiness_closure.py`
- Read: `pyproject.toml`

**Interfaces:**
- `provision(...)` remains idempotent and testable through injected command runner/path seams.
- It creates a real venv or an explicit test-equivalent interpreter seam, installs/copies the local package without Internet/PYTHONPATH, runs `import jarvis` and `import jarvis.nodes.venom_daemon`, and stops with truthful failure status/reason when any required stage fails.
- Existing dry-run and rollback metadata remain compatible.

- [x] **Step 1: Add failing package-install, import-smoke, and failure-truth tests**

Use a temporary install root and a narrow command runner; assert failed venv, package install, import smoke, daemon reload, enable, and start commands return non-success status instead of a false `success` result.

- [x] **Step 2: Implement the smallest offline deployment path**

Use the canonical repository/package source available to the provisioner, create a real interpreter environment, install with no network dependency, and record each completed stage. Do not add boot-time cloning or cloud dependencies.

- [x] **Step 3: Run provisioning tests**

Run: `python -m pytest tests/test_phase_seventeen_network_readiness_closure.py -k "provision" -q`

Expected: PASS.

---

### Task 5: Enforce Venom binding and authenticate detailed node health

**Files:**
- Modify: `src/jarvis/api/core.py`
- Modify: `src/jarvis/api/node_http.py`
- Test: `tests/test_phase_seventeen_network_readiness_closure.py`

**Interfaces:**
- `CoreApplication.venom_heartbeat` accepts only an active, non-revoked, same-owner, server-role device with `node.health` and canonical Venom binding metadata; other authenticated devices fail closed before telemetry mutation.
- Detailed `/health`, `/nodes/health`, `/venom/health`, and `/nodes/venom/health` require the existing node authentication boundary. If an unauthenticated liveness route is retained, it returns only `{"service":"jarvis-node","alive":true}`.
- Enrollment redemption remains unauthenticated and one-time; UI/memory/browser/admin routes remain unavailable on the node server.

- [x] **Step 1: Run the binding/auth tests RED**

Expected: a room satellite, desktop, wrong owner, revoked Venom, and unauthenticated detailed-health request currently demonstrate the missing guard.

- [x] **Step 2: Implement the binding predicate and route guard**

Read the enrolled device record rather than hardcoding a physical device ID. Keep telemetry bounded and preserve the existing Core authority.

- [x] **Step 3: Run focused tests**

Run: `python -m pytest tests/test_phase_seventeen_network_readiness_closure.py -k "venom or health or auth" -q`

Expected: PASS.

---

### Task 6: Add an atomic Home approval execution claim

**Files:**
- Modify: `src/jarvis/devices/home/service.py`
- Modify: `src/jarvis/authority/approvals/service.py` only if the existing repository CAS boundary is insufficient
- Modify: `src/jarvis/persistence/repositories.py` only for a bounded compare-and-set operation if required
- Test: `tests/test_phase_seventeen_network_readiness_closure.py`

**Interfaces:**
- Approval decision remains canonical in the existing `DurableApprovalEngine`.
- Before any external Home transport call, one winner atomically claims the pending action; losers return a deterministic already-consumed/decision result and never execute transport.
- Approve-vs-deny produces one durable decision; restart with no raw pending args fails safe and cannot replay.

- [x] **Step 1: Run concurrent tests RED**

Use a barrier in a fake transport and two real service calls; assert exactly one transport execution and one canonical approval decision.

- [x] **Step 2: Implement the minimal CAS/claim seam**

Do not add a second approval engine or broad schema migration. Keep raw Home arguments ephemeral and remove them after the winner claims or the request is denied.

- [x] **Step 3: Run focused approval tests**

Run: `python -m pytest tests/test_phase_seventeen_network_readiness_closure.py -k "approval or race" -q`

Expected: PASS.

---

### Task 7: Update Phase 17 documentation and perform closure verification

**Files:**
- Modify: `docs/audits/MEGA_PHASE_17_REVIEW.md`
- Modify: `docs/phase17/PHASE17_ACCEPTANCE.md`
- Modify: `docs/phase17/SATELLITE_TRANSPORT.md`
- Modify: `docs/phase17/VENOM_DEPLOYMENT.md`
- Modify: `docs/phase17/VENOM_OPERATIONS.md`
- Modify: `docs/phase17/PRIVACY_AND_SECURITY.md`
- Modify: `docs/phase17/ACTIVATION_PLAN.md`

- [x] **Step 1: Run the complete new focused matrix**

Run: `python -m pytest tests/test_phase_seventeen_network_readiness_closure.py -q`

Expected: more than zero tests and zero failures.

- [x] **Step 2: Run Phase 17 and phase 13-16 regressions**

Run: `python -m pytest tests -k phase_seventeen -q` and the repository’s existing Phase 13-16 regression selector.

Expected: Phase 17 is greater than 66 passed; Phase 16 is at least 47, Phase 15 at least 45, Phase 14 at least 19, and Phase 13 at least 107, with zero failures.

- [x] **Step 3: Run repository, frontend, and static gates**

Run the full Python suite, frontend tests/build/audit, `python -m compileall src tests`, `git diff --check`, remote asset scan, and duplicate-authority scan. Expected: full Python is greater than 502 with zero failures, frontend is at least 75 with zero failures, and all gates pass.

- [x] **Step 4: Review the full diff**

Confirm no duplicate EventBus/Scheduler/AgentRuntime/VoiceCore/DeviceFabric, no broad SQL cleanup, no public bind/default, no hardcoded `192.162.1.33`/`192.162.1.2`, and no changes to protected Phase 10 evidence.

- [x] **Step 5: Commit and push one focused change**

```bash
git add <explicit readiness source/tests/docs paths>
git commit -m "fix: close phase 17 real network readiness"
git push origin main
```

Verify `git rev-parse HEAD` equals `git rev-parse origin/main`, `git status --short --branch` is clean, and Phase 18/19 were not started.

---
