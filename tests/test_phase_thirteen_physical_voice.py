from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import LLMResponse, VoiceSessionContext, VoiceSessionState, VoiceTranscript
from jarvis.models.gateway import ModelGateway
from jarvis.models.providers import MockModelProvider
from jarvis.voice.adapters import (
    SpeechEndpointDetector,
    VoiceDeviceError,
    resolve_sounddevice_device,
    resample_pcm_16le,
)
from jarvis.voice.config import VoiceDeviceSelector, VoiceRuntimeConfig
from jarvis.voice.core import VoiceCore
from jarvis.voice.runtime import LocalVoiceRuntime, VoiceRunnerState


class _StaticStt:
    def __init__(self, transcript: VoiceTranscript | None = None) -> None:
        self.transcript = transcript or VoiceTranscript("voice request", True, "en")
        self.calls = 0

    async def transcribe(self, audio: bytes) -> VoiceTranscript:
        self.calls += 1
        self.last_audio = audio
        return self.transcript


class _Tts:
    sample_rate = 16_000

    def __init__(self, audio: bytes = b"tts") -> None:
        self.audio = audio
        self.texts: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.texts.append(text)
        return self.audio


class _SlowTts(_Tts):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def synthesize(self, text: str) -> bytes:
        self.texts.append(text)
        self.started.set()
        await self.release.wait()
        return self.audio


class _Playback:
    def __init__(self, block: bool = False) -> None:
        self.block = block
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.stopped = 0
        self.played: list[tuple[bytes, int]] = []
        self.started_output = False
        self.closed = False
        self.faulted = False

    def start(self) -> None:
        self.started_output = True

    async def play(self, audio: bytes, sample_rate: int) -> None:
        self.played.append((audio, sample_rate))
        self.started.set()
        if self.block:
            await self.release.wait()

    async def stop(self) -> None:
        self.stopped += 1
        self.release.set()

    def close(self) -> None:
        self.closed = True

    def take_fault(self) -> bool:
        result, self.faulted = self.faulted, False
        return result


class _Input:
    sample_rate = 16_000

    def __init__(self) -> None:
        self.callback = None
        self.started = 0
        self.stopped = 0
        self.faulted = False
        self.fail_starts = 0

    def start(self, callback) -> None:
        self.started += 1
        if self.fail_starts:
            self.fail_starts -= 1
            raise VoiceDeviceError("voice_device_missing")
        self.callback = callback

    def stop(self) -> None:
        self.stopped += 1

    def take_fault(self) -> bool:
        result, self.faulted = self.faulted, False
        return result

    def push(self, audio: bytes) -> None:
        assert self.callback is not None
        self.callback(audio)


class _Wake:
    def __init__(self) -> None:
        self.detected = False
        self.frames = 0

    def detect_pcm(self, audio: bytes) -> bool:
        self.frames += 1
        result, self.detected = self.detected, False
        return result


class _Endpoint:
    def __init__(self) -> None:
        self.next_utterance: bytes | None = None
        self.discarded = 0

    def feed(self, audio: bytes) -> bytes | None:
        del audio
        result, self.next_utterance = self.next_utterance, None
        return result

    def discard(self) -> None:
        self.discarded += 1


class _SequenceVad:
    def __init__(self, decisions: list[bool]) -> None:
        self.decisions = iter(decisions)
        self.resets = 0

    def is_speech(self, audio: bytes) -> bool:
        del audio
        return next(self.decisions, False)

    def reset(self) -> None:
        self.resets += 1


class _SoundDevice:
    def __init__(self, devices: list[dict[str, object]]) -> None:
        self.devices = devices

    def query_devices(self):
        return self.devices

    def query_hostapis(self):
        return [{"name": "Windows WASAPI"}, {"name": "MME"}]


class PhaseThirteenPhysicalVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Phase Thirteen Owner")
        grant = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                self.identity.owner_id,
                "Phase Thirteen Workstation",
                "desktop",
                "windows",
                ("tool.request",),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(grant.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        self.context = VoiceSessionContext(
            session.id,
            self.device.device_id,
            owner_id=self.identity.owner_id,
            conversation_id=self.runtime.repository.create_conversation(
                self.identity.owner_id, self.device.device_id, "voice"
            ).id,
        )

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    def _voice(self, stt: _StaticStt | None = None, tts: _Tts | None = None, playback: _Playback | None = None) -> VoiceCore:
        return VoiceCore(self.runtime.agent, self.runtime.event_bus, stt or _StaticStt(), tts or _Tts(), playback=playback)

    async def test_physical_runner_uses_the_single_runtime_voice_authority(self) -> None:
        self.assertIs(self.runtime.voice, self.runtime.notification_delivery.voice_core)
        self.assertIsInstance(self.runtime.voice, VoiceCore)
        stt, tts, input_device, playback, wake, endpoint = _StaticStt(), _Tts(), _Input(), _Playback(), _Wake(), _Endpoint()
        self.runtime.voice.configure_adapters(stt, tts, playback)
        runner = LocalVoiceRuntime(self.runtime.voice, input_device, playback, wake, endpoint)
        await runner.start(self.context, self.identity, self.device)
        self.assertEqual(self.runtime.voice.state, VoiceSessionState.SLEEPING)
        wake.detected = True
        input_device.push(b"wake")
        await asyncio.sleep(0.04)
        self.assertEqual(self.runtime.voice.state, VoiceSessionState.LISTENING)
        endpoint.next_utterance = b"FINAL_PCM"
        input_device.push(b"speech")
        await asyncio.sleep(0.08)
        self.assertEqual(stt.calls, 1)
        self.assertEqual(self.runtime.voice.state, VoiceSessionState.FOLLOW_UP)
        self.assertTrue(playback.played)
        await runner.stop()
        self.assertEqual(runner.state, VoiceRunnerState.STOPPED)

    async def test_wake_follow_up_and_expiry_are_physical_stateful(self) -> None:
        voice = self._voice()
        voice.follow_up_seconds = 0.05
        await voice.start(self.context, wake_enabled=True)
        self.assertEqual(voice.state, VoiceSessionState.SLEEPING)
        self.assertTrue(await voice.wake_detected())
        result = await voice.process_transcript(VoiceTranscript("hello", True, "en"), self.identity, self.device)
        self.assertEqual(result.state, VoiceSessionState.FOLLOW_UP)
        await asyncio.sleep(0.08)
        self.assertEqual(voice.state, VoiceSessionState.SLEEPING)
        await voice.stop()

    async def test_follow_up_accepts_second_turn_without_another_wake(self) -> None:
        voice = self._voice()
        await voice.start(self.context, wake_enabled=True)
        await voice.wake_detected()
        first = await voice.process_transcript(VoiceTranscript("first", True, "en"), self.identity, self.device)
        self.assertEqual(first.state, VoiceSessionState.FOLLOW_UP)
        second = await voice.process_transcript(VoiceTranscript("second", True, "en"), self.identity, self.device)
        self.assertEqual(second.state, VoiceSessionState.FOLLOW_UP)
        await voice.stop()

    async def test_wrong_owner_and_wrong_context_fail_before_stt(self) -> None:
        stt = _StaticStt()
        voice = self._voice(stt)
        await voice.start(self.context, wake_enabled=True)
        await voice.wake_detected()
        with self.assertRaisesRegex(ValueError, "owner binding mismatch"):
            await voice.process_audio(b"PCM", replace(self.identity, owner_id="spoof-owner"), self.device)
        self.assertEqual(stt.calls, 0)
        with self.assertRaisesRegex(ValueError, "voice device does not match"):
            await voice.process_audio(b"PCM", self.identity, replace(self.device, device_id="wrong-device"))
        self.assertEqual(stt.calls, 0)
        await voice.stop()

    async def test_final_transcript_is_durable_but_pcm_partial_and_tts_are_not(self) -> None:
        pcm_sentinel = b"PCM_SENTINEL_PHASE13"
        tts_sentinel = b"TTS_SENTINEL_PHASE13"
        partial = _StaticStt(VoiceTranscript("PARTIAL_SENTINEL_PHASE13", False, "en"))
        voice = self._voice(partial, _Tts(tts_sentinel))
        await voice.start(self.context)
        partial_result = await voice.process_audio(pcm_sentinel, self.identity, self.device)
        assert partial_result is not None
        self.assertEqual(voice.state, VoiceSessionState.LISTENING)
        final = _StaticStt(VoiceTranscript("final voice request", True, "en"))
        # A fresh core avoids mutating an active session while preserving the same AgentRuntime authority.
        await voice.stop()
        voice = self._voice(final, _Tts(tts_sentinel))
        await voice.start(self.context)
        await voice.process_audio(pcm_sentinel, self.identity, self.device)
        durable = json.dumps(
            {
                "events": self.runtime.repository.events(),
                "audit": self.runtime.repository.audit(),
                "messages": [message.content for message in self.runtime.repository.messages(self.context.conversation_id or "")],
                "world": self.runtime.repository.world_facts(self.identity.owner_id),
            },
            default=str,
        )
        self.assertNotIn(pcm_sentinel.decode(), durable)
        self.assertNotIn(tts_sentinel.decode(), durable)
        self.assertNotIn("PARTIAL_SENTINEL_PHASE13", durable)
        self.assertIn("final voice request", durable)
        await voice.stop()

    async def test_barge_in_cancels_synthesis_and_playback_without_old_audio(self) -> None:
        slow_tts, playback = _SlowTts(), _Playback(block=True)
        voice = self._voice(tts=slow_tts, playback=playback)
        await voice.start(self.context, wake_enabled=True)
        await voice.wake_detected()
        task = asyncio.create_task(voice.process_transcript(VoiceTranscript("interrupt me", True, "en"), self.identity, self.device))
        await slow_tts.started.wait()
        self.assertTrue(await voice.barge_in())
        result = await task
        self.assertTrue(result.interrupted)
        self.assertEqual(voice.state, VoiceSessionState.LISTENING)
        self.assertFalse(playback.played)
        await voice.stop()

    async def test_barge_in_stops_active_playback(self) -> None:
        playback = _Playback(block=True)
        voice = self._voice(playback=playback)
        await voice.start(self.context, wake_enabled=True)
        await voice.wake_detected()
        task = asyncio.create_task(voice.process_transcript(VoiceTranscript("play", True, "en"), self.identity, self.device))
        await playback.started.wait()
        self.assertTrue(await voice.barge_in())
        result = await task
        self.assertTrue(result.interrupted)
        self.assertGreaterEqual(playback.stopped, 1)
        self.assertEqual(voice.state, VoiceSessionState.LISTENING)
        await voice.stop()

    async def test_runner_queue_is_bounded_and_device_recovery_uses_configured_input_only(self) -> None:
        voice = self._voice()
        input_device, playback, wake, endpoint = _Input(), _Playback(), _Wake(), _Endpoint()
        runner = LocalVoiceRuntime(voice, input_device, playback, wake, endpoint)
        for _ in range(runner.queue_capacity + 3):
            runner._capture_callback(b"frame")
        self.assertEqual(runner._pcm.qsize(), runner.queue_capacity)
        self.assertEqual(runner.queue_overruns, 3)
        await runner.start(self.context, self.identity, self.device)
        input_device.faulted = True
        await asyncio.sleep(0.35)
        self.assertGreaterEqual(input_device.started, 2)
        self.assertEqual(runner.state, VoiceRunnerState.RUNNING)
        await runner.stop()

    async def test_runner_recovers_only_the_configured_output_after_playback_loss(self) -> None:
        voice = self._voice()
        input_device, playback, wake, endpoint = _Input(), _Playback(), _Wake(), _Endpoint()
        runner = LocalVoiceRuntime(voice, input_device, playback, wake, endpoint)
        await runner.start(self.context, self.identity, self.device)
        playback.faulted = True
        await asyncio.sleep(0.35)
        self.assertTrue(playback.closed)
        self.assertTrue(playback.started_output)
        self.assertEqual(runner.state, VoiceRunnerState.RUNNING)
        await runner.stop()

    async def test_spoken_yes_cannot_resume_an_existing_approval(self) -> None:
        responses = [
            LLMResponse(
                "approval-request",
                "",
                "phase13-test-model",
                "tool_calls",
                ({"function": {"name": "echo.consequential", "arguments": {"message": "pending"}}},),
                provider="mock",
            ),
            LLMResponse("voice-yes", "I cannot approve that by voice.", "phase13-test-model", "stop", provider="mock"),
        ]

        def handler(request):
            response = responses.pop(0)
            return LLMResponse(
                request.request_id,
                response.text,
                response.model,
                response.finish_reason,
                response.tool_calls,
                response.usage,
                "mock",
            )

        gateway = ModelGateway(self.runtime.config, {"mock": MockModelProvider(handler)})
        self.runtime.agent.models = gateway
        paused = await self.runtime.agent.process_text("please echo a consequential message", self.identity, self.device)
        self.assertEqual(paused.state.value, "paused")
        voice = self._voice()
        await voice.start(self.context)
        await voice.process_transcript(VoiceTranscript("yes", True, "en"), self.identity, self.device)
        run = self.runtime.repository.run(paused.run_id)
        assert run is not None
        self.assertEqual(run.status, "paused")
        await voice.stop()

    def test_device_selector_is_exact_and_never_uses_a_persisted_numeric_id(self) -> None:
        selector = VoiceDeviceSelector("Windows WASAPI", "Microphone Array")
        devices = [
            {"hostapi": 0, "name": "Microphone Array", "max_input_channels": 2, "max_output_channels": 0},
            {"hostapi": 1, "name": "Microphone Array", "max_input_channels": 2, "max_output_channels": 0},
        ]
        self.assertEqual(resolve_sounddevice_device(_SoundDevice(devices), selector, "input"), 0)
        with self.assertRaisesRegex(VoiceDeviceError, "voice_device_missing"):
            resolve_sounddevice_device(_SoundDevice(devices), selector, "output")
        duplicated = devices + [dict(devices[0])]
        with self.assertRaisesRegex(VoiceDeviceError, "voice_device_ambiguous"):
            resolve_sounddevice_device(_SoundDevice(duplicated), selector, "input")

    def test_vad_endpointing_has_bounded_preroll_and_no_partial_return(self) -> None:
        vad = _SequenceVad([False, False, True, True, True, False, False, False, False, False, False, False, False, False, False])
        endpoint = SpeechEndpointDetector(vad, preroll_ms=320, min_speech_ms=240, end_silence_ms=800)
        frames = [b"x" * 2560 for _ in range(15)]  # 80 ms of 16 kHz mono PCM each
        result = None
        for frame in frames:
            result = endpoint.feed(frame)
            if result is not None:
                break
        self.assertIsNotNone(result)
        assert result is not None
        self.assertLessEqual(len(result), int(20 * 16_000 * 2))
        self.assertGreaterEqual(vad.resets, 1)

    def test_in_memory_resampling_normalizes_realtek_style_48khz_to_stt_rate(self) -> None:
        source = (b"\x01\x00" * 4_800)
        normalized = resample_pcm_16le(source, 48_000, 16_000)
        self.assertEqual(len(normalized), len(source) // 3)

    def test_disabled_config_is_safe_and_optional_audio_imports_are_not_loaded(self) -> None:
        with patch.dict(os.environ, {"JARVIS_VOICE_ENABLED": "false"}, clear=True):
            config = VoiceRuntimeConfig.from_env()
        self.assertFalse(config.enabled)
        self.assertNotIn("sounddevice", sys.modules)
        self.assertNotIn("faster_whisper", sys.modules)


if __name__ == "__main__":
    unittest.main()
