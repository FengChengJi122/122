"""
Unit tests for the EventBus async event-driven engine.
"""

import asyncio
import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.engine.event_bus import EventBus, Event


@pytest.fixture
def bus():
    return EventBus()


# ---------------------------------------------------------------------------
# Basic subscribe / publish
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_handler_called(bus):
    received = []

    async def handler(event: Event):
        received.append(event.data)

    bus.subscribe("test", handler)
    await bus.publish(Event(type="test", data="hello"))

    assert received == ["hello"]


@pytest.mark.asyncio
async def test_multiple_handlers_called(bus):
    results = []

    async def h1(event):
        results.append("h1")

    async def h2(event):
        results.append("h2")

    bus.subscribe("click", h1)
    bus.subscribe("click", h2)
    await bus.publish(Event(type="click"))

    assert "h1" in results
    assert "h2" in results


@pytest.mark.asyncio
async def test_unsubscribe_removes_handler(bus):
    calls = []

    async def handler(event):
        calls.append(1)

    bus.subscribe("ping", handler)
    bus.unsubscribe("ping", handler)
    await bus.publish(Event(type="ping"))

    assert calls == []


@pytest.mark.asyncio
async def test_no_handler_for_event_type(bus):
    """Publishing to an event with no subscribers should not raise."""
    await bus.publish(Event(type="nonexistent"))


@pytest.mark.asyncio
async def test_wildcard_subscriber(bus):
    """Subscribers registered to '*' receive every event."""
    received = []

    async def wildcard(event):
        received.append(event.type)

    bus.subscribe("*", wildcard)
    await bus.publish(Event(type="alpha"))
    await bus.publish(Event(type="beta"))

    assert "alpha" in received
    assert "beta" in received


@pytest.mark.asyncio
async def test_sync_handler(bus):
    """Sync (non-async) handlers are also supported."""
    results = []

    def sync_handler(event):
        results.append(event.data)

    bus.subscribe("sync", sync_handler)
    await bus.publish(Event(type="sync", data=42))

    assert results == [42]


@pytest.mark.asyncio
async def test_handler_exception_does_not_stop_others(bus):
    """A handler that raises should not prevent other handlers from running."""
    called = []

    async def bad(event):
        raise RuntimeError("oops")

    async def good(event):
        called.append("good")

    bus.subscribe("boom", bad)
    bus.subscribe("boom", good)
    # Should not raise.
    await bus.publish(Event(type="boom"))

    assert called == ["good"]


@pytest.mark.asyncio
async def test_emit_returns_task(bus):
    received = []

    async def handler(event):
        received.append(event.data)

    bus.subscribe("fire", handler)
    task = bus.emit("fire", data="payload")
    assert asyncio.isfuture(task) or isinstance(task, asyncio.Task)
    await task
    assert received == ["payload"]


@pytest.mark.asyncio
async def test_duplicate_subscribe_ignored(bus):
    """Registering the same handler twice should not call it twice."""
    calls = []

    async def handler(event):
        calls.append(1)

    bus.subscribe("dup", handler)
    bus.subscribe("dup", handler)
    await bus.publish(Event(type="dup"))

    assert len(calls) == 1
