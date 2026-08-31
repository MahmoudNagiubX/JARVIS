# Phase 14 capability activation matrix

| Capability | Backend exists | UI existed before | Phase 14 action | User-ready after |
|---|---:|---:|---|---:|
| Agent text conversation | Yes | Partial legacy HUD | Route Chat through `CoreApplication.send_message` and canonical runtime | Yes |
| Conversation history | Yes | No rich surface | Add owner-bound list/history reads over repository authority | Yes |
| Experience projection | Yes | Yes, legacy HUD | Make local Command Center consume the same projection | Yes |
| Approvals | Yes | Partial | Show sanitized pending cards and call existing resume endpoint | Yes |
| Missions and goals | Yes | Partial | Add state-backed Missions page and honest empty states | Inspectable |
| Memory | Yes | Partial API | Add search, inspect, edit, and delete controls through `MemoryService` | Yes |
| World state/current context | Yes | Partial | Separate projection-backed Context page from durable memory | Yes |
| Notifications/proactive state | Yes | Partial | Add projection-backed Notifications and attention cards | Inspectable |
| Automation/personal operations | Yes | Partial API | Add Automation page over existing state | Inspectable |
| Research | Yes | Partial API | Add Research page; unavailable providers remain explicit | Inspectable |
| Engineering workers | Yes | Partial HUD | Add read-only Engineering page | Inspectable |
| Browser/computer | Yes | Partial API | Add Browser entry point; actions remain authority/approval-bound | Inspectable |
| Skills | Yes | Partial HUD | Add Skills registry page | Inspectable |
| Devices/home | Yes | Partial HUD | Add Devices page and honest disconnected home state | Inspectable |
| Voice | Yes | Partial Tk/HUD | Show reported operational state; defer physical acceptance | Operational state only |
| Setup/repair/diagnostics | Yes | Yes, Tk | Keep Tk as advanced lifecycle surface | Yes |

No UI component becomes an identity, memory, mission, model, tool, approval,
event bus, scheduler, or VoiceCore authority.
