# Computer control

## Native installed-application surface

Installed desktop applications are the preferred local surface for application
requests. The product-owned `InstalledApplicationRegistry` is a bounded
identity catalog, not an execution authority. It reads only the per-user and
all-users Start Menu program roots, Windows App Paths entries, and a small
legacy allowlist for known system applications. It does not scan arbitrary
drives, return executable paths to the model, or accept a model-supplied shell
command, executable path, script, or launch argument.

The model-facing descriptor contains only an opaque `app_ref`, bounded display
names/aliases, publisher/version when available, support tier, risk/class,
login status, surface preference, and capability flags. The registry keeps the
resolved target, launch arguments, process/window identity, and SHA-256
fingerprint private. Duplicate friendly-name identities fail closed; a
previously resolved target is re-fingerprinted immediately before launch.

All launch and focus requests travel through `ComputerActionService` and the
local `WindowsNativeComputerController`:

```text
observe catalog -> resolve opaque app_ref -> policy/approval
-> exact native launch or existing-window focus -> fresh window/foreground verification
-> audit/event receipt
```

`open_application` may focus an existing uniquely identified window or launch
the exact verified `.exe`/approved MSIX identity with `shell=False`. It never
falls back to a generic shell. `focus_application` never launches. Generic
hosts such as Windows Calculator require a bounded title rule in addition to
the verified process identity. Admin tools, installers, uninstallers, and
background components are catalogued only as denied/unsupported Tier D items.
Remote/satellite application control is denied; installed-app control is a
same-host native capability.

Current support is truthful Tier C launch/focus only. Semantic application
workflows and visual fallback remain explicit capabilities and are not inferred
from discovery. Tier A/B status requires fresh physical evidence for the exact
application and workflow. Brave host open/focus is separate from browser page
control: page navigation, DOM/accessibility interaction, transfers, and
authenticated sessions remain under `BrowserActionService` and its dedicated
Brave profile policy.

The runtime exposes computer actions through `ComputerActionService` and the
typed `ComputerAction`/`ComputerResult` contracts. Every request carries an
authenticated identity, device, scope, capability set, session, and
correlation id. Permission, approval, audit, and normalized computer events
are evaluated before controller execution.

The built-in Windows controller is intentionally bounded. It can inspect a
small process list, read a small text file, search a bounded directory tree,
open existing files/folders, launch allowlisted applications, and stop only an
allowlisted safe process. Unsupported volume, mouse, keyboard, clipboard,
window, and screenshot operations return an explicit adapter status instead of
opening an unrestricted shell or capture channel.

The native controller is the first adapter. The existing typed Windows
satellite registry remains available for remote execution, while UFO/Windows
UI automation is represented as a future adapter boundary. No external UI
automation package is required to compose or test the runtime.

Read actions use `computer.observe`. State-changing actions require
`computer.input` and approval when the authority or autonomy policy requires
it. Dry-run results are marked verified only as contract-level simulation;
they do not claim physical execution.

Phase 10 adds only grounded `focus_window` support. It accepts an ephemeral
`window_ref`, revalidates it through the native desktop provider, executes
through this existing `ComputerActionService`, and reports `verified` only
when `GetForegroundWindow` confirms the result. Raw HWNDs, coordinate clicks,
keyboard injection, and vision-selected coordinates remain outside scope.
