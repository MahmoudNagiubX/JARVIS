from __future__ import annotations

import json
import unittest
from dataclasses import replace

from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.agents.runtime.runtime import AgentRuntime
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import LLMMessage, LLMRequest, LLMResponse, LLMRole, VoiceSessionContext, VoiceTranscript
from jarvis.models.gateway import ModelGateway
from jarvis.models.providers import LlamaCppProvider, MockModelProvider, ModelProviderError
from jarvis.models.routing import ModelRoute
from jarvis.tools.selection import ToolSchemaSelector, normalize_intent


class PhaseTwelveFinalClosureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Phase Twelve Closure Owner")
        grant = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                self.identity.owner_id,
                "Phase Twelve Closure Desktop",
                "desktop",
                "windows",
                ("tool.request",),
                ("computer.observe", "perception.screen"),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(grant.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    def _mock_gateway(self, responses: list[LLMResponse], requests: list[LLMRequest] | None = None) -> ModelGateway:
        def handler(request: LLMRequest) -> LLMResponse:
            if requests is not None:
                requests.append(request)
            response = responses.pop(0)
            return LLMResponse(
                request.request_id,
                response.text,
                response.model or request.model or "phase12-test-model",
                response.finish_reason,
                response.tool_calls,
                response.usage,
                "mock",
                response.model_digest,
            )

        return ModelGateway(self.runtime.config, {"mock": MockModelProvider(handler)})

    @staticmethod
    def _names(schemas: tuple[dict[str, object], ...]) -> tuple[str, ...]:
        return tuple(schema["function"]["name"] for schema in schemas)

    def test_bilingual_selector_matrix_is_bounded_and_keeps_ordinary_chat_tool_free(self) -> None:
        selector = ToolSchemaSelector(self.runtime.tools)
        visual_cases = (
            "شوف الشاشة",
            "إيه اللي قدامي؟",
            "أيه اللي قدامي؟",
            "شوف الscreen",
        )
        for intent in visual_cases:
            with self.subTest(intent=intent):
                self.assertEqual(self._names(selector.select(intent)), ToolSchemaSelector.ARABIC_METADATA_TOOLS)
        desktop_schema = selector.select("شوف الشاشة")[0]
        self.assertIn("current screen's active application", desktop_schema["function"]["description"])
        english_visual = selector.select("what is on my current screen")
        self.assertEqual(self._names(english_visual), ToolSchemaSelector.VISUAL_TOOLS)
        self.assertIn("Do not call this for identifying the active application or window", english_visual[1]["function"]["description"])

        mixed_visual = self._names(selector.select("بص على الwindow"))
        self.assertLessEqual(len(mixed_visual), ToolSchemaSelector.MAX_MODEL_TOOLS)
        self.assertIn("desktop.context.read", mixed_visual)
        self.assertIn("computer.window.control", mixed_visual)

        computer_cases = ("اكتب الكلام ده", "type الكلام ده")
        for intent in computer_cases:
            with self.subTest(intent=intent):
                self.assertEqual(self._names(selector.select(intent)), ToolSchemaSelector.COMPUTER_TOOLS)
        self.assertEqual(self._names(selector.select("what type of network is this?")), ())

        self.assertIn("computer.audio.adjust", self._names(selector.select("وطي الصوت")))
        self.assertIn("computer.audio.adjust", self._names(selector.select("علي الvolume")))
        self.assertIn("computer.clipboard.read", self._names(selector.select("حط في الكليب بورد")))
        self.assertIn("computer.clipboard.write", self._names(selector.select("حطه في الclipboard")))
        self.assertEqual(self._names(selector.select("قولي حالتك")), ToolSchemaSelector.STATUS_TOOLS)
        self.assertEqual(self._names(selector.select("check الstatus")), ToolSchemaSelector.STATUS_TOOLS)

        for intent in ("run the tests", "run tests", "test the project", "execute tests", "unit tests", "شغل التستات", "رن التستات", "شغل tests", "اعمل test للمشروع", "اختبر المشروع", "شغل الunit tests"):
            with self.subTest(intent=intent):
                self.assertEqual(self._names(selector.select(intent)), ToolSchemaSelector.ENGINEERING_TOOLS)

        for intent in ("شوف الشاشة وقولي الحالة", "شوف الscreen and check الstatus", "type الكلام ده في الwindow"):
            with self.subTest(intent=intent):
                self.assertLessEqual(len(selector.select(intent)), ToolSchemaSelector.MAX_MODEL_TOOLS)
        for intent in ("عامل ايه؟", "احكيلي نكتة", "اشرحلي machine learning", "صباح الخير", "tell me a joke"):
            with self.subTest(intent=intent):
                self.assertEqual(selector.select(intent), ())

    def test_selector_normalization_is_conservative_and_does_not_change_user_text(self) -> None:
        original = "  إيه الــشَّاشة؟  "
        self.assertEqual(normalize_intent(original), "ايه الشاشة؟")
        self.assertEqual(original, "  إيه الــشَّاشة؟  ")

    def test_tool_output_cannot_expand_second_turn_schema_selection(self) -> None:
        user_intent = LLMMessage(LLMRole.USER, "tell me a joke")
        tool_output = LLMMessage(LLMRole.TOOL, "clipboard اكتب screen")
        messages = [LLMMessage(LLMRole.SYSTEM, "system"), user_intent, tool_output]
        self.assertEqual(self._names(self.runtime.agent._selected_tool_schemas(messages)), ())

    async def test_selector_is_bounded_exact_registered_and_stable_for_tool_turn(self) -> None:
        selector = ToolSchemaSelector(self.runtime.tools)
        self.assertEqual(selector.select("tell me a short joke"), ())
        visual = selector.select("what is on my current screen")
        self.assertEqual(
            tuple(schema["function"]["name"] for schema in visual),
            ToolSchemaSelector.VISUAL_TOOLS,
        )
        self.assertLessEqual(len(visual), ToolSchemaSelector.MAX_MODEL_TOOLS)
        self.assertTrue(all(self.runtime.tools.get(schema["function"]["name"]) is not None for schema in visual))
        original = tuple(schema["function"]["name"] for schema in visual)
        second_turn = selector.select("what is on my current screen")
        self.assertEqual(original, tuple(schema["function"]["name"] for schema in second_turn))

    async def test_large_desktop_tool_evidence_is_bounded_but_active_window_is_preserved(self) -> None:
        output = {
            "status": "completed",
            "context": {
                "active_window": {"process_name": "active-app.exe", "title": "JARVIS"},
                "windows": [{"process_name": f"background-{index}.exe", "title": "x" * 300} for index in range(50)],
            },
        }
        bounded = AgentRuntime._bounded_tool_message(output)
        self.assertLessEqual(len(bounded), AgentRuntime.MAX_TOOL_MESSAGE_CHARS)
        self.assertIn("active-app.exe", bounded)
        self.assertIn('"count":50', bounded)
        truncated = AgentRuntime._bounded_tool_message({"huge": "x" * 10000})
        self.assertLessEqual(len(truncated), AgentRuntime.MAX_TOOL_MESSAGE_CHARS)
        self.assertTrue(json.loads(truncated)["truncated"])

    async def test_empty_no_tool_response_fails_truthfully_without_assistant_message(self) -> None:
        gateway = self._mock_gateway([LLMResponse("ignored", "", "phase12-test-model", "stop")])
        self.runtime.models = gateway
        self.runtime.agent.models = gateway
        outcome = await self.runtime.agent.process_text("ordinary chat", self.identity, self.device)
        self.assertEqual(outcome.state.value, "failed")
        self.assertEqual(outcome.error_code, "model_empty_response")
        messages = self.runtime.repository.messages(outcome.conversation_id)
        self.assertEqual([message.role for message in messages], ["user"])
        self.assertTrue(any(row["event_type"] == "run.failed" for row in self.runtime.repository.events()))

    async def test_blank_tool_response_remains_valid_and_second_turn_uses_same_selection(self) -> None:
        requests: list[LLMRequest] = []
        gateway = self._mock_gateway(
            [
                LLMResponse(
                    "ignored",
                    "",
                    "phase12-test-model",
                    "tool_calls",
                    ({"function": {"name": "status.read", "arguments": {}}},),
                ),
                LLMResponse("ignored", "Status is ready.", "phase12-test-model", "stop"),
            ],
            requests,
        )
        self.runtime.models = gateway
        self.runtime.agent.models = gateway
        outcome = await self.runtime.agent.process_text("tell me the current status", self.identity, self.device)
        self.assertEqual(outcome.state.value, "succeeded")
        self.assertEqual(outcome.response, "Status is ready.")
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].tools, requests[1].tools)
        self.assertEqual(tuple(schema["function"]["name"] for schema in requests[0].tools), ("status.read",))
        self.assertTrue(any("JARVIS context" in message.content for message in requests[0].messages))
        self.assertFalse(any("JARVIS context" in message.content for message in requests[1].messages))
        run = self.runtime.repository.run(outcome.run_id)
        assert run is not None
        event_types = [row["event_type"] for row in self.runtime.repository.events(run.correlation_id)]
        self.assertIn("tool.completed", event_types)

    async def test_nonempty_no_tool_response_succeeds(self) -> None:
        gateway = self._mock_gateway([LLMResponse("ignored", "A bounded answer.", "phase12-test-model", "stop")])
        self.runtime.models = gateway
        self.runtime.agent.models = gateway
        outcome = await self.runtime.agent.process_text("ordinary chat", self.identity, self.device)
        self.assertEqual(outcome.state.value, "succeeded")
        self.assertEqual(outcome.response, "A bounded answer.")
        self.assertIsNotNone(outcome.assistant_message_id)

    async def test_queue_idempotency_and_owner_thread_binding_remain_fail_closed(self) -> None:
        gateway = self._mock_gateway([LLMResponse("ignored", "one answer", "phase12-test-model", "stop")])
        self.runtime.models = gateway
        self.runtime.agent.models = gateway
        first = await self.runtime.agent.process_text(
            "ordinary chat", self.identity, self.device, client_message_id="phase12-client-1"
        )
        replay = await self.runtime.agent.process_text(
            "ordinary chat", self.identity, self.device, client_message_id="phase12-client-1"
        )
        self.assertTrue(replay.replayed)
        self.assertEqual(first.run_id, replay.run_id)

        wrong_device = replace(self.device, owner_id="owner-spoof")
        with self.assertRaisesRegex(ValueError, "identity/device owner binding mismatch"):
            await self.runtime.agent.process_text("ordinary chat", self.identity, wrong_device)

        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        other_owner_id = self.runtime.repository.create_owner("Other Phase Twelve Owner")
        other_conversation = self.runtime.repository.create_conversation(other_owner_id, self.device.device_id, None)
        with self.assertRaisesRegex(ValueError, "conversation owner binding mismatch"):
            await self.runtime.agent.process_text(
                "ordinary chat",
                self.identity,
                self.device,
                session_id=session.id,
                conversation_id=other_conversation.id,
            )

    async def test_voice_core_is_single_runtime_authority_and_rejects_spoofed_device(self) -> None:
        self.assertIs(self.runtime.voice, self.runtime.notification_delivery.voice_core)
        await self.runtime.voice.start(
            VoiceSessionContext("phase12-voice", self.device.device_id, owner_id=self.identity.owner_id)
        )
        with self.assertRaisesRegex(ValueError, "voice owner does not match"):
            await self.runtime.voice.process_transcript(
                VoiceTranscript("spoof", True),
                self.identity,
                replace(self.device, owner_id="owner-spoof"),
            )
        await self.runtime.voice.stop()

    async def test_vision_route_is_truthfully_unsupported_by_local_text_model(self) -> None:
        provider = LlamaCppProvider("http://127.0.0.1:8080")
        gateway = ModelGateway(JarvisConfig(environment="test", model_provider="llama_cpp"), {"llama_cpp": provider})
        request = LLMRequest("phase12-route", (LLMMessage(LLMRole.USER, "inspect image"),))
        with self.assertRaisesRegex(ModelProviderError, "model_route_unsupported"):
            await gateway.generate(request, ModelRoute.VISION)


if __name__ == "__main__":
    unittest.main()
