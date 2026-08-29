"""Run the no-op foundation lifecycle for a local smoke check."""

from __future__ import annotations

import asyncio

from .bootstrap import running_runtime


async def _main() -> None:
    async with running_runtime() as runtime:
        print(f"JARVIS foundation ready: {runtime.runtime_id}")


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
