"""Unit tests for EventBus protocol and InMemoryEventBus."""
from __future__ import annotations

import pytest

from orchestra_tprm.bus.event_bus import EventBus, InMemoryEventBus


@pytest.fixture
def bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.mark.asyncio
async def test_in_memory_publish_stores_in_history(bus: InMemoryEventBus) -> None:
    await bus.publish("runs", {"run_id": "abc", "status": "started"})
    assert len(bus.history) == 1
    channel, payload = bus.history[0]
    assert channel == "runs"
    assert payload["run_id"] == "abc"


@pytest.mark.asyncio
async def test_in_memory_subscribe_handler_called_on_publish(bus: InMemoryEventBus) -> None:
    received: list[dict] = []

    async def handler(payload: dict) -> None:
        received.append(payload)

    await bus.subscribe("runs", handler)
    await bus.publish("runs", {"run_id": "xyz"})

    assert len(received) == 1
    assert received[0]["run_id"] == "xyz"


@pytest.mark.asyncio
async def test_in_memory_multiple_channels_isolated(bus: InMemoryEventBus) -> None:
    a_received: list[dict] = []
    b_received: list[dict] = []

    async def handler_a(p: dict) -> None:
        a_received.append(p)

    async def handler_b(p: dict) -> None:
        b_received.append(p)

    await bus.subscribe("channel_a", handler_a)
    await bus.subscribe("channel_b", handler_b)

    await bus.publish("channel_a", {"msg": "for a"})
    await bus.publish("channel_b", {"msg": "for b"})

    assert len(a_received) == 1 and a_received[0]["msg"] == "for a"
    assert len(b_received) == 1 and b_received[0]["msg"] == "for b"
    # Cross-channel isolation
    assert len(bus.history) == 2


def test_in_memory_event_bus_satisfies_protocol() -> None:
    bus = InMemoryEventBus()
    assert isinstance(bus, EventBus), (
        "InMemoryEventBus must satisfy the EventBus runtime_checkable Protocol"
    )
