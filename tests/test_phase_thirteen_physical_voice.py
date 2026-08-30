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
    SoundDevicePlayback,
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
        self.start_speech = False
        self.reject_speech = False
        self._speech_active = False

    @property
    def speech_active(self) -> bool:
        return self._speech_active

    def feed(self, audio: bytes) -> bytes | None:
        del audio
        if self.start_speech:
            self.start_speech = False
            self._speech_active = True
        if self.reject_speech:
            self.reject_speech = False
            self._speech_active = False
            return None
        result, self.next_utterance = self.next_utterance, None
        if result is not None:
            self._speech_active = False
        return result

    def discard(self) -> None:
        self.discarded += 1
        self._speech_active = False


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


class _PlaybackBackend:
    def __init__(self) -> None:
        self.play_calls = 0
        self.wait_calls = 0

    def play(self, samples, **kwargs) -> None:
        del samples, kwargs
        self.play_calls += 1

    def wait(self) -> None:
        self.wait_calls += 1

    def stop(self) -> None:
        return None


class _BlockingGateway:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.calls = 0

    async def generate(self, request, route):
        del route
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            await asyncio.Event().wait()
        return LLMResponse(
            request.request_id,
            "new answer",
            "phase13-test-model",
            "stop",
            provider="mock",
        )


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

    async def test_wake_without_speech_times_out_to_sleeping_and_runs_no_agent(self) -> None:
        voice = self._voice()
        input_device, playback, wake, endpoint = _Input(), _Playback(), _Wake(), _Endpoint()
        runner = LocalVoiceRuntime(
            voice,
            input_device,
            playback,
            wake,
            endpoint,
            wake_command_timeout_seconds=0.05,
        )
        run_count = self.runtime.database.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        await runner.start(self.context, self.identity, self.device)
        wake.detected = True
        input_device.push(b"wake")
        await asyncio.sleep(0.09)
        self.assertEqual(voice.state, VoiceSessionState.SLEEPING)
        self.assertEqual(self.runtime.database.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], run_count)
        self.assertTrue(any(row["event_type"] == "voice.wake_timeout" for row in self.runtime.repository.events()))
        await runner.stop()

    async def test_speech_start_cancels_wake_timeout_and_can_continue_past_deadline(self) -> None:
        voice = self._voice()
        input_device, playback, wake, endpoint = _Input(), _Playback(), _Wake(), _Endpoint()
        runner = LocalVoiceRuntime(
            voice,
            input_device,
            playback,
            wake,
            endpoint,
            wake_command_timeout_seconds=0.06,
        )
        await runner.start(self.context, self.identity, self.device)
        wake.detected = True
        input_device.push(b"wake")
        await asyncio.sleep(0.02)
        endpoint.start_speech = True
        input_device.push(b"speech")
        await asyncio.sleep(0.09)
        self.assertTrue(endpoint.speech_active)
        self.assertFalse(runner.wake_command_timer_active)
        self.assertEqual(voice.state, VoiceSessionState.LISTENING)
        self.assertFalse(any(row["event_type"] == "voice.wake_timeout" for row in self.runtime.repository.events()))
        await runner.stop()

    async def test_rejected_initial_speech_sleeps_without_stt_or_agent_and_requires_fresh_wake(self) -> None:
        stt = _StaticStt()
        voice = self._voice(stt)
        input_device, playback, wake = _Input(), _Playback(), _Wake()
        endpoint = SpeechEndpointDetector(
            _SequenceVad([True] + [False] * 10),
            preroll_ms=320,
            min_speech_ms=240,
            end_silence_ms=800,
        )
        runner = LocalVoiceRuntime(
            voice,
            input_device,
            playback,
            wake,
            endpoint,
            wake_command_timeout_seconds=0.50,
        )
        frame = b"\x00\x00" * 1_280  # 80 ms at 16 kHz.
        run_count = self.runtime.database.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        await runner.start(self.context, self.identity, self.device)
        wake.detected = True
        await runner._process_pcm(frame)
        self.assertEqual(voice.state, VoiceSessionState.LISTENING)

        await runner._process_pcm(frame)
        self.assertTrue(endpoint.speech_active)
        self.assertFalse(runner.wake_command_timer_active)
        for _ in range(10):
            await runner._process_pcm(frame)

        self.assertEqual(voice.state, VoiceSessionState.SLEEPING)
        self.assertFalse(endpoint.speech_active)
        self.assertFalse(runner.wake_command_timer_active)
        self.assertEqual(stt.calls, 0)
        self.assertEqual(self.runtime.database.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], run_count)
        self.assertTrue(any(row["event_type"] == "voice.utterance_rejected" for row in self.runtime.repository.events()))

        await runner._process_pcm(frame)
        self.assertEqual(voice.state, VoiceSessionState.SLEEPING)
        self.assertEqual(stt.calls, 0)
        wake.detected = True
        await runner._process_pcm(frame)
        self.assertEqual(voice.state, VoiceSessionState.LISTENING)
        await runner.stop()

    async def test_new_wake_replaces_stale_command_timer(self) -> None:
        voice = self._voice()
        input_device, playback, wake, endpoint = _Input(), _Playback(), _Wake(), _Endpoint()
        runner = LocalVoiceRuntime(
            voice,
            input_device,
            playback,
            wake,
            endpoint,
            wake_command_timeout_seconds=0.12,
        )
        await runner.start(self.context, self.identity, self.device)
        wake.detected = True
        input_device.push(b"wake")
        await asyncio.sleep(0.08)
        wake.detected = True
        input_device.push(b"wake-again")
        await asyncio.sleep(0.07)
        self.assertEqual(voice.state, VoiceSessionState.LISTENING)
        await asyncio.sleep(0.08)
        self.assertEqual(voice.state, VoiceSessionState.SLEEPING)
        timeout_events = [row for row in self.runtime.repository.events() if row["event_type"] == "voice.wake_timeout"]
        self.assertEqual(len(timeout_events), 1)
        await runner.stop()

    async def test_stop_and_device_loss_cancel_wake_timeout(self) -> None:
        voice = self._voice()
        input_device, playback, wake, endpoint = _Input(), _Playback(), _Wake(), _Endpoint()
        runner = LocalVoiceRuntime(
            voice,
            input_device,
            playback,
            wake,
            endpoint,
            wake_command_timeout_seconds=0.05,
        )
        await runner.start(self.context, self.identity, self.device)
        wake.detected = True
        input_device.push(b"wake")
        await asyncio.sleep(0.02)
        await runner.stop()
        await asyncio.sleep(0.06)
        self.assertFalse(any(row["event_type"] == "voice.wake_timeout" for row in self.runtime.repository.events()))

        other_voice = self._voice()
        other_input, other_playback, other_wake, other_endpoint = _Input(), _Playback(), _Wake(), _Endpoint()
        other_runner = LocalVoiceRuntime(
            other_voice,
            other_input,
            other_playback,
            other_wake,
            other_endpoint,
            wake_command_timeout_seconds=0.05,
        )
        await other_runner.start(self.context, self.identity, self.device)
        other_wake.detected = True
        other_input.push(b"wake")
        await asyncio.sleep(0.02)
        await other_runner.recover_device(attempts=1)
        self.assertEqual(other_voice.state, VoiceSessionState.SLEEPING)
        timeout_events = [row for row in self.runtime.repository.events() if row["event_type"] == "voice.wake_timeout"]
        self.assertEqual(timeout_events, [])
        await other_runner.stop()

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

    async def test_empty_stt_restores_physical_and_historical_states_without_agent_run(self) -> None:
        blank = _StaticStt(VoiceTranscript("", True, "en"))
        physical = self._voice(blank)
        await physical.start(self.context, wake_enabled=True)
        await physical.wake_detected()
        run_count = self.runtime.database.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        result = await physical.process_audio(b"PCM", self.identity, self.device)
        assert result is not None
        self.assertEqual(result.state, VoiceSessionState.SLEEPING)
        self.assertEqual(self.runtime.database.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], run_count)
        await physical.stop()

        historical = self._voice(_StaticStt(VoiceTranscript("", False, None)))
        await historical.start(self.context)
        result = await historical.process_audio(b"PCM", self.identity, self.device)
        assert result is not None
        self.assertEqual(result.state, VoiceSessionState.LISTENING)
        self.assertEqual(self.runtime.database.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], run_count)
        await historical.stop()

    async def test_follow_up_empty_stt_preserves_bounded_expiry(self) -> None:
        stt = _StaticStt()
        voice = self._voice(stt)
        voice.follow_up_seconds = 0.10
        await voice.start(self.context, wake_enabled=True)
        await voice.wake_detected()
        await voice.process_transcript(VoiceTranscript("first", True, "en"), self.identity, self.device)
        stt.transcript = VoiceTranscript("", True, "en")
        result = await voice.process_audio(b"PCM", self.identity, self.device)
        assert result is not None
        self.assertEqual(result.state, VoiceSessionState.FOLLOW_UP)
        await asyncio.sleep(0.13)
        self.assertEqual(voice.state, VoiceSessionState.SLEEPING)
        await voice.stop()

    async def test_successful_second_turn_gets_a_full_fresh_follow_up_interval(self) -> None:
        voice = self._voice()
        voice.follow_up_seconds = 0.16
        await voice.start(self.context, wake_enabled=True)
        await voice.wake_detected()
        await voice.process_transcript(VoiceTranscript("first", True, "en"), self.identity, self.device)
        await asyncio.sleep(0.10)
        await voice.process_transcript(VoiceTranscript("second", True, "en"), self.identity, self.device)
        await asyncio.sleep(0.08)
        self.assertEqual(voice.state, VoiceSessionState.FOLLOW_UP)
        await asyncio.sleep(0.11)
        self.assertEqual(voice.state, VoiceSessionState.SLEEPING)
        await voice.stop()

    async def test_follow_up_speech_start_holds_expiry_until_accepted_turn_gets_fresh_window(self) -> None:
        stt = _StaticStt()
        voice = self._voice(stt)
        voice.follow_up_seconds = 0.16
        input_device, playback, wake, endpoint = _Input(), _Playback(), _Wake(), _Endpoint()
        runner = LocalVoiceRuntime(voice, input_device, playback, wake, endpoint)
        await runner.start(self.context, self.identity, self.device)
        await voice.wake_detected()
        await voice.process_transcript(VoiceTranscript("first", True, "en"), self.identity, self.device)

        await asyncio.sleep(0.11)
        endpoint.start_speech = True
        await runner._process_pcm(b"speech-start")
        self.assertTrue(endpoint.speech_active)
        await asyncio.sleep(0.08)
        self.assertEqual(voice.state, VoiceSessionState.FOLLOW_UP)

        endpoint.next_utterance = b"SECOND_FINAL_PCM"
        await runner._process_pcm(b"speech-end")
        assert runner._turn_task is not None
        await runner._turn_task
        self.assertEqual(stt.calls, 1)
        self.assertEqual(voice.state, VoiceSessionState.FOLLOW_UP)
        await asyncio.sleep(0.10)
        self.assertEqual(voice.state, VoiceSessionState.FOLLOW_UP)
        await asyncio.sleep(0.09)
        self.assertEqual(voice.state, VoiceSessionState.SLEEPING)
        await runner.stop()

    async def test_rejected_follow_up_restores_only_original_remaining_deadline(self) -> None:
        stt = _StaticStt()
        voice = self._voice(stt)
        voice.follow_up_seconds = 0.18
        input_device, playback, wake, endpoint = _Input(), _Playback(), _Wake(), _Endpoint()
        runner = LocalVoiceRuntime(voice, input_device, playback, wake, endpoint)
        await runner.start(self.context, self.identity, self.device)
        await voice.wake_detected()
        await voice.process_transcript(VoiceTranscript("first", True, "en"), self.identity, self.device)
        run_count = self.runtime.database.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

        await asyncio.sleep(0.11)
        endpoint.start_speech = True
        await runner._process_pcm(b"speech-start")
        await asyncio.sleep(0.02)
        endpoint.reject_speech = True
        await runner._process_pcm(b"rejected-end")
        self.assertEqual(voice.state, VoiceSessionState.FOLLOW_UP)
        self.assertEqual(stt.calls, 0)
        self.assertEqual(self.runtime.database.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], run_count)

        await asyncio.sleep(0.08)
        self.assertEqual(voice.state, VoiceSessionState.SLEEPING)
        expired = [row for row in self.runtime.repository.events() if row["event_type"] == "voice.follow_up_expired"]
        self.assertEqual(len(expired), 1)
        await runner.stop()

    async def test_empty_stt_after_reserved_follow_up_restores_remaining_deadline(self) -> None:
        stt = _StaticStt(VoiceTranscript("", True, "en"))
        voice = self._voice(stt)
        voice.follow_up_seconds = 0.18
        input_device, playback, wake, endpoint = _Input(), _Playback(), _Wake(), _Endpoint()
        runner = LocalVoiceRuntime(voice, input_device, playback, wake, endpoint)
        await runner.start(self.context, self.identity, self.device)
        await voice.wake_detected()
        await voice.process_transcript(VoiceTranscript("first", True, "en"), self.identity, self.device)
        run_count = self.runtime.database.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

        await asyncio.sleep(0.11)
        endpoint.start_speech = True
        await runner._process_pcm(b"speech-start")
        await asyncio.sleep(0.02)
        endpoint.next_utterance = b"EMPTY_STT_PCM"
        await runner._process_pcm(b"speech-end")
        assert runner._turn_task is not None
        await runner._turn_task
        self.assertEqual(stt.calls, 1)
        self.assertEqual(voice.state, VoiceSessionState.FOLLOW_UP)
        self.assertEqual(self.runtime.database.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], run_count)

        await asyncio.sleep(0.08)
        self.assertEqual(voice.state, VoiceSessionState.SLEEPING)
        await runner.stop()

    async def test_follow_up_hold_restore_cycles_have_one_expiry_and_stop_leaks_none(self) -> None:
        voice = self._voice()
        voice.follow_up_seconds = 0.12
        input_device, playback, wake, endpoint = _Input(), _Playback(), _Wake(), _Endpoint()
        runner = LocalVoiceRuntime(voice, input_device, playback, wake, endpoint)
        await runner.start(self.context, self.identity, self.device)
        await voice.wake_detected()
        await voice.process_transcript(VoiceTranscript("first", True, "en"), self.identity, self.device)

        await asyncio.sleep(0.04)
        for _ in range(2):
            endpoint.start_speech = True
            await runner._process_pcm(b"speech-start")
            endpoint.reject_speech = True
            await runner._process_pcm(b"rejected-end")
            self.assertEqual(voice.state, VoiceSessionState.FOLLOW_UP)
        await asyncio.sleep(0.10)
        self.assertEqual(voice.state, VoiceSessionState.SLEEPING)
        expired = [row for row in self.runtime.repository.events() if row["event_type"] == "voice.follow_up_expired"]
        self.assertEqual(len(expired), 1)

        await voice.wake_detected()
        await voice.process_transcript(VoiceTranscript("second", True, "en"), self.identity, self.device)
        endpoint.start_speech = True
        await runner._process_pcm(b"speech-start")
        await runner.stop()
        await asyncio.sleep(0.14)
        self.assertEqual(voice.state, VoiceSessionState.STOPPED)
        expired = [row for row in self.runtime.repository.events() if row["event_type"] == "voice.follow_up_expired"]
        self.assertEqual(len(expired), 1)

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

    async def test_paused_voice_turn_emits_safe_approval_and_sleeps(self) -> None:
        secret = "PHASE13_APPROVAL_SECRET"

        def handler(request):
            return LLMResponse(
                request.request_id,
                "",
                "phase13-test-model",
                "tool_calls",
                ({"function": {"name": "echo.consequential", "arguments": {"message": secret}}},),
                provider="mock",
            )

        self.runtime.agent.models = ModelGateway(
            self.runtime.config,
            {"mock": MockModelProvider(handler)},
        )
        tts, playback = _Tts(), _Playback()
        voice = self._voice(tts=tts, playback=playback)
        await voice.start(self.context, wake_enabled=True)
        await voice.wake_detected()
        result = await voice.process_transcript(
            VoiceTranscript("perform the consequential action", True, "en"),
            self.identity,
            self.device,
        )

        self.assertEqual(result.state, VoiceSessionState.SLEEPING)
        self.assertIsNotNone(result.run_id)
        run = self.runtime.repository.run(result.run_id or "")
        assert run is not None
        self.assertEqual(run.status, "paused")
        self.assertIsNotNone(run.pending_approval_id)
        self.assertEqual(tts.texts, [VoiceCore.APPROVAL_REQUIRED_MESSAGE])
        self.assertTrue(playback.played)
        approval_events = [
            row
            for row in self.runtime.repository.events()
            if row["event_type"] == "voice.approval_required"
        ]
        self.assertEqual(len(approval_events), 1)
        self.assertNotIn(secret, json.dumps(approval_events, default=str))
        await voice.stop()

    async def test_failed_wake_turn_returns_to_sleep_without_tts(self) -> None:
        def handler(request):
            return LLMResponse(
                request.request_id,
                "",
                "phase13-test-model",
                "stop",
                provider="mock",
            )

        self.runtime.agent.models = ModelGateway(
            self.runtime.config,
            {"mock": MockModelProvider(handler)},
        )
        tts = _Tts()
        voice = self._voice(tts=tts)
        await voice.start(self.context, wake_enabled=True)
        await voice.wake_detected()
        result = await voice.process_transcript(
            VoiceTranscript("empty model response", True, "en"),
            self.identity,
            self.device,
        )

        self.assertEqual(result.state, VoiceSessionState.SLEEPING)
        self.assertEqual(tts.texts, [])
        run = self.runtime.repository.run(result.run_id or "")
        assert run is not None
        self.assertEqual(run.status, "failed")
        await voice.stop()

    async def test_thinking_barge_cancels_real_agent_run_and_next_turn_is_clean(self) -> None:
        gateway = _BlockingGateway()
        self.runtime.agent.models = gateway
        tts, playback = _Tts(), _Playback()
        voice = self._voice(tts=tts, playback=playback)
        await voice.start(self.context, wake_enabled=True)
        await voice.wake_detected()
        first_task = asyncio.create_task(
            voice.process_transcript(
                VoiceTranscript("old turn", True, "en"),
                self.identity,
                self.device,
            )
        )
        await asyncio.wait_for(gateway.started.wait(), timeout=1)
        self.assertEqual(voice.state, VoiceSessionState.THINKING)
        self.assertTrue(await voice.barge_in())
        first = await asyncio.wait_for(first_task, timeout=1)

        self.assertTrue(first.interrupted)
        self.assertEqual(voice.state, VoiceSessionState.LISTENING)
        self.assertEqual(tts.texts, [])
        self.assertEqual(playback.played, [])
        self.assertTrue(
            any(row["event_type"] == "run.cancelled" for row in self.runtime.repository.events())
        )

        second = await voice.process_transcript(
            VoiceTranscript("new turn", True, "en"),
            self.identity,
            self.device,
        )
        self.assertEqual(second.response, "new answer")
        self.assertEqual(second.state, VoiceSessionState.FOLLOW_UP)
        self.assertEqual(tts.texts, ["new answer"])
        self.assertEqual(len(playback.played), 1)
        await voice.stop()

    async def test_playback_rejects_resampled_audio_over_hard_duration_bound(self) -> None:
        backend = _PlaybackBackend()
        playback = SoundDevicePlayback(
            VoiceDeviceSelector("Windows WASAPI", "Speakers"),
            max_duration_seconds=0.10,
        )
        playback._sounddevice = backend
        playback._device_index = 1
        playback.sample_rate = 16_000

        await playback.play(b"\x00\x00" * 1_000, 16_000)
        self.assertEqual(backend.play_calls, 1)
        self.assertEqual(backend.wait_calls, 1)
        with self.assertRaisesRegex(VoiceDeviceError, "voice_playback_too_long"):
            await playback.play(b"\x00\x00" * 2_000, 16_000)
        self.assertEqual(backend.play_calls, 1)
        self.assertEqual(backend.wait_calls, 1)

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
        self.assertEqual(config.wake_command_timeout_seconds, 5.0)
        with self.assertRaisesRegex(ValueError, "WAKE_COMMAND_TIMEOUT_SECONDS"):
            replace(config, wake_command_timeout_seconds=0.99).validated()
        with self.assertRaisesRegex(ValueError, "WAKE_COMMAND_TIMEOUT_SECONDS"):
            replace(config, wake_command_timeout_seconds=15.01).validated()
        self.assertNotIn("sounddevice", sys.modules)
        self.assertNotIn("faster_whisper", sys.modules)


if __name__ == "__main__":
    unittest.main()
