# Authorized tunnel setup

No Venom host, SSH alias, user, or IP was present in the Phase 09 workstation
inventory. Therefore no tunnel was opened and no host was guessed.

When an operator supplies an authorized SSH target, keep the JARVIS service
loopback-only and use an explicit, reviewed tunnel. Examples use placeholders
only:

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 8787:127.0.0.1:8787 <user>@<authorized-host>
ssh -N -o ExitOnForwardFailure=yes -R 11434:127.0.0.1:11434 <user>@<authorized-host>
```

Verify host keys, account scope, firewall rules, and the exact target before
running a tunnel. Do not put credentials in command arguments or commit
machine-specific host data. Check the local loopback health endpoint and the
remote service independently; an SSH connection alone is not service health.

Record target, direction, ports, timestamp, owner authorization, and recovery
result in the physical evidence record. Close the tunnel after acceptance
unless the deployment owner has explicitly approved supervised persistence.
