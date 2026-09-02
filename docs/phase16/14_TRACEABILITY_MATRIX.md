# Phase 16: Requirements Traceability Matrix

| Specification Requirement | Implementation Path | Verification Test / Evidence |
|---|---|---|
| Durable Memory Policy & Credential Blocking | `src/jarvis/memory/policy.py` | `tests/test_phase_sixteen_memory_core.py::test_memory_policy_blocks_credentials` |
| Deterministic Extraction (Arabic & English) | `src/jarvis/memory/extractors.py` | `tests/test_phase_sixteen_bilingual_arabic.py::test_arabic_deterministic_extraction` |
| Key-Based Conflict & Superseding Versioning | `src/jarvis/memory/service.py` | `tests/test_phase_sixteen_memory_core.py::test_memory_conflict_and_superseding` |
| Memory Deletion & Category Forgetting | `src/jarvis/memory/service.py` | `tests/test_phase_sixteen_memory_core.py::test_memory_delete_and_forget_category` |
| Memory Expiry & Maintenance | `src/jarvis/memory/service.py` | `tests/test_phase_sixteen_memory_core.py::test_memory_expiry_and_maintenance` |
| Arabic Keyword Ranking & Normalization | `src/jarvis/memory/retrieval.py` | `tests/test_phase_sixteen_bilingual_arabic.py::test_arabic_normalization_and_retrieval` |
| World State Freshness TTL & Expiry | `src/jarvis/world_state/service.py` | `tests/test_phase_sixteen_world_state_firewall.py::test_freshness_ttl_and_expiry` |
| Strict World State != Memory Firewall | `src/jarvis/world_state/service.py` | `tests/test_phase_sixteen_world_state_firewall.py::test_strict_firewall_world_state_never_persists_to_memory` |
| Competing Observations Conflict Detection | `src/jarvis/world_state/service.py` | `tests/test_phase_sixteen_world_state_firewall.py::test_competing_observations_conflict_detection` |
| Personal Context Hierarchy & Metadata | `src/jarvis/context/assembler.py` | `tests/test_phase_sixteen_context_assembly.py::test_context_assembler_bounds_and_selection_metadata` |
| Goal Lifecycle & Checkpoint Auditing | `src/jarvis/goals/engine.py` | `tests/test_phase_sixteen_goals_missions.py::test_goal_lifecycle_and_checkpoints` |
| Mission Planning & Budget Guardrails | `src/jarvis/missions/service.py` | `tests/test_phase_sixteen_goals_missions.py::test_mission_lifecycle_and_budget_bounds` |
| Mission Approval Consumption & Exact Resume | `src/jarvis/missions/service.py`, `src/jarvis/persistence/repositories.py` | `tests/test_phase_sixteen_goals_missions.py::test_mission_approval_pause_and_exact_resume`, `test_mission_approval_denial_fails_safely_and_no_step_start`, `test_concurrent_mission_approval_resume_exactly_once` |
| Interrupted Mission Crash Reconciliation | `src/jarvis/persistence/repositories.py` | `tests/test_phase_sixteen_goals_missions.py::test_startup_reconciliation_of_interrupted_missions` |
| Proactive Detectors & Notification Bridge | `src/jarvis/proactive/service.py`, `src/jarvis/bootstrap.py` | `tests/test_phase_sixteen_proactivity_automation.py::test_proactive_finding_bridges_to_canonical_notification_and_experience_projection`, `test_proactive_notification_restart_visibility` |
| Safe Automation Rules (No Raw Shells) | `src/jarvis/automation/service.py` | `tests/test_phase_sixteen_proactivity_automation.py::test_automation_rule_creation_and_execution` |
| Untrusted Web/Browser Direct-Memory Firewall | `src/jarvis/memory/policy.py` | `tests/test_phase_sixteen_security_injection.py::test_untrusted_direct_memory_fail_closed_and_explicit_owner_restate`, `test_untrusted_source_prompt_injection_firewall` |
| Symmetric Project Context Scoping | `src/jarvis/context/assembler.py`, `src/jarvis/world_state/service.py` | `tests/test_phase_sixteen_context_assembly.py::test_symmetric_project_context_scoping_global_alpha_beta_matrix` |
| Cross-Owner Multi-Tenant Isolation | `src/jarvis/persistence/repositories.py` | `tests/test_phase_sixteen_security_injection.py::test_cross_owner_memory_and_goal_isolation` |
| 100% Offline Local Operation | `src/jarvis/offline/service.py` | `tests/test_phase_sixteen_offline.py::test_complete_local_personal_intelligence_stack_offline` |
| Desktop UI Memory Center & Privacy Controls | `ui/src/screens/Screens.tsx` | Vitest test suite (`75 passed across 14 files`), Vite production build |
