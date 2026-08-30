# Windows desktop context

`WindowsDesktopProvider` is a zero-download, stdlib/`ctypes` adapter. It uses
typed native calls for foreground-window lookup, visible-window enumeration,
window rectangles, process executable names, and virtual-display dimensions.
It does not use `wmic`, a registry crawl, process-memory reads, shell commands,
or arbitrary PowerShell.

`window_ref` values are ephemeral references with a 45-second default TTL.
Raw HWND values never cross the public contract. Invalid, stale, or hidden
references fail closed with `window_ref_expired`.

Capture modes are full virtual desktop, active-window rectangle, and a
validated explicit region. Regions must be positive, in bounds, and below the
12-megapixel safety cap. Capture output is metadata only after the transient
buffer is released.
