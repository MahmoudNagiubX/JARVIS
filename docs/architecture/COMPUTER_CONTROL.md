# Computer control

Phase 04 exposes computer actions through `ComputerActionService` and the
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
