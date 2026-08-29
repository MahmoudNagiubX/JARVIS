"""Small in-process event bus for the foundation bootstrap."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from .events import Event

EventHandler = Callable[[Event], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class EventSubscription:
    token: str
    event_type: str


class EventBus(Protocol):
    """Transport-neutral event bus contract."""

    def subscribe(self, event_type: str, handler: EventHandler) -> EventSubscription: ...

    def unsubscribe(self, subscription: EventSubscription) -> None: ...

    async def publish(self, event: Event) -> None: ...

    async def close(self) -> None: ...


class InMemoryEventBus:
    """Typed-by-envelope pub/sub with exact and wildcard subscriptions.

    The bus is deliberately process-local in Phase 01. Durable delivery,
    retries, and cross-process transport are adapter decisions for a later phase.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, dict[str, EventHandler]] = {}
        self._closed = False
        self._handler_errors: list[Exception] = []

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def handler_errors(self) -> tuple[Exception, ...]:
        return tuple(self._handler_errors)

    def subscribe(self, event_type: str, handler: EventHandler) -> EventSubscription:
        if self._closed:
            raise RuntimeError("event bus is closed")
        if not event_type.strip():
            raise ValueError("event_type cannot be empty")
        token = f"subscription-{len(self._handlers.get(event_type, {})) + 1}"
        self._handlers.setdefault(event_type, {})[token] = handler
        return EventSubscription(token, event_type)

    def unsubscribe(self, subscription: EventSubscription) -> None:
        handlers = self._handlers.get(subscription.event_type)
        if handlers is None:
            return
        handlers.pop(subscription.token, None)
        if not handlers:
            self._handlers.pop(subscription.event_type, None)

    async def publish(self, event: Event) -> None:
        if self._closed:
            raise RuntimeError("event bus is closed")
        handlers = [
            *self._handlers.get(event.event_type, {}).values(),
            *self._handlers.get("*", {}).values(),
        ]
        for handler in handlers:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # one consumer cannot break the lifecycle
                self._handler_errors.append(exc)

    async def close(self) -> None:
        self._closed = True
        self._handlers.clear()
