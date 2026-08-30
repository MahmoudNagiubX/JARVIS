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

Phase 09 adds a runnable typed Windows satellite and loopback transport. On
2026-08-30, a bounded same-host physical acceptance ran a real Core server and
real satellite-agent process with an environment-only owner credential. A
non-dry-run `list_processes` observation reached the target through the
product `ComputerActionService`, returned a verified native result, and
produced matching audit metadata. The bounded evidence is stored at
`docs/phase09/evidence/PHYSICAL_COMPUTER_AUTHORITY_ACCEPTANCE.json`.

This proves the Windows authority path on the inspected host; it does not
claim an authorized second physical node. Physical voice, local model, Venom,
browser, and external services remain deferred.
