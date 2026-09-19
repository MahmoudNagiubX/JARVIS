# JARVIS Pre-Physical Deep Review Issue Register

**Review date:** 2026-09-19
**Branch:** `feature/jarvis-final-completion`
**Implementation review HEAD:** `a129ddc638df02538ba3f231f2509c3c0ff019b6`
**Starting HEAD:** `d5869e304b0e57e276d88604f54085bf81815f72`
**Scope:** code-controlled pre-physical review only. No owner login, API-key
entry, microphone acceptance, or cross-app account action was performed.

All findings below were found during the review, reproduced or negatively
tested, fixed through the existing canonical authorities, and covered by a
regression test. `RESOLVED` means the code-controlled defect is closed; it
does not imply live provider, authenticated-service, or physical acceptance.

## PRP-001

| Field | Record |
|---|---|
| ID | `PRP-001` |
| Subsystem | `ToolExecutionService` / `DurableApprovalEngine` |
| Severity | `P1` |
| Type | `SECURITY`, `AUTHORITY`, `RELIABILITY` |
| Evidence | Durable approvals used a durable decision call, but the delegated in-memory record was removed after the awaited handler path. Concurrent callers could both pass the local pending check. |
| Reproduction | Run two `decide_and_resume` calls concurrently for one durable, consequential tool approval. The pre-fix shape permitted both callers to reach execution. |
| Root cause | Approval reservation and handler execution were not coupled at the in-memory boundary; the durable CAS alone was not used as an execution claim. |
| User impact | A consequential tool could run twice after one approval. |
| Security/authority impact | Approval replay and duplicate side effects violated the single-use approval invariant. |
| Fix | Reserve delegated approval state before the first await and require `decide_with_claim`; return a typed replay failure when another caller owns the claim. |
| Regression test | `tests/test_phase_eighteen_stabilization.py::test_durable_approval_claim_prevents_concurrent_handler_replay` |
| Commit | `a129ddc` |
| Status | `RESOLVED` |

## PRP-002

| Field | Record |
|---|---|
| ID | `PRP-002` |
| Subsystem | `CapabilityRouter` / hybrid model gateway |
| Severity | `P2` |
| Type | `BUG`, `CONFIG`, `PERFORMANCE` |
| Evidence | The complex reasoning branch preceded the large-context branch, and context sizing considered only a recent slice of messages. A large older context combined with a reasoning route could be sent to Groq first. |
| Reproduction | Submit a request with a large earlier message and a recent reasoning message; request `GENERAL_REASONING`. The pre-fix route selected Groq before Gemini. |
| Root cause | Route precedence and context accounting did not reflect the whole bounded request. |
| User impact | Large or document-like work could use the wrong provider, increasing latency/cost and reducing multimodal/large-context suitability. |
| Security/authority impact | Unnecessary cloud transmission of context was possible, although provider keys and payload limits remained bounded. |
| Fix | Count bounded request message content and evaluate large-context routing immediately after media/vision, before simple/complex route classification. |
| Regression test | `tests/test_hybrid_models.py::test_large_context_precedes_reasoning_route` |
| Commit | `a129ddc` |
| Status | `RESOLVED` |

## PRP-003

| Field | Record |
|---|---|
| ID | `PRP-003` |
| Subsystem | `DurableWorldStateService` |
| Severity | `P1` |
| Type | `SECURITY`, `AUTHORITY`, `BUG` |
| Evidence | Observation persistence used the observation's embedded owner while fact fusion used the caller-supplied owner. A mismatched observation could split one observation across owner partitions. |
| Reproduction | Submit an observation owned by `owner-2` through an `owner-1` call and inspect both observation rows and fused facts. The pre-fix persistence path accepted the mismatch. |
| Root cause | The observation owner was not validated and rebound before both persistence and fact fusion. |
| User impact | World-state reads could be incomplete or cross-owner inconsistent. |
| Security/authority impact | Cross-owner state contamination was possible. |
| Fix | Reject explicit owner mismatches and persist a copied observation bound to the effective owner before any fusion. |
| Regression test | `tests/test_phase_sixteen_world_state_firewall.py::test_observation_owner_binding_cannot_split_persistence_and_facts` |
| Commit | `a129ddc` |
| Status | `RESOLVED` |

