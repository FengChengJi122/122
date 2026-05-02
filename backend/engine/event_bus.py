"""
Async Event-Driven Engine — EventBus

A lightweight pub/sub bus built on asyncio that lets every component of the
system communicate without tight coupling.  Handlers can be synchronous or
asynchronous coroutines.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """A typed event that travels through the bus."""

    type: str
    data: Any = None
    source: Optional[str] = None
    timestamp: float = field(default_factory=lambda: asyncio.get_event_loop().time())


# A handler can be any callable that accepts a single Event argument.
Handler = Callable[[Event], Coroutine | Any]


class EventBus:
    """
    Asynchronous publish/subscribe event bus.

    Usage::

        bus = EventBus()

        async def on_chat(event: Event):
            print(event.data)

        bus.subscribe("chat", on_chat)
        await bus.publish(Event(type="chat", data="hello"))
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Handler]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Register *handler* for *event_type*."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
            logger.debug("Subscribed %s -> %s", event_type, handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        """Remove *handler* from *event_type*."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h is not handler
            ]

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(self, event: Event) -> None:
        """
        Dispatch *event* to all registered handlers.

        Handlers are called concurrently via ``asyncio.gather``.  If a
        handler raises, the exception is logged but other handlers still
        run.
        """
        handlers = list(self._subscribers.get(event.type, []))
        # Also dispatch to wildcard subscribers.
        handlers += list(self._subscribers.get("*", []))

        if not handlers:
            return

        async def _call(h: Handler) -> None:
            try:
                result = h(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:  # noqa: BLE001
                logger.exception("Handler %s raised for event %s: %s", h, event.type, exc)

        await asyncio.gather(*[_call(h) for h in handlers])

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def emit(self, event_type: str, data: Any = None, source: Optional[str] = None) -> asyncio.Task:
        """
        Fire-and-forget helper that schedules publish without ``await``.

        Returns the asyncio Task so callers can optionally ``await`` it.
        """
        event = Event(type=event_type, data=data, source=source)
        loop = asyncio.get_event_loop()
        return loop.create_task(self.publish(event))
