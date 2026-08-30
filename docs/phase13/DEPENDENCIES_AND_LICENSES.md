# Phase 13 local voice dependencies and licenses

All model/binary assets are user-local under the documented external voice
root. This repository records code/configuration only and performs no runtime
download.

| Component | Version/asset | License status | Decision |
|---|---|---|---|
| sounddevice | 0.5.6 | package dependency; review its bundled PortAudio notices before distribution | optional local I/O only |
| openWakeWord | 0.6.0 + `hey_jarvis_v0.1.onnx` | code Apache-2.0; supplied pre-trained models CC-BY-NC-SA-4.0 | personal/non-commercial workstation use only; commercial replacement debt recorded |
| Silero VAD | 16 kHz ONNX | MIT | approved local inference boundary |
| faster-whisper | 1.2.1 + local `small` directory | code MIT; weight provenance/license must remain with downloaded model card | no network fallback or cache lookup at runtime |
| Piper | 1.7.0 | engine code MIT; upstream repository archival/move is a maintenance risk | optional local synthesis boundary |
| Piper English voice | `en_US-hfc_female-medium` | model card cites CC-BY-NC-SA-4.0 dataset | personal/non-commercial only pending separate voice/distribution review |
| Piper Arabic voice | `ar_JO-kareem-low` | model card says dataset license “See URL” | routing-only evaluation; no commercial or Egyptian-quality claim |

The product does not clone an owner, actor, or other natural voice. Arabic
`ar_JO` is Jordanian Arabic and low quality; it is not evidence of Egyptian
Arabic intelligibility. Re-review package notices, model cards, provenance,
and all distribution terms before any broader use.
