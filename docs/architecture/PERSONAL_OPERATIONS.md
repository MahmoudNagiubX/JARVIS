# Personal Operations

Phase 08 adds a bounded orchestration layer for work, study, focus, review,
leave, return, and sleep modes. `PersonalOperationsService` coordinates the
existing Goals, Missions, Skills, Automation, Briefing, Notification, World
State, and Personalization authorities. It does not own tasks, messages,
notifications, or approvals.

Modes are transient World State with optional TTL. Focus sessions and
operation results are durable audit-friendly records. An operation returns
step status, evidence, and optional failures so an unavailable adapter does
not erase successful local work. Voice and API callers use the same service;
voice speech never becomes approval by implication.
