# Personal Operations Testing

The Phase 08 regression suite covers fresh and expired presence evidence,
attention quiet/focus behavior, operation and focus state, partial/offline
behavior, follow-up due/acknowledgement, auto-send allowlists and anti-loop
limits, home safe/blocked actions, unavailable delivery surfaces, and the
World State versus Memory boundary.

Run locally with:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

The HTTP surface must also be checked with missing, valid, revoked, and
wrong-owner credentials. Only `/health`, `/hud`, and `/experience/hud` are
public GET routes; all Phase 08 resource GETs require Bearer plus device and
identity headers.
