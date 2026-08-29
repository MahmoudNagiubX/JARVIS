"""Run JARVIS locally without implicit model or network side effects."""

from __future__ import annotations

import asyncio
import argparse
import json

from .api.core import CoreApplication
from .api.http import CoreHttpServer
from .bootstrap import running_runtime
from .contracts import LLMMessage, LLMRequest, LLMRole
from .models.routing import ModelRoute


async def _main(args: argparse.Namespace) -> None:
    async with running_runtime() as runtime:
        application = CoreApplication(runtime)
        print(f"JARVIS runtime ready: {runtime.runtime_id}")
        if args.text is not None:
            principal = await application.ensure_demo_principal()
            result = await application.send_message(args.text, principal.identity, principal.device)
            print(json.dumps(result, ensure_ascii=False))
        if args.model_smoke:
            if runtime.config.model_provider != "ollama":
                print("MODEL SMOKE: NOT RUN (set JARVIS_MODEL_PROVIDER=ollama)")
            else:
                health = await runtime.models.health(ModelRoute.GENERAL_REASONING)
                if not health.available:
                    print(f"MODEL SMOKE: NOT RUN ({health.reason})")
                else:
                    request = LLMRequest(
                        "cli-model-smoke",
                        (LLMMessage(LLMRole.USER, "Reply with the single word ready."),),
                        max_output_tokens=16,
                        timeout_seconds=10,
                    )
                    response = await runtime.models.generate(request, ModelRoute.GENERAL_REASONING)
                    print(f"MODEL SMOKE: PASS ({response.model})")
        if args.serve:
            server = CoreHttpServer(application, port=args.port)
            print(f"JARVIS HTTP API listening on http://127.0.0.1:{server.address[1]}")
            try:
                await asyncio.to_thread(server.serve_forever)
            finally:
                server.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local JARVIS core runtime")
    parser.add_argument("--text", help="send one text message through the full runtime")
    parser.add_argument("--model-smoke", action="store_true", help="probe an already-running loopback model provider")
    parser.add_argument("--serve", action="store_true", help="serve the loopback HTTP API")
    parser.add_argument("--port", type=int, default=8787, help="loopback HTTP port")
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
