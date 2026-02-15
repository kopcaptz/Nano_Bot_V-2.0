"""Regression tests for async EventBus behavior."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.event_bus import EventBus  # noqa: E402


class EventBusTests(unittest.IsolatedAsyncioTestCase):
    """Validate subscribe/publish/unsubscribe semantics."""

    async def test_publish_dispatches_to_async_subscriber(self) -> None:
        bus = EventBus()
        delivered: list[Any] = []
        signal = asyncio.Event()

        async def subscriber(payload: Any) -> None:
            delivered.append(payload)
            signal.set()

        await bus.subscribe("topic.demo", subscriber)
        await bus.publish("topic.demo", {"value": 42})
        await asyncio.wait_for(signal.wait(), timeout=0.5)

        self.assertEqual(delivered, [{"value": 42}])
        self.assertEqual(bus.get_subscriber_count("topic.demo"), 1)

    async def test_non_async_subscriber_is_rejected(self) -> None:
        bus = EventBus()

        def not_async(_: Any) -> None:
            return None

        await bus.subscribe("topic.demo", not_async)  # type: ignore[arg-type]
        self.assertEqual(bus.get_subscriber_count("topic.demo"), 0)

    async def test_unsubscribe_removes_event_type(self) -> None:
        bus = EventBus()

        async def subscriber(_: Any) -> None:
            return None

        await bus.subscribe("topic.demo", subscriber)
        self.assertEqual(bus.list_event_types(), ["topic.demo"])
        await bus.unsubscribe("topic.demo", subscriber)

        self.assertEqual(bus.get_subscriber_count("topic.demo"), 0)
        self.assertEqual(bus.list_event_types(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
