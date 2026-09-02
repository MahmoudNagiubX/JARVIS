# Phase 16: Proactivity & Automation Runtime

## 1. Deterministic Proactive Detectors (`DurableProactiveService`)

Proactivity in JARVIS is strictly deterministic and evidence-based. An LLM is never prompted to invent proactive suggestions.

| Detector Type | Trigger Condition | Severity | Cooldown | Recommended Action |
|---|---|---|---|---|
| `build_failed` | World State reports `build.status in ("failed", "failing", "error")` | Warning | 3600s | Run tests / inspect build |
| `tests_repeatedly_failing` | >= 3 test failure events in past 1 hour | Warning | 3600s | Review failing test output |
| `goal_blocked` | Active goal has status `BLOCKED` | Warning | 3600s | Inspect blocked reason |
| `deadline_approaching` | Goal target date within next 24 hours | Warning | 3600s | Review remaining steps |
| `dev_server_stopped` | `dev_server.status in ("stopped", "offline", "dead")` | Warning | 1800s | Restart development server |
| `task_stalled` | `task.status in ("stalled", "idle_too_long")` | Info | 1800s | Check background job |
| `disk_space_critical` | `system.disk_free_gb < 5.0` | Critical | 1800s | Free local disk space |
| `approval_waiting` | Pending approval older than 10 minutes | Info | 1800s | Review approval queue |
| `communication_followup_due`| Followup timestamp <= now | Info | 1800s | Reply to communication thread |

## 2. Canonical NotificationService Bridge & Deduplication
1. **Canonical Notification Bridge**: Newly detected proactive findings automatically create a canonical `Notification` in `NotificationService` with `source="proactive"`, truthful severity, stable dedup key (`proactive:{finding_type}:{fingerprint}`), and metadata (`finding_id`, `finding_type`).
2. **HUD & ExperienceProjection Visibility**: The proactive alerts are projected to the client Command Center HUD through `ExperienceProjection.state()`.
3. **Storm Suppression**: If a condition triggers 100 times within its configured cooldown, exactly 1 finding and 1 canonical notification exist.
4. **Independent Lifecycle**: Dismissing/acknowledging a notification clears the HUD alert without falsely marking the underlying durable `ProactiveFinding` as resolved.
5. **Restart Rehydration**: Active durable findings (`status == 'detected'`) are rehydrated into the in-memory `NotificationService` across process restarts without duplicate alerts.

## 3. Safe Automation Runtime (`AutomationService`)

Automation rules allow deterministic reactions to system events, schedule triggers, or world state changes.

### Security Guardrails:
- **Allowed Actions**: Restricted strictly to `skill`, `mission`, `notification`, and `briefing`.
- **No Raw Commands**: Targets starting with `cmd:`, `shell:`, or `python:` are blocked at rule creation.
- **Risk Ceilings**: Rules with `critical` or `forbidden_autonomous` risk are unconditionally rejected.
- **Offline Safety**: Action execution respects `OfflineModeService`; internet-requiring dispatches are cleanly paused or skipped when offline.
