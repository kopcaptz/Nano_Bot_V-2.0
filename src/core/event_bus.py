"""Asynchronous event bus for inter-component communication."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

EventCallback = Callable[[Any], Awaitable[None]]


class EventBus:
    """Minimal async pub/sub event bus."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventCallback]] = defaultdict(list)

    async def subscribe(self, event_type: str, callback: EventCallback) -> None:
        """Register callback for an event type."""
        self._subscribers[event_type].append(callback)
        logger.debug("Subscriber added for event '%s'.", event_type)

    async def publish(self, event_type: str, data: Any) -> None:
        """Publish event to all subscribers as detached async tasks."""
        callbacks = self._subscribers.get(event_type, [])
        logger.info("Event published: %s | subscribers=%d", event_type, len(callbacks))
        for callback in callbacks:
            asyncio.create_task(callback(data))

