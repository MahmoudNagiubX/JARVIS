# Phase 16: Desktop UI Surfaces

## 1. Memory Center (`MemoryScreen` in `ui/src/screens/Screens.tsx`)
- **Category Filter Tabs**: Quick filtering across `All`, `fact`, `preference`, `project`, `task`, `goal`, `profile`, and `decision`.
- **Search Bar**: Keyword search matching text, tags, and categories.
- **Card Metadata**: Displays Category, Provenance (`Owner stated`, `Conversation extracted`, `Direct entry`), Confidence meter, Sensitivity, and Status.
- **Card Actions**:
  - `Pin` / `Unpin`: Pins high-priority records for guaranteed inclusion in context.
  - `Edit`: Opens modal to update memory content.
  - `Delete`: Soft-deletes record through `DELETE /memory/{id}` with immediate UI update.

## 2. Missions & Operations Surfaces
- **Missions Screen**: Tracks active, planned, and completed missions with step progress, budget consumption, and approval pause indicators.
- **Operations Screen**: Surfaces approvals requiring user confirmation for consequential actions.

## 3. Settings & Privacy Center (`SettingsScreen`)
- Displays truthful local-first privacy telemetry:
  - `Local brain`: YES
  - `Raw audio stored`: NO
  - `Raw screenshots stored`: NO
  - `Core cloud dependency`: NO
  - `Memory`: Inspectable / editable / deletable
  - `Credentials`: HttpOnly session boundary
