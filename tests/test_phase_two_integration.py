from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime

from jarvis.api.core import CoreApplication
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.computer.controller import WindowsComputerController
from jarvis.config import JarvisConfig
from jarvis.contracts import (
    ComputerAction,
    LLMResponse,
    ToolContext,
    VoiceSessionContext,
    VoiceSessionState,
    VoiceTranscript,
)
from jarvis.devices.satellite.contracts import CommandObservation, SatelliteCommand, SatelliteHello
from jarvis.devices.satellite.registry import WindowsSatelliteRegistry
from jarvis.models.gateway import ModelGateway
from jarvis.models.providers import MockModelProvider
from jarvis.agents.workers import LocalWorkerRuntime, WorkerCategory, WorkerRequest, WorkerResult, WorkerStatus
from jarvis.voice.core import VoiceCore


class _SpeechToText:
    async def transcribe(self, audio: bytes) -> VoiceTranscript:
        self.audio = audio
        return VoiceTranscript("hello from voice", True, "en")


class _TextToSpeech:
    async def synthesize(self, text: str) -> bytes:
        return text.encode()


class _SlowTextToSpeech:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def synthesize(self, text: str) -> bytes:
        del text
        self.started.set()
        await self.release.wait()
        return b"audio"


class PhaseTwoIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Test Owner")
        enrollment = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                owner_id=self.identity.owner_id,
                display_name="Test Windows",
                device_kind="desktop",
                platform="windows",
                scopes=("tool.request",),
                capabilities=("computer.observe", "computer.input"),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(enrollment.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def test_text_flow_is_durable_and_idempotent(self) -> None:
        application = CoreApplication(self.runtime)
        result = await application.send_message("hello", self.identity, self.device, client_message_id="client-1")
        self.assertEqual(result["state"], "succeeded")
        self.assertTrue(result["response"])
        replay = await application.send_message("hello", self.identity, self.device, client_message_id="client-1")
        self.assertTrue(replay["replayed"])
        messages = self.runtime.repository.messages(result["conversation_id"])
        self.assertEqual([message.role for message in messages], ["user", "assistant"])
        event_types = [event["event_type"] for event in self.runtime.repository.events()]
        self.assertIn("model.completed", event_types)

    async def test_tool_allow_and_approval_resume_are_audited(self) -> None:
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        context = ToolContext(self.identity, self.device, session.id, "correlation-tools")
        allowed = await self.runtime.tool_service.execute("status.read", {}, context)
        self.assertEqual(allowed.status.value, "completed")
        self.assertEqual(allowed.output["state"], "ready")

        responses = [
            LLMResponse("request-1", "", "qwen3.5:4b", "tool_calls", ({"function": {"name": "echo.consequential", "arguments": {"message": "approved"}}},), provider="mock"),
            LLMResponse("request-2", "approval completed", "qwen3.5:4b", "stop", provider="mock"),
        ]

        def handler(request):
            response = responses.pop(0)
            return LLMResponse(request.request_id, response.text, request.model, response.finish_reason, response.tool_calls, response.usage, "mock")

        gateway = ModelGateway(self.runtime.config, {"mock": MockModelProvider(handler)})
        self.runtime.models = gateway
        self.runtime.agent.models = gateway
        paused = await self.runtime.agent.process_text("please echo", self.identity, self.device)
        self.assertEqual(paused.state.value, "paused")
        resumed = await self.runtime.agent.resume(paused.run_id, self.identity, self.device, self.identity.identity_id, approved=True)
        self.assertEqual(resumed.state.value, "succeeded")
        self.assertEqual(resumed.response, "approval completed")
        self.assertTrue(any(row["event_type"] == "tool.completed" for row in self.runtime.repository.audit()))
        self.assertTrue(any(row["event_type"] == "tool.completed" for row in self.runtime.repository.events()))

    async def test_permission_denies_missing_scope(self) -> None:
        denied_device = self.device.__class__(
            self.device.device_id,
            self.device.owner_id,
            self.device.device_kind,
            self.device.platform,
            self.device.capabilities,
            frozenset(),
            self.device.authenticated_at,
            self.device.credential_id,
        )
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        result = await self.runtime.tool_service.execute(
            "status.read", {}, ToolContext(self.identity, denied_device, session.id, "correlation-denied")
        )
        self.assertEqual(result.status.value, "denied")
        self.assertEqual(result.error_code, "scope_missing")

    async def test_application_health_is_transport_neutral(self) -> None:
        health = await CoreApplication(self.runtime).health()
        self.assertEqual(health["state"], "ready")
        self.assertEqual(health["model"]["provider"], "mock")

    async def test_voice_turn_and_barge_in(self) -> None:
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        context = VoiceSessionContext(session.id, self.device.device_id, "mic-1", "speaker-1", "room-1")
        voice = VoiceCore(self.runtime.agent, self.runtime.event_bus, _SpeechToText(), _TextToSpeech())
        await voice.start(context)
        result = await voice.process_audio(b"pcm", self.identity, self.device)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.state, VoiceSessionState.FOLLOW_UP)
        self.assertEqual(result.audio, b"Mock JARVIS response: hello from voice")
        await voice.stop()

        slow_tts = _SlowTextToSpeech()
        voice = VoiceCore(self.runtime.agent, self.runtime.event_bus, _SpeechToText(), slow_tts)
        await voice.start(context)
        task = asyncio.create_task(voice.process_audio(b"pcm", self.identity, self.device))
        await slow_tts.started.wait()
        self.assertTrue(await voice.barge_in())
        interrupted = await task
        assert interrupted is not None
        self.assertTrue(interrupted.interrupted)
        self.assertEqual(voice.state, VoiceSessionState.LISTENING)

    async def test_windows_satellite_is_typed_and_bounded(self) -> None:
        registry = WindowsSatelliteRegistry()

        async def handler(command: SatelliteCommand) -> CommandObservation:
            return CommandObservation(command.command_id, "completed", {"action": command.action})

        welcome = registry.register(
            SatelliteHello(self.device.device_id, self.device.owner_id, "Windows", "1.0", self.device.capabilities),
            self.device,
            handler,
        )
        self.assertTrue(welcome.accepted)
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        controller = WindowsComputerController(registry)
        result = await controller.execute(
            ComputerAction("observe", {"window": "active"}),
            ToolContext(self.identity, self.device, session.id, "correlation-satellite"),
        )
        self.assertEqual(result.status.value, "succeeded")
        with self.assertRaisesRegex(ValueError, "unsupported satellite capability"):
            await registry.execute(welcome.session_id, SatelliteCommand("bad", "shell", "shell.execute"))

    async def test_worker_is_bounded_and_reports_missing_adapter(self) -> None:
        workers = LocalWorkerRuntime()
        missing = await workers.run(WorkerRequest("research", WorkerCategory.RESEARCH))
        self.assertEqual(missing.status, WorkerStatus.FAILED)

        async def handler(request: WorkerRequest) -> WorkerResult:
            return WorkerResult("unused", WorkerStatus.SUCCEEDED, request.task, completed_at=datetime.now(UTC))

        workers = LocalWorkerRuntime({WorkerCategory.RESEARCH: handler})
        result = await workers.run(WorkerRequest("bounded task", WorkerCategory.RESEARCH))
        self.assertEqual(result.status, WorkerStatus.SUCCEEDED)
