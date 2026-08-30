"""Command-line entry point for the bounded Windows satellite agent."""

from __future__ import annotations

import argparse
import asyncio
import os

from .agent import SatelliteAgentConfig, WindowsSatelliteAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the JARVIS typed Windows satellite agent")
    parser.add_argument("--core-url", default=os.getenv("JARVIS_CORE_URL"))
    parser.add_argument("--owner-id", default=os.getenv("JARVIS_OWNER_ID"))
    parser.add_argument("--identity-id", default=os.getenv("JARVIS_IDENTITY_ID"))
    parser.add_argument("--device-id", default=os.getenv("JARVIS_NODE_ID"))
    parser.add_argument("--credential", default=os.getenv("JARVIS_SATELLITE_CREDENTIAL"), help="credential held in memory only")
    parser.add_argument("--capability", action="append", dest="capabilities", default=None)
    parser.add_argument("--software-version", default="phase09")
    args = parser.parse_args()
    required = {name: getattr(args, name) for name in ("core_url", "owner_id", "identity_id", "device_id", "credential")}
    missing = [name for name, value in required.items() if not value]
    if missing:
        parser.error("missing required settings: " + ", ".join(missing))
    config = SatelliteAgentConfig(
        args.core_url,
        args.owner_id,
        args.identity_id,
        args.device_id,
        frozenset(args.capabilities or ("computer.observe",)),
        args.software_version,
    )
    asyncio.run(WindowsSatelliteAgent(config, args.credential).run_forever())


if __name__ == "__main__":
    main()
