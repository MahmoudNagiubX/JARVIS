# Notifications

`NotificationService` provides owner-scoped local notification records with
title, message, severity, source, action options, target device, expiry, and a
deduplication key. Repeated active notifications with the same owner and key
reuse the existing record. Create, deliver, dismiss, and failure boundaries
emit UI events and audit records.

Delivery is injected so the core remains dependency-free. The default runtime
stores notifications but does not claim an operating-system toast, speaker,
or device delivery adapter. Expiry and dismissal are visible to callers, and
notification content remains local unless a configured adapter explicitly
handles it.
