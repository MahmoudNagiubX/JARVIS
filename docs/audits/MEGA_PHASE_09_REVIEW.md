# Mega Phase 09 review

## Scope

Phase 09 establishes a live-ready distributed runtime shape without claiming
physical integrations that are unavailable on the inspected workstation. The
implementation reuses the existing `WindowsSatelliteRegistry`, `DeviceFabric`,
`VoiceCore`, `ModelGateway`, and authority plane.

## Implemented

- Explicit `test`, `development`, `live-workstation`, and `live-distributed`
  profiles with core/satellite roles, node identity, intervals, and loopback
  URL validation.
- Authenticated standard-library HTTP long-poll transport for connect,
  heartbeat, commands, results, and disconnect.
- Owner/device/session binding, capability checks, bounded queue and payloads,
  command TTL, replay idempotency, command-id reuse denial, revocation, and
  heartbeat freshness wired to DeviceFabric and World State.
- Runnable typed Windows satellite agent using the existing bounded native
  computer controller. No shell, PowerShell, Python evaluation, or arbitrary
  executable operation was added.
- Product computer actions now resolve an explicit owner-scoped target and
  pass through the single `ComputerActionService` policy/approval/audit path
  before a local or satellite execution router. Remote execution records
  request device, target device, and adapter without secret arguments.
- Topology in health/HUD projections without credentials; public health is an
  aggregate while authenticated topology retains useful detail. Model and
  voice adapters remain explicit and lazy.
- The existing satellite health job now expires stale transport sessions,
  disconnects the registry, fails pending commands as `satellite_stale`, and
  projects offline state to DeviceFabric and World State. Identity revocation
  propagates through the existing EventBus to transport, DeviceFabric, and
  World State.
- Heartbeat freshness is retained without repeated lifecycle events or
  World-State observation churn. Reconnect history is bounded, and satellite
  credentials are environment-only for both the CLI and PowerShell launcher.
- `runtime_role=satellite` fails closed in the core composer; the typed
  `jarvis.satellite_agent` remains the only satellite runtime.
- Workstation inventory and evidence record. No Ollama listener, authorized
  Venom host, or installed audio runtime was found; physical model, voice, and
  Venom acceptance remain deferred.

## Independent GitHub Review Remediation

The remediation started from the published Phase 09 commit
`0bb1d0b219b36867ee261f8e0eee20ea5a6913ee` and stayed within the targeted
review gaps. It did not restart Phase 09 or add a second authority. The new
focused file is `tests/test_phase_nine_authority_integration.py`.

## Verification

- Published baseline before remediation: **95 passed, 0 failed**.
- Focused remediation suite: **15 passed, 0 failed**.
- Phase 09 focused suite including remediation: **33 passed, 0 failed**.
- Phase 08 closure + regression: **13 passed, 0 failed**; regression subset is
  **9/9 passed**.
- Full repository suite after remediation: **110 passed, 0 failed** using
  `python -m unittest discover -s tests -v`.
- `python -m compileall src tests`: PASS.
- `git diff --check`: PASS.

The remediation suite covers the product-facing remote authority path,
actor/target separation, permission and approval ordering, cross-owner denial,
no remote-to-local fallback, stale session reconciliation, pending stale
failures, canonical revocation propagation, heartbeat coalescing, bounded
reconnect history, public-health redaction, satellite role separation, and
environment-only credentials. Existing transport, HTTP, model/voice, and
deployment tests remain green.

## Architecture review

The diff was reviewed for duplicate scheduler/EventBus/VoiceCore/tool-registry
authorities and for broad SQL cleanup. None was added. Retention remains the
existing Phase 08 targeted operational cleanup; Phase 09 adds no broad SQL
delete path. Model stores, protected BMO evidence, and donor repositories were
not modified.

## Physical acceptance

The bounded physical computer authority-path scenario passed on 2026-08-30:
the Core server and satellite agent ran as separate processes on `NIGHTFURY`,
connected over loopback with an environment credential, and executed a
non-dry-run `list_processes` observation through `CoreApplication` /
`ComputerActionService` to the target. The result was verified and audit
metadata matched the actor, target, and satellite adapter. Only a bounded
count and correlation are committed in
`docs/phase09/evidence/PHYSICAL_COMPUTER_AUTHORITY_ACCEPTANCE.json`.

This is same-host physical acceptance, not a claim of a second physical node.
Physical voice, local model, Venom, browser, Home Assistant, and external
communications remain honestly deferred.

## Final Routing and Liveness Delta

The final delta is based on `a2f9c4bc31af2d9e20d3fc60827b3db44d9ac365` and
keeps topology resolution inside the existing Core authority. Routing no
longer infers local versus satellite execution from request/target ID
equality. An explicitly targeted device is classified from JARVIS-owned
DeviceFabric/registry topology, so a same-device-ID satellite target still
routes through the satellite adapter; an omitted target retains local
backward-compatible behavior. The client exposes only `target_device_id` and
cannot select an execution adapter.

Stale transport expiration now retires its inactive registry connection, and
registry selection prefers the current active non-revoked connection. Repeated
stale/reconnect cycles therefore keep both transport and registry history
bounded. Public aggregate health reports a healthy reconnect as available and
not degraded; inactive diagnostic history does not affect current status.

Final verification:

- Final routing delta tests: **6 passed, 0 failed**.
- Focused Phase 09 authority integration file: **21 passed, 0 failed**.
- Phase 09 focused suite: **39 passed, 0 failed**.
- Phase 08 closure/regression: **13 passed, 0 failed**; regression subset
  remains **9/9 passed**.
- Full repository suite: **116 passed, 0 failed**.
- `python -m compileall src tests`: PASS.
- `git diff --check`: PASS.

The final tests cover same request/target satellite routing, same-ID offline
no-fallback, no-target local compatibility, stale/reconnect registry current
state, bounded registry history, and public reconnect health semantics. No
new scheduler, EventBus, ApprovalEngine, PermissionEngine, ComputerActionService,
VoiceCore, broad SQL cleanup, paid API, model copy/download, or protected BMO
evidence change was introduced.
