# HUD development

Run the loopback server with `PYTHONPATH=src python -m jarvis --help`, then
open `/v1/hud`. Authenticate state requests with the existing credential,
device id, and identity id query parameters. Keep presentation changes inside
the static HUD and experience projection; do not add business state to the
browser.
