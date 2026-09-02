# Home Architecture & Safety Policy

## Home Control Authority
JARVIS interacts with Home Assistant and smart home devices via `HomeActionService`, enforcing explicit safety boundaries, allowlists, and approval thresholds:

```
+-------------------------------------------------------------------------------+
| HomeActionService (NIGHTFURY)                                                 |
| - Registry of HomeEntityMapping (entity_id, domain, area, enabled)            |
| - Safety Policy Enforcement: allowlist check, dangerous action block          |
| - Consequential Action Gate: temperature thresholds (15°C - 30°C)             |
| - Transport Adapters: HomeAssistant REST/WS Transport, RestrictedMQTTTransport|
+---------------------------------------+---------------------------------------+
                                        |
       +--------------------------------+-------------------------------+
       |                                                                |
       v                                                                v
+-------------------------------+                               +---------------+
| Home Assistant Core           |                               | ESP32 / Relays|
| (Lights, Climate, Scenes)     |                               | (Direct MQTT) |
+-------------------------------+                               +---------------+
```

## Action Boundaries
1. **Safe Action Allowlist**: `turn_on`, `turn_off`, `set_brightness`, `set_color`, `trigger_scene`, `set_temperature`, `publish_mqtt`, `list_entities`, `read_state`, `read_sensor`.
2. **Blocked Dangerous Actions**: `lock`, `unlock`, `alarm`, `security_override`, `life_safety_override`, `raw_shell`, `system_exec`. Always denied (`home_action_blocked`).
3. **Consequential Parameter Bounds**: Temperature adjustments outside 15°C to 30°C require explicit owner approval (`approval_required`).
