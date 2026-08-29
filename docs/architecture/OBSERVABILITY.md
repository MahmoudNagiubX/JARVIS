# Observability

`ObservabilityService` is a local-only wildcard event consumer. It records
low-cardinality counts by event/category, failures, safe duration totals when
events provide them, and the last event timestamp. The system projection also
reports runtime/offline/model status.

The `/v1/experience/system` response exposes these safe metrics. It explicitly
reports local-process storage and `secrets_retained: false`; no hosted
telemetry, cloud metrics, raw prompt, credential, or raw frame sink is added.
