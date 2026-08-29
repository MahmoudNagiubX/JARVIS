# Event intelligence

The event intelligence service is deterministic and evidence-led. Its first
detector identifies repeated failed/error events inside a bounded time window,
records event IDs, threshold, frequency, confidence, affected resource, and a
recommended read-only action, then applies an active-finding/cooldown rule.

Findings are durable, owner-scoped, resolvable, and visible in the HUD. Future
detectors may add rolling averages, rates, trends, and last-known-good values;
no opaque anomaly score is treated as a fact and no anomaly model is bundled.
