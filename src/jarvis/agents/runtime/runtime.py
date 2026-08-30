"""Bounded text-first agent loop with durable run state."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from ...bus import InMemoryEventBus
from ...contracts import DeviceIdentity, Identity, LLMMessage, LLMRequest, LLMRole, ToolContext, ToolResultRetention
from ...context.assembler import ContextAssembler
from ...events import Event, EventCategory, EventState
from ...models.gateway import ModelGateway
from ...models.routing import ModelRoute
from ...persistence.models import RunRecord
from ...persistence.repositories import RuntimeRepository
from ...tools.service import ToolCallResult, ToolExecutionService, ToolExecutionStatus
from ..routing.router import RequestRouter


class AgentRunState(StrEnum):
    SUCCEEDED = "succeeded"
    PAUSED = "paused"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class AgentRunOutcome:
    run_id: str
    conversation_id: str
    session_id: str
    state: AgentRunState
    response: str | None = None
    pending_approval_id: str | None = None
    assistant_message_id: str | None = None
    error_code: str | None = None
    replayed: bool = False
    context_snapshot: dict[str, object] | None = None


class AgentRuntime:
    """The only text path permitted to reach the model and tool services."""

    def __init__(
        self,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
        models: ModelGateway,
        tools: ToolExecutionService,
        *,
        max_steps: int = 3,
        context_assembler: ContextAssembler | None = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.models = models
        self.tools = tools
        self.router = RequestRouter()
        self.max_steps = max(1, min(max_steps, 10))
        self.context_assembler = context_assembler
        self._tasks: dict[str, asyncio.Task[AgentRunOutcome]] = {}
        self._cancelled: set[str] = set()

    async def process_text(
        self,
        text: str,
        identity: Identity,
        device: DeviceIdentity,
        *,
        session_id: str | None = None,
        conversation_id: str | None = None,
        client_message_id: str | None = None,
    ) -> AgentRunOutcome:
        content = text.strip()
        if not content:
            raise ValueError("message cannot be blank")
        if client_message_id:
            previous = self.repository.message_by_client_id(client_message_id)
            if previous is not None and previous.run_id:
                prior_run = self.repository.run(previous.run_id)
                if prior_run:
                    state = {
                        "succeeded": AgentRunState.SUCCEEDED,
                        "paused": AgentRunState.PAUSED,
                        "failed": AgentRunState.FAILED,
                        "cancelled": AgentRunState.CANCELLED,
                    }.get(prior_run.status, AgentRunState.FAILED)
                    return AgentRunOutcome(prior_run.id, prior_run.conversation_id, prior_run.session_id, state, replayed=True)
        if session_id is None:
            session = self.repository.create_session(identity.owner_id, device.device_id)
            session_id = session.id
        session = self.repository.session(session_id)
        if session is None or session.owner_id != identity.owner_id or session.device_id != device.device_id:
            raise ValueError("session owner/device binding mismatch")
        if conversation_id is None:
            conversation = self.repository.create_conversation(identity.owner_id, device.device_id, None)
            conversation_id = conversation.id
        conversation = self.repository.conversation(conversation_id)
        if conversation is None or conversation.owner_id != identity.owner_id:
            raise ValueError("conversation owner binding mismatch")
        message = self.repository.create_message(conversation_id, session_id, None, device.device_id, "user", content, client_message_id)
        run = self.repository.create_run(conversation_id, session_id, device.device_id, message.id, f"corr-{uuid4()}")
        self.repository.update_message_run_id(message.id, run.id)
        if self.context_assembler is not None:
            await self.context_assembler.capture_input(identity, content, message.id)
        return await self._execute(run.id, identity, device)

    async def resume(
        self,
        run_id: str,
        identity: Identity,
        device: DeviceIdentity,
        decided_by: str,
        *,
        approved: bool | None = None,
    ) -> AgentRunOutcome:
        run = self.repository.run(run_id)
        if run is None:
            raise KeyError(run_id)
        if run.request_device_id != device.device_id or run.status != "paused" or run.pending_approval_id is None:
            raise ValueError("run is not awaiting approval for this device")
        decision = await self.tools.approvals.get(run.pending_approval_id)
        if decision is None:
            raise ValueError("approval not found")
        context = ToolContext(identity, device, run.session_id, run.correlation_id)
        if decision.status.value == "pending":
            if approved is None:
                raise ValueError("approval decision is required before resume")
            decision = await self.tools.approvals.decide(run.pending_approval_id, approved, decided_by)
        approved_result = decision.status.value == "approved"
        if not approved_result:
            self.repository.update_run(run_id, status="failed", completed_at=datetime.now(UTC), failure_code="approval_denied", pending_approval_id=None)
            await self._emit("run.failed", EventCategory.AGENT, run, {"reason": "approval_denied"}, state=EventState.FAILED)
            return AgentRunOutcome(run.id, run.conversation_id, run.session_id, AgentRunState.FAILED, error_code="approval_denied")
        tool_result = await self.tools.decide_and_resume(run.pending_approval_id, True, decided_by, context)
        if tool_result.status is not ToolExecutionStatus.COMPLETED:
            self.repository.update_run(run_id, status="failed", completed_at=datetime.now(UTC), failure_code=tool_result.error_code, pending_approval_id=None)
            return AgentRunOutcome(run.id, run.conversation_id, run.session_id, AgentRunState.FAILED, error_code=tool_result.error_code)
        messages = [
            LLMMessage(
                LLMRole(item["role"]),
                item["content"] if isinstance(item.get("content"), str) else json.dumps(item.get("content"), ensure_ascii=False, default=str),
            )
            for item in run.context.get("messages", [])
        ]
        messages.append(LLMMessage(LLMRole.TOOL, json.dumps(tool_result.output, ensure_ascii=False, default=str)))
        ephemeral = {len(messages) - 1: tool_result} if tool_result.retention is ToolResultRetention.EPHEMERAL else {}
        self.repository.update_run(run_id, status="running", pending_approval_id=None, context_json=self._run_context(messages, None, ephemeral))
        return await self._execute(run_id, identity, device, messages_override=messages, ephemeral_results=ephemeral)

    async def cancel(self, run_id: str) -> AgentRunOutcome | None:
        run = self.repository.run(run_id)
        if run is None:
            return None
        self._cancelled.add(run_id)
        task = self._tasks.get(run_id)
        if task and task is not asyncio.current_task():
            task.cancel()
        self.repository.update_run(run_id, status="cancel_requested", cancel_requested_at=datetime.now(UTC))
        return AgentRunOutcome(run.id, run.conversation_id, run.session_id, AgentRunState.CANCELLED)

    async def _execute(
        self,
        run_id: str,
        identity: Identity,
        device: DeviceIdentity,
        *,
        messages_override: list[LLMMessage] | None = None,
        ephemeral_results: dict[int, ToolCallResult] | None = None,
    ) -> AgentRunOutcome:
        task = asyncio.current_task()
        if task:
            self._tasks[run_id] = task
        run = self.repository.run(run_id)
        if run is None:
            raise KeyError(run_id)
        self.repository.update_run(run_id, status="running", started_at=run.started_at or datetime.now(UTC))
        await self._emit("run.started", EventCategory.AGENT, run, {})
        try:
            messages = messages_override or self._history(run)
            ephemeral_results = dict(ephemeral_results or {})
            context_snapshot = await self.context_assembler.assemble(identity, device, messages[-1].content, session_id=run.session_id) if self.context_assembler else None
            for _step in range(self.max_steps):
                if run_id in self._cancelled:
                    raise asyncio.CancelledError
                request_id = f"model-request-{uuid4()}"
                request_messages = self._with_context(messages, context_snapshot)
                request = LLMRequest(
                    request_id,
                    tuple(request_messages),
                    max_output_tokens=512,
                    tools=self._tool_schemas(),
                )
                await self._emit("model.requested", EventCategory.MODEL, run, {"request_id": request_id})
                started = datetime.now(UTC)
                try:
                    route = ModelRoute.TOOL_ORCHESTRATION if any(message.role is LLMRole.TOOL for message in messages) else self.router.classify(messages[-1].content).model_route
                    response = await self.models.generate(request, route)
                except Exception as exc:
                    self.repository.update_run(run_id, status="failed", completed_at=datetime.now(UTC), failure_code=exc.__class__.__name__)
                    await self._emit("model.failed", EventCategory.MODEL, run, {"request_id": request_id, "error": exc.__class__.__name__}, state=EventState.FAILED)
                    return AgentRunOutcome(run.id, run.conversation_id, run.session_id, AgentRunState.FAILED, error_code=exc.__class__.__name__)
                self.repository.update_run(
                    run_id,
                    model_request_id=response.request_id,
                    model_id=response.model,
                    model_digest=response.model_digest,
                    finish_reason=response.finish_reason,
                    prompt_usage=response.usage.get("prompt_tokens"),
                    output_usage=response.usage.get("output_tokens"),
                    latency_ms=(datetime.now(UTC) - started).total_seconds() * 1000,
                )
                await self._emit("model.completed", EventCategory.MODEL, run, {"request_id": request_id, "model": response.model}, state=EventState.COMPLETED)
                if not response.tool_calls:
                    assistant = self.repository.create_message(run.conversation_id, run.session_id, run.id, None, "assistant", response.text)
                    self.repository.update_run(run_id, status="succeeded", completed_at=datetime.now(UTC), context_json=self._run_context(messages, context_snapshot, ephemeral_results))
                    await self._emit("run.completed", EventCategory.AGENT, run, {"assistant_message_id": assistant.id}, state=EventState.COMPLETED)
                    return AgentRunOutcome(run.id, run.conversation_id, run.session_id, AgentRunState.SUCCEEDED, response.text, assistant_message_id=assistant.id, context_snapshot=context_snapshot)
                context = ToolContext(identity, device, run.session_id, run.correlation_id)
                for proposal in response.tool_calls:
                    name, arguments = self._proposal(proposal)
                    tool_result = await self.tools.execute(name, arguments, context, run_id=run.id)
                    if tool_result.status is ToolExecutionStatus.APPROVAL_REQUIRED:
                        context_json = self._run_context(messages, context_snapshot, ephemeral_results)
                        self.repository.update_run(run_id, status="paused", pending_approval_id=tool_result.approval_id, context_json=context_json)
                        await self._emit("run.paused", EventCategory.AGENT, run, {"approval_id": tool_result.approval_id})
                        return AgentRunOutcome(run.id, run.conversation_id, run.session_id, AgentRunState.PAUSED, pending_approval_id=tool_result.approval_id, context_snapshot=context_snapshot)
                    messages.append(LLMMessage(LLMRole.TOOL, json.dumps(tool_result.output if tool_result.output is not None else {"error": tool_result.error_code}, ensure_ascii=False, default=str)))
                    if tool_result.retention is ToolResultRetention.EPHEMERAL:
                        ephemeral_results[len(messages) - 1] = tool_result
            self.repository.update_run(run_id, status="failed", completed_at=datetime.now(UTC), failure_code="max_agent_steps", context_json=self._run_context(messages, context_snapshot, ephemeral_results))
            return AgentRunOutcome(run.id, run.conversation_id, run.session_id, AgentRunState.FAILED, error_code="max_agent_steps", context_snapshot=context_snapshot)
        except asyncio.CancelledError:
            self.repository.update_run(run_id, status="cancelled", completed_at=datetime.now(UTC), failure_code="cancelled")
            await self._emit("run.cancelled", EventCategory.AGENT, run, {}, state=EventState.COMPLETED)
            return AgentRunOutcome(run.id, run.conversation_id, run.session_id, AgentRunState.CANCELLED, error_code="cancelled")
        finally:
            self._tasks.pop(run_id, None)
            self._cancelled.discard(run_id)

    def _history(self, run: RunRecord) -> list[LLMMessage]:
        history = [LLMMessage(LLMRole.SYSTEM, "You are JARVIS. Use only declared tools and report factual outcomes. When the user explicitly refers to the current screen/window/page and a perception tool is available, observe before answering. Never guess visual state.")]
        for message in self.repository.messages(run.conversation_id):
            if message.role in {"user", "assistant"}:
                history.append(LLMMessage(LLMRole(message.role), message.content))
        return history

    @staticmethod
    def _proposal(proposal: dict[str, Any]) -> tuple[str, dict[str, object]]:
        function = proposal.get("function") if isinstance(proposal.get("function"), dict) else proposal
        name = function.get("name")
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise ValueError("invalid_tool_proposal")
        return name, arguments

    def _tool_schemas(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.json_schema(),
                },
            }
            for spec in self.tools.registry.list()
        )

    @staticmethod
    def _with_context(messages: list[LLMMessage], snapshot: object | None) -> list[LLMMessage]:
        if snapshot is None:
            return list(messages)
        prompt = ContextAssembler.prompt(snapshot)
        if messages and messages[0].role is LLMRole.SYSTEM:
            return [messages[0], LLMMessage(LLMRole.SYSTEM, prompt), *messages[1:]]
        return [LLMMessage(LLMRole.SYSTEM, prompt), *messages]

    @staticmethod
    def _run_context(messages: list[LLMMessage], snapshot: object | None, ephemeral_results: dict[int, ToolCallResult] | None = None) -> dict[str, object]:
        ephemeral_results = ephemeral_results or {}
        persisted: list[dict[str, object]] = []
        for index, message in enumerate(messages):
            result = ephemeral_results.get(index)
            if result is None:
                persisted.append({"role": message.role.value, "content": message.content})
                continue
            try:
                output = json.loads(message.content)
            except (TypeError, ValueError, json.JSONDecodeError):
                output = message.content
            digest = hashlib.sha256(message.content.encode("utf-8")).hexdigest()
            observation_id = output.get("observation_id") if isinstance(output, dict) else None
            source = output.get("source") if isinstance(output, dict) else None
            if isinstance(output, dict) and isinstance(output.get("observation"), dict):
                observation_id = observation_id or output["observation"].get("observation_id")
                source = source or output["observation"].get("source")
            persisted.append({"role": message.role.value, "content": {"tool": result.name, "observation_id": observation_id, "retained": False, "content_digest": digest, "source": source or "ephemeral-tool"}})
        return {
            "messages": persisted,
            "context_snapshot": snapshot.as_dict() if snapshot is not None else None,
        }

    async def _emit(self, event_type: str, category: EventCategory, run: RunRecord, payload: dict[str, object], *, state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, category, correlation_id=run.correlation_id, session_id=run.session_id, actor_id=run.request_device_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
