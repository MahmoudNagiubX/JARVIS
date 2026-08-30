# Physical acceptance

Automated tests prove contracts and deterministic adapters, not physical
acceptance. A physical result is recorded only after the named dependency is
present and the operator observes the result on the target machine.

Required evidence for a live run includes timestamp, host/device identity,
software/model aliases, configuration fingerprint without secrets, command,
observed result, latency/error notes, and recovery result. Do not mark a
missing microphone, speaker, model, satellite, browser, Venom, HA/MQTT, or
messaging account as PASS.

The Phase 06 workstation audit detected Windows audio devices but found no
Ollama, PostgreSQL listener/client, Node/Playwright, FFmpeg, Venom, HA/MQTT, or
other live listener. Voice, satellite, browser/Playwright, and external-node
physical acceptance therefore remain deferred or partial in the checklist.

Phase 09 adds a runnable typed Windows satellite and loopback transport, but
the inspected workstation still has no authorized second-node endpoint. The
transport and agent tests are contract evidence only; they do not change the
deferred physical status.
