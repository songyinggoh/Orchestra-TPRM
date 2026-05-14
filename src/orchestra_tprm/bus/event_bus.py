"""EventBus protocol + in-memory fake implementation."""
from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class EventBus(Protocol):
    """Protocol satisfied by any event-bus backend (Postgres LISTEN/NOTIFY, fake)."""

    async def publish(self, channel: str, payload: dict[str, Any]) -> None:
        """Publish *payload* to *channel*."""
        ...

    async def subscribe(self, channel: str, handler: Callable[[dict], Any]) -> None:
        """Register *handler* to be called for every message on *channel*."""
        ...


class InMemoryEventBus:
    """In-process pub/sub for unit tests.

    Not thread-safe; safe for use with asyncio single-loop tests.

    Attributes
    ----------
    history:
        Read-only list of ``(channel, payload)`` tuples in publish order.
        Useful for assertions in tests without subscribing.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = {}
        self._history: list[tuple[str, dict]] = []

    async def publish(self, channel: str, payload: dict[str, Any]) -> None:
        """Append to history and call all registered handlers for *channel*."""
        self._history.append((channel, payload))
        for handler in self._handlers.get(channel, []):
            if inspect.iscoroutinefunction(handler):
                await handler(payload)
            else:
                handler(payload)

    async def subscribe(self, channel: str, handler: Callable[[dict], Any]) -> None:
        """Register *handler* for *channel*; multiple handlers per channel allowed."""
        self._handlers.setdefault(channel, []).append(handler)

    @property
    def history(self) -> list[tuple[str, dict]]:
        """Snapshot of all published events (channel, payload) in order."""
        return list(self._history)
