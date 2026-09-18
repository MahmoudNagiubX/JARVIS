"""Run JARVIS locally without implicit model or network side effects."""

from __future__ import annotations

import asyncio
import argparse
import json
import os
from pathlib import Path

from .api.core import CoreApplication
from .api.http import CoreHttpServer
from .bootstrap import running_runtime
from .config import JarvisConfig
from .contracts import LLMMessage, LLMRequest, LLMRole
from .models.routing import ModelRoute
from .models.probes import LocalModelCapabilityProbe
from .persistence.backup import SQLiteBackupService
from .persistence.db import SQLiteDatabase


async def _main(args: argparse.Namespace) -> None:
    async with running_runtime() as runtime:
        application = CoreApplication(runtime)
        print(f"JARVIS runtime ready: {runtime.runtime_id}")
        if args.text is not None:
            principal = await application.ensure_demo_principal()
            result = await application.send_message(args.text, principal.identity, principal.device)
            print(json.dumps(result, ensure_ascii=False))
        if args.model_smoke:
            if runtime.config.model_provider not in {"ollama", "gguf", "llama_cpp", "openai"}:
                print("MODEL SMOKE: NOT RUN (set an explicit local or OpenAI model provider)")
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
        if args.model_probe:
            result = await LocalModelCapabilityProbe(runtime.models).run(
                ModelRoute.GENERAL_REASONING,
                exercise_generation=args.model_exercise,
            )
            print(json.dumps(result.as_dict(), ensure_ascii=False))
        if args.status:
            print(json.dumps({
                "runtime": runtime.state.value,
                "database": runtime.config.database_path,
                "model_provider": runtime.config.model_provider,
                "model_primary": runtime.config.primary_model,
                "offline": runtime.offline.state.online is False,
                "event_count": runtime.repository.event_count(),
            }, ensure_ascii=False))
        node_server = None
        if args.serve_node:
            from .api.node_http import CoreNodeHttpServer
            node_server = CoreNodeHttpServer(
                application,
                host=args.node_host,
                port=args.node_port,
                allow_wildcard_bind=args.allow_wildcard_node_bind,
            )
            node_server.start()
            print(f"JARVIS Node HTTP adapter listening on http://{node_server.host}:{node_server.port}")

        try:
            if args.serve:
                server = CoreHttpServer(application, port=args.port)
                print(f"JARVIS HTTP API listening on http://127.0.0.1:{server.address[1]}")
                try:
                    await asyncio.to_thread(server.serve_forever)
                finally:
                    server.shutdown()
            elif args.serve_node:
                stop_event = asyncio.Event()
                await stop_event.wait()
        finally:
            if node_server is not None:
                node_server.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local JARVIS core runtime")
    parser.add_argument("--text", help="send one text message through the full runtime")
    parser.add_argument("--model-smoke", action="store_true", help="probe an already-running loopback model provider")
    parser.add_argument("--model-probe", action="store_true", help="inspect model health/capabilities without downloading")
    parser.add_argument("--model-exercise", action="store_true", help="send one bounded generation during --model-probe")
    parser.add_argument("--status", action="store_true", help="print runtime status")
    parser.add_argument("--serve", action="store_true", help="serve the loopback HTTP API")
    parser.add_argument("--port", type=int, default=8787, help="loopback HTTP port")
    parser.add_argument("--serve-node", action="store_true", help="serve the minimal authenticated node HTTP adapter")
    parser.add_argument("--node-host", default=os.getenv("JARVIS_NODE_HOST", "127.0.0.1"), help="node HTTP adapter bind host (default: 127.0.0.1)")
    parser.add_argument("--node-port", type=int, default=int(os.getenv("JARVIS_NODE_PORT", "8788")), help="node HTTP adapter bind port (default: 8788)")
    parser.add_argument("--allow-wildcard-node-bind", action="store_true", default=os.getenv("JARVIS_ALLOW_WILDCARD_NODE_BIND", "false").lower() in {"true", "1", "yes", "on"}, help="explicit opt-in to allow 0.0.0.0 or :: wildcard bind on node server")
    parser.add_argument("--backup", metavar="PATH", help="create an explicit SQLite backup")
    parser.add_argument("--verify-backup", metavar="PATH", help="verify an SQLite backup")
    parser.add_argument("--restore-backup", metavar="SOURCE", help="restore SOURCE to --restore-target")
    parser.add_argument("--restore-target", metavar="PATH", help="destination used with --restore-backup")
    parser.add_argument("--overwrite-restore", action="store_true", help="allow an explicit existing restore destination")
    args = parser.parse_args()
    maintenance = [bool(args.backup), bool(args.verify_backup), bool(args.restore_backup)]
    if sum(maintenance) > 1:
        parser.error("--backup, --verify-backup, and --restore-backup are mutually exclusive")
    if args.restore_target and not args.restore_backup:
        parser.error("--restore-target requires --restore-backup")
    if args.overwrite_restore and not args.restore_backup:
        parser.error("--overwrite-restore requires --restore-backup")
    if args.backup or args.verify_backup or args.restore_backup:
        config = JarvisConfig.from_env()
        if args.backup:
            source = Path(config.database_path).expanduser().resolve(strict=True)
            database = SQLiteDatabase(str(source))
            try:
                print(json.dumps(SQLiteBackupService(database).create(args.backup), ensure_ascii=False))
            finally:
                database.close()
        elif args.verify_backup:
            print(json.dumps(SQLiteBackupService.verify(args.verify_backup), ensure_ascii=False))
        else:
            if not args.restore_target:
                parser.error("--restore-backup requires --restore-target")
            print(json.dumps(SQLiteBackupService.restore(args.restore_backup, args.restore_target, overwrite=args.overwrite_restore), ensure_ascii=False))
        return
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
