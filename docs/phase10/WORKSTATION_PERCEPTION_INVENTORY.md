# Phase 10 workstation perception inventory

Inventory date: 2026-08-30
Repository: `C:\Jarivs\00_final\jarvis`
Probe policy: read-only; no package installation, model download, webcam open,
or screenshot file.

| Capability | Result | Evidence boundary |
|---|---|---|
| Windows desktop | PASS | Windows 11 host reported by native runtime probe |
| `user32.dll` | PASS | Loaded through `ctypes` |
| `gdi32.dll` | PASS | Loaded through `ctypes` |
| `kernel32.dll` | PASS | Loaded through `ctypes` |
| `dwmapi.dll` | PASS | Loaded through `ctypes` |
| Pillow | INSTALLED | Optional package detected; not required by core provider |
| pywinauto | ABSENT | No install attempted |
| uiautomation | ABSENT | No install attempted |
| winrt | ABSENT | No install attempted |
| Tesseract | ABSENT | `where.exe` found no executable |
| FFmpeg | ABSENT | `where.exe` found no executable |
| native active-window metadata | PASS | Process/bounds metadata observed; title omitted from evidence |
| native bounded capture | PASS | Real capture completed; frame was released; no image retained |
| local vision | DEFERRED | No actual image-input model capability verified |
| camera | DEFERRED | Webcam was not opened |

The provider and tests are capability-driven. Optional absence is reported as
deferred rather than being filled by a downloaded dependency or a cloud API.
