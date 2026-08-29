# Notification Delivery

`NotificationService` remains the notification record authority.
`NotificationDeliveryCoordinator` applies `AttentionPolicy`, chooses the
available HUD/desktop/voice seam, records each attempt, deduplicates voice
fingerprints, and returns honest `delivered`, `queued`, `unavailable`, or
suppressed results. A missing adapter is recorded as unavailable, never as a
successful presentation.
