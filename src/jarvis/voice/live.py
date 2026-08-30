"""Explicit entry point for the local physical voice workstation.

Run this module with the isolated local voice environment after supplying an
already-enrolled device credential through the process environment.  It never
bootstraps an owner, accepts a credential from the command line, or starts on
ordinary package import.
"""

from __future__ import annotations

import asyncio
import os

from ..bootstrap import create_runtime
from ..config import JarvisConfig
from ..contracts import VoiceSessionContext
from .config import VoiceRuntimeConfig
from .core import VoiceCore
from .runtime import LocalVoiceRuntime, build_local_voice_runtime


async def run() -> None:
    voice_config = VoiceRuntimeConfig.from_env()
    credential = os.getenv("JARVIS_VOICE_CREDENTIAL", "")
    identity_id = os.getenv("JARVIS_VOICE_IDENTITY_ID", "")
    configured_device_id = os.getenv("JARVIS_VOICE_DEVICE_ID", "")
    if not credential or not identity_id or not configured_device_id:
        raise RuntimeError(
            "JARVIS_VOICE_CREDENTIAL, JARVIS_VOICE_IDENTITY_ID, and JARVIS_VOICE_DEVICE_ID are required"
        )
    runtime = create_runtime(JarvisConfig.from_env())
    runner: LocalVoiceRuntime | None = None
    try:
        await runtime.start()
        device = await runtime.identity.authenticate(credential, configured_device_id)
        identity = await runtime.identity.get_identity(identity_id)
        if device is None or identity is None:
            raise RuntimeError("voice identity or enrolled device authentication failed")
        if identity.owner_id != device.owner_id:
            raise RuntimeError("voice identity/device owner binding mismatch")
        if not isinstance(runtime.voice, VoiceCore):
            raise RuntimeError("runtime did not compose the product VoiceCore")
        session = runtime.repository.create_session(identity.owner_id, device.device_id)
        conversation = runtime.repository.create_conversation(identity.owner_id, device.device_id, "Local voice")
        context = VoiceSessionContext(
            session_id=session.id,
            device_id=device.device_id,
            input_device=voice_config.input_device.name if voice_config.input_device else None,
            output_device=voice_config.output_device.name if voice_config.output_device else None,
            owner_id=identity.owner_id,
            endpoint_id="windows-local-voice",
            conversation_id=conversation.id,
        )
        runner = build_local_voice_runtime(runtime.voice, voice_config)
        await runner.start(context, identity, device)
        await asyncio.Event().wait()
    finally:
        if runner is not None:
            await runner.stop()
        if runtime.state.value == "ready":
            await runtime.shutdown()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