## PRP-004

| Field | Record |
|---|---|
| ID | `PRP-004` |
| Subsystem | `MemoryPolicy` |
| Severity | `P1` |
| Type | `SECURITY`, `BUG` |
| Evidence | The credential firewall scanned candidate content but not structured metadata, tags, or source references. Secret-like metadata could reach the memory decision path. |
| Reproduction | Submit a benign content string with credential-like material in `structured_data`, `tags`, or `source_reference`. The pre-fix policy evaluated only content. |
| Root cause | Non-content candidate fields were omitted from policy materialization. |
| User impact | Sensitive metadata could be retained or surfaced as durable Memory. |
| Security/authority impact | Secret retention and web/worker-to-Memory isolation were incomplete. |
| Fix | Serialize bounded metadata fields for the same credential scan, reject oversized metadata, and preserve the existing secret-content rules. |
| Regression test | `tests/test_phase_sixteen_memory_core.py::test_memory_policy_scans_structured_metadata_tags_and_source_reference` |
| Commit | `a129ddc` |
| Status | `RESOLVED` |

## PRP-005

| Field | Record |
|---|---|
| ID | `PRP-005` |
| Subsystem | `WindowsNativeComputerController` file open path |
| Severity | `P2` |
| Type | `FALSE_SUCCESS`, `BUG` |
| Evidence | `_open_path` reported `verified=True` immediately after `os.startfile` dispatch, without checking the resulting application or window state. |
| Reproduction | Patch `os.startfile` to accept a permitted file and inspect the returned computer result. The pre-fix result claimed verification without a postcondition. |
| Root cause | Shell dispatch was treated as target-state verification. |
| User impact | The model could be told that a file was open when Windows had only accepted a dispatch request. |
| Security/authority impact | False verification could permit later plans to rely on an unobserved state. |
| Fix | Keep the bounded dispatch result but mark it `verified=False` with explicit `dispatch_only` and `os_startfile_dispatch_not_independently_verified` metadata. |
| Regression test | `tests/test_phase_eighteen_file_access.py::test_open_file_reports_dispatch_without_claiming_postcondition_verification` |
| Commit | `a129ddc` |
| Status | `RESOLVED` |

## PRP-006

| Field | Record |
|---|---|
| ID | `PRP-006` |
| Subsystem | Installed application discovery and legacy application compatibility path |
| Severity | `P1` |
| Type | `SECURITY`, `AUTHORITY`, `BUG` |
| Evidence | Legacy application resolution used `shutil.which`, allowing PATH/current-directory executables to satisfy names such as Brave. This contradicted the bounded standard-location discovery contract. |
| Reproduction | Put a fake `brave.exe` in a temporary PATH entry and resolve the legacy Brave name. The pre-fix resolver could select the PATH executable. |
| Root cause | Generic executable lookup was reused for an installed-app target. |
| User impact | A name-only app request could launch an unintended executable. |
| Security/authority impact | PATH hijacking could cross the installed-app boundary and bypass the catalog's exact target identity. |
| Fix | Resolve compatibility names only through fixed standard Windows locations; preserve target fingerprinting and revalidation in the registry. |
| Regression test | `tests/test_phase_eighteen_installed_app_registry.py::test_legacy_discovery_ignores_path_executables_and_uses_standard_locations` |
| Commit | `a129ddc` |
| Status | `RESOLVED` |

## PRP-007

