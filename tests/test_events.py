from __future__ import annotations

import asyncio
import unittest

from jarvis.bus import InMemoryEventBus
from jarvis.events import Event, EventCategory, EventState


class EventTests(unittest.IsolatedAsyncioTestCase):
    async def test_event_envelope_carries_trace_metadata(self) -> None:
        event = Event.create(
            "tool.call.proposed",
            EventCategory.TOOL,
            correlation_id="corr-1",
            causation_id="event-0",
            session_id="session-1",
            actor_id="owner-1",
            payload={"name": "observe"},
        )
        self.assertEqual(event.correlation_id, "corr-1")
        self.assertEqual(event.causation_id, "event-0")
        self.assertEqual(event.category, EventCategory.TOOL)
        self.assertEqual(event.state, EventState.EMITTED)
        self.assertIsNotNone(event.timestamp.tzinfo)

    async def test_exact_and_wildcard_subscribers_receive_events(self) -> None:
        bus = InMemoryEventBus()
        seen: list[str] = []

        async def exact(event: Event) -> None:
            seen.append(f"exact:{event.event_type}")

        def wildcard(event: Event) -> None:
            seen.append(f"wildcard:{event.event_type}")

        bus.subscribe("system.bootstrap.ready", exact)
        bus.subscribe("*", wildcard)
        await bus.publish(Event.create("system.bootstrap.ready", EventCategory.SYSTEM))
        self.assertEqual(
            seen,
            ["exact:system.bootstrap.ready", "wildcard:system.bootstrap.ready"],
        )

    async def test_one_handler_failure_does_not_stop_dispatch(self) -> None:
        bus = InMemoryEventBus()
        seen: list[str] = []

        def broken(_: Event) -> None:
            raise RuntimeError("consumer failure")

        def healthy(_: Event) -> None:
            seen.append("healthy")

        bus.subscribe("engineering.test", broken)
        bus.subscribe("engineering.test", healthy)
        await bus.publish(Event.create("engineering.test", EventCategory.ENGINEERING))
        self.assertEqual(seen, ["healthy"])
        self.assertEqual(len(bus.handler_errors), 1)

    async def test_closed_bus_rejects_new_events(self) -> None:
        bus = InMemoryEventBus()
        await bus.close()
        with self.assertRaises(RuntimeError):
            await bus.publish(Event.create("system.test", EventCategory.SYSTEM))
