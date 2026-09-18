"""Run the bounded Batch 10 T2 dedicated-profile restart gate.

The caller supplies the exact Brave path and profile root through environment
variables.  The script does not discover browsers, inspect profile databases,
read cookies, or expose an owner identity/secret.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from jarvis.browser.playwright_adapter import PlaywrightBrowserController
from jarvis.browser.profile import BrowserProfilePolicy
from jarvis.contracts import BrowserAction, BrowserSessionMode, DeviceIdentity, Identity, ToolContext


async def _run() -> int:
    executable_path = os.environ.get("JARVIS_BROWSER_EXECUTABLE_PATH", "").strip()
    profile_root = os.environ.get("JARVIS_BROWSER_PROFILE_ROOT", "").strip()
    url = os.environ.get("JARVIS_BROWSER_T2_URL", "https://example.com").strip()
    if not executable_path or not profile_root:
        print(json.dumps({"status": "blocked", "error_code": "explicit_browser_path_and_profile_required"}))
        return 2
    identity = Identity("local-owner-session", "Local owner session", "local-owner")
    device = DeviceIdentity("local-owner-device", identity.owner_id, "desktop", "windows", frozenset(), frozenset())
    context = ToolContext(identity, device, "batch10-t2", "batch10-t2-profile-gate")
    policy = BrowserProfilePolicy(Path(profile_root), owner_persistent_opt_in=True)
    outcomes: list[dict[str, object]] = []
    for run_number in (1, 2):
        controller = PlaywrightBrowserController(
            executable_path=executable_path,
            headless=True,
            profile_policy=policy,
        )
        try:
            opened = await controller.execute(
                BrowserAction("open_url", {"url": url}),
                context,
                session_mode=BrowserSessionMode.OWNER_PERSISTENT,
            )
            outcomes.append({
                "run": run_number,
                "status": opened.status,
                "error_code": opened.error_code,
                "mode": opened.output.get("mode"),
                "url": opened.output.get("url"),
            })
            if opened.status != "succeeded":
                return_code = 1
            else:
                return_code = 0
        finally:
            await controller.close()
        if return_code:
            print(json.dumps({"status": "failed", "runs": outcomes}, sort_keys=True))
            return return_code
    print(json.dumps({"status": "pass", "runs": outcomes}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))