| Field | Record |
|---|---|
| ID | `PRP-007` |
| Subsystem | `BrowserActionService` and browser approval HTTP boundary |
| Severity | `P1` |
| Type | `SECURITY`, `AUTHORITY`, `RELIABILITY` |
| Evidence | Browser approval decisions did not carry the authenticated identity/device into the service, and the HTTP route accepted a body-supplied `decided_by`. The pending browser record already contained the owner/device binding. |
| Reproduction | Create a browser approval, attempt a direct decision with a foreign identity/device, and inspect whether the pending action remains available. Concurrent decisions also exercised the pre-fix get/await/pop race. |
| Root cause | Principal validation was not enforced at the browser approval boundary and local reservation occurred after the await. |
| User impact | A wrongly bound caller could attempt to consume an owner approval; concurrent decisions could race. |
| Security/authority impact | Approval owner/device binding and exactly-once browser side effects were incomplete at the direct service/API seam. |
| Fix | Validate optional authenticated identity/device against the pending record, require the authenticated identity as the HTTP decider, reserve before await, and use durable claim semantics. |
| Regression test | `tests/test_phase_fifteen_final_security_closure.py::test_browser_approval_owner_and_device_binding_remains_fail_closed` plus `tests/test_phase_eighteen_browser_v2.py::test_t6_approval_replay_cannot_repeat_a_browser_action` |
| Commit | `a129ddc` |
| Status | `RESOLVED` |

## PRP-008

| Field | Record |
|---|---|
| ID | `PRP-008` |
| Subsystem | `CommunicationsHub` send approval |
| Severity | `P1` |
| Type | `SECURITY`, `AUTHORITY`, `RELIABILITY` |
| Evidence | `decide_send` awaited the approval decision before removing the pending message, and the route accepted a body decider label. |
| Reproduction | Submit one local-channel send approval and decide it concurrently from two tasks. The pre-fix sequence left a duplicate-send window. |
| Root cause | Pending-message reservation happened after the awaited approval operation; service identity/device bindings were not passed through the HTTP boundary. |
| User impact | One approved message could be delivered more than once. |
| Security/authority impact | Duplicate external communication is a consequential side effect and must be exactly once. |
| Fix | Bind the optional authenticated principal to the pending message, use the principal identity as `decided_by`, reserve before await, use `decide_with_claim`, and return a typed replay result. |
| Regression test | `tests/test_phase_four_integration.py::test_communications_notifications_voice_and_capabilities` concurrent send section |
| Commit | `a129ddc` |
| Status | `RESOLVED` |

## PRP-009

| Field | Record |
|---|---|
| ID | `PRP-009` |
| Subsystem | `EngineeringService` write/execution approval |
| Severity | `P1` |
| Type | `SECURITY`, `AUTHORITY`, `RELIABILITY` |
| Evidence | `decide` awaited the approval decision and removed the pending engineering action only after provider execution was prepared. The HTTP route also trusted a body decider label. |
| Reproduction | Submit one approved engineering write and decide it concurrently. The pre-fix pending map was not reserved before the await. |
| Root cause | In-memory reservation and durable approval claim were not made before the provider side effect. |
| User impact | A write/execute action could run twice after one approval. |
| Security/authority impact | Duplicate workspace/provider side effects and missing principal binding violated the canonical action path. |
| Fix | Bind identity/device and decider at the API seam, reserve before await, use `decide_with_claim`, and return a typed replay result. |
| Regression test | `tests/test_phase_five_integration.py::test_engineering_scope_approval_and_existing_worker_boundary` concurrent approval section |
| Commit | `a129ddc` |
| Status | `RESOLVED` |

## Register conclusion

| Severity | Found | Resolved | Remaining code-controlled blockers |
|---|---:|---:|---:|
| P0 | 0 | 0 | 0 |
| P1 | 7 | 7 | 0 |
| P2 | 2 | 2 | 0 |
| P3 | 0 | 0 | 0 |

The remaining release gates are owner-controlled, external-service, optional,
or physical: Groq/Gemini keys, authenticated service destinations, manual
ChatGPT authentication/send confirmation, live Heretic runtime readiness if
not already configured, foreground/focus behavior on an interactive desktop,
voice hardware acceptance, and cold lifecycle/cross-app receipts. They are
not deferred code bugs.
