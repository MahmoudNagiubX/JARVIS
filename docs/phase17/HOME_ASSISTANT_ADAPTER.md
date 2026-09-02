# Home Assistant Adapter & Entity Mapping

## Transport Integration & Verification
The Home Assistant integration is governed through `HomeTransport` and `HomeActionService`:
- **Entity Discovery**: Discovers entities across domains (`light`, `switch`, `climate`, `sensor`, `scene`).
- **Entity Mappings (`HomeEntityMapping`)**: Maps entity IDs to canonical room boundaries (`room_id`), user-facing aliases, domain categories, and enabled flags.
- **Truthful UI Projection**: The Command Center UI never fabricates live entity state without verified backend connection data. If the controller is offline or unconfigured, the UI displays a clean empty state.
- **Audit Logging**: All executed, denied, or approval-paused home actions append structured audit records into `DurableAuditService` without leaking bearer tokens or credentials.
