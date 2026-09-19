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
from .contracts import LLMInputMedia, LLMMessage, LLMRequest, LLMRole
from .models.routing import ModelRoute
from .models.probes import LocalModelCapabilityProbe
from .persistence.backup import SQLiteBackupService
from .persistence.db import SQLiteDatabase


_MINIMAL_PNG_FIXTURE = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010804000000b51c0c02"
    "0000000b4944415478da6364f80f00010501012718e3660000000049454e44ae426082"
)


async def _run_provider_probe(runtime: object, provider_name: str) -> dict[str, object]:
    """Run one explicit cloud-provider acceptance call without exposing secrets."""

    routes = {"groq": ModelRoute.GENERAL_REASONING, "gemini": ModelRoute.VISION}
    if provider_name not in routes:
        raise ValueError("model provider probe must be groq or gemini")
    route = routes[provider_name]
    models = runtime.models
    selection = models.selection(route)
    architecture = models.architecture_snapshot()
    state = architecture.get(provider_name)
    state = state if isinstance(state, dict) else {}
    result: dict[str, object] = {
        "provider": provider_name,
        "model": selection.model,
        "state": state.get("state", "unknown"),
        "health_reason": state.get("reason", "provider_state_unavailable"),
        "generation_checked": False,
        "fallback_used": False,
        "result": "NOT_RUN",
    }
    # Missing/disabled credentials are an owner boundary, not a provider call.
    if state.get("state") != "configured_unprobed":
        result["result"] = "OWNER_ACTION_REQUIRED" if state.get("state") == "missing_key" else "NOT_RUN"
        return result

    if provider_name == "gemini":
        request = LLMRequest(
            "model-provider-probe-gemini",
            (LLMMessage(
                LLMRole.USER,
                "Inspect this tiny generated fixture and reply with one short word.",
                (LLMInputMedia("image/png", _MINIMAL_PNG_FIXTURE),),
            ),),
            model=selection.model,
            max_output_tokens=16,
            timeout_seconds=20,
        )
    else:
        request = LLMRequest(
            "model-provider-probe-groq",
            (LLMMessage(LLMRole.USER, "Reply with one short sentence confirming a bounded reasoning probe."),),
            model=selection.model,
            max_output_tokens=32,
            timeout_seconds=20,
        )
    try:
        response = await models.generate(request, route)
    except Exception as exc:  # Do not print provider exception text or headers.
        result.update({
            "generation_checked": True,
            "result": "FAIL",
            "error": exc.__class__.__name__,
        })
        return result
    actual_provider = response.provider or "unknown"
    result.update({
        "generation_checked": True,
        "actual_provider": actual_provider,
        "actual_model": response.model,
        "fallback_used": actual_provider != provider_name,
        "finish_reason": response.finish_reason,
        "nonempty": bool(response.text.strip() or response.tool_calls),
        "result": "PASS" if actual_provider == provider_name else "FALLBACK",
    })
    return result


async def _main(args: argparse.Namespace) -> None:
    async with running_runtime() as runtime:
        application = CoreApplication(runtime)
        print(f"JARVIS runtime ready: {runtime.runtime_id}")
        if args.text is not None:
            principal = await application.ensure_demo_principal()
            result = await application.send_message(args.text, principal.identity, principal.device)
            print(json.dumps(result, ensure_ascii=False))
        if args.model_smoke:
            if runtime.config.model_provider not in {"ollama", "gguf", "llama_cpp", "hybrid"}:
                print("MODEL SMOKE: NOT RUN (set an explicit local or hybrid model provider)")
            else:
                health = await runtime.models.health(ModelRoute.FAST_CONVERSATION)
                if not health.available:
                    print(f"MODEL SMOKE: NOT RUN ({health.reason})")
                else:
                    request = LLMRequest(
                        "cli-model-smoke",
                        (LLMMessage(LLMRole.USER, "Reply with the single word ready."),),
                        max_output_tokens=16,
                        timeout_seconds=10,
                    )
                    response = await runtime.models.generate(request, ModelRoute.FAST_CONVERSATION)
                    print(f"MODEL SMOKE: PASS ({response.model})")
        if args.model_probe:
            result = await LocalModelCapabilityProbe(runtime.models).run(
                ModelRoute.FAST_CONVERSATION,
                exercise_generation=args.model_exercise,
            )
            print(json.dumps(result.as_dict(), ensure_ascii=False))
        if args.model_architecture:
            print(json.dumps(runtime.models.architecture_snapshot(), ensure_ascii=False))
        if args.model_provider_probe:
            result = await _run_provider_probe(runtime, args.model_provider_probe)
            print(json.dumps(result, ensure_ascii=False))
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
    parser.add_argument("--model-architecture", action="store_true", help="print the safe three-model architecture snapshot")
    parser.add_argument("--model-provider-probe", choices=("groq", "gemini"), help="run one explicit live provider acceptance call")
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
