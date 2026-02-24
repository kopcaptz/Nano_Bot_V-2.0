"""Async regression tests for CommandHandler shortcuts."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.event_bus import EventBus  # noqa: E402
from core.handler import CommandHandler  # noqa: E402
from core.memory import CrystalMemory  # noqa: E402


class DummyLLMRouter:
    """Simple in-memory LLM stub for handler tests."""

    def __init__(self) -> None:
        self.model = "dummy/model"
        self.max_context_messages = 4
        self.request_timeout_seconds = 1.0
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    async def process_command(self, command: str, context: list[dict[str, str]]) -> str:
        self.calls.append((command, [dict(item) for item in context]))
        return "llm-result"


class CommandHandlerShortcutsTests(unittest.IsolatedAsyncioTestCase):
    """Covers slash-command shortcut behavior and persistence rules."""

    async def asyncSetUp(self) -> None:
        self.event_bus = EventBus()
        self.memory = CrystalMemory()
        self.llm = DummyLLMRouter()
        self.handler = CommandHandler(self.event_bus, self.llm, self.memory)
        await self.handler.initialize()
        self.replies: list[dict[str, Any]] = []
        await self.event_bus.subscribe("telegram.send.reply", self._capture_reply)

        # Patch gateway_execute_task so tests don't need a real nanobot agent
        patcher = patch(
            "core.handler.gateway_execute_task",
            new_callable=AsyncMock,
            return_value="agent-result",
        )
        self._gateway_mock = patcher.start()
        self.addCleanup(patcher.stop)

    async def asyncTearDown(self) -> None:
        await self.handler.shutdown()

    async def _capture_reply(self, payload: dict[str, Any]) -> None:
        self.replies.append(dict(payload))

    async def _publish_command(self, chat_id: int, command: str, wait_for_debounce: bool = False) -> dict[str, Any]:
        await self.event_bus.publish(
            "telegram.command.received",
            {"chat_id": chat_id, "command": command},
        )
        # If command is not a slash command and we expect debounce, wait longer
        if wait_for_debounce:
            await asyncio.sleep(5.2)  # Wait for debounce delay + buffer
        else:
            await asyncio.sleep(0.05)
        self.assertTrue(self.replies, msg="Expected at least one reply event")
        return self.replies[-1]

    async def test_ping_returns_pong_and_is_not_persisted(self) -> None:
        """`/ping` must bypass LLM and avoid memory pollution."""
        reply = await self._publish_command(chat_id=7001, command="/ping")
        self.assertEqual(reply["text"], "pong")
        self.assertEqual(self.llm.calls, [])
        self.assertEqual(self.memory.get_history(7001), [])

    async def test_unknown_slash_returns_help_hint_without_llm_call(self) -> None:
        """Unknown slash commands should not hit the LLM path."""
        reply = await self._publish_command(chat_id=7002, command="/unknown arg")
        self.assertEqual(reply["text"], "Неизвестная команда. Используйте /help.")
        self.assertEqual(self.llm.calls, [])
        self.assertEqual(self.memory.get_history(7002), [])

    async def test_status_shortcut_is_not_persisted(self) -> None:
        """Known slash shortcuts should stay out of conversation history."""
        reply = await self._publish_command(chat_id=7004, command="/status")
        self.assertIn("Статус Nano Bot V-2.0:", reply["text"])
        self.assertEqual(self.llm.calls, [])
        self.assertEqual(self.memory.get_history(7004), [])

    async def test_regular_text_delegates_to_agent_and_persists_turns(self) -> None:
        """Non-slash text must be delegated to AgentLoop via gateway and persist user+assistant messages."""
        reply = await self._publish_command(chat_id=7003, command="hello bot", wait_for_debounce=True)
        self.assertEqual(reply["text"], "agent-result")
        # LLM router should NOT be called — delegation goes directly to gateway
        self.assertEqual(len(self.llm.calls), 0)
        # Gateway should have been called with correct session_key
        self._gateway_mock.assert_called_once_with(
            task="hello bot",
            session_key="telegram:7003",
        )

        history = self.memory.get_history(7003)
        self.assertEqual(
            history,
            [
                {"role": "user", "content": "hello bot"},
                {"role": "assistant", "content": "agent-result"},
            ],
        )

    async def test_debounce_accumulates_multiple_messages(self) -> None:
        """Multiple rapid messages should be accumulated and sent as one to the agent."""
        chat_id = 7005
        
        # Send three messages in rapid succession
        await self.event_bus.publish(
            "telegram.command.received",
            {"chat_id": chat_id, "command": "Hello"},
        )
        await asyncio.sleep(0.1)
        
        await self.event_bus.publish(
            "telegram.command.received",
            {"chat_id": chat_id, "command": "this is"},
        )
        await asyncio.sleep(0.1)
        
        await self.event_bus.publish(
            "telegram.command.received",
            {"chat_id": chat_id, "command": "a test"},
        )
        
        # Wait for debounce delay
        await asyncio.sleep(5.2)
        
        # Should have received exactly one reply
        self.assertEqual(len(self.replies), 1)
        self.assertEqual(self.replies[0]["text"], "agent-result")
        
        # Gateway should have been called once with concatenated message
        self._gateway_mock.assert_called_once_with(
            task="Hello this is a test",
            session_key=f"telegram:{chat_id}",
        )
        
        # History should show the combined message
        history = self.memory.get_history(chat_id)
        self.assertEqual(
            history,
            [
                {"role": "user", "content": "Hello this is a test"},
                {"role": "assistant", "content": "agent-result"},
            ],
        )

    async def test_slash_command_bypasses_debounce(self) -> None:
        """Slash commands should be processed immediately without debounce."""
        chat_id = 7006
        
        # Send a slash command
        await self.event_bus.publish(
            "telegram.command.received",
            {"chat_id": chat_id, "command": "/ping"},
        )
        
        # Should get immediate response without waiting for debounce
        await asyncio.sleep(0.1)
        
        self.assertEqual(len(self.replies), 1)
        self.assertEqual(self.replies[0]["text"], "pong")
        
        # Should not call LLM
        self.assertEqual(len(self.llm.calls), 0)

    async def test_calendar_request_delegates_to_agent(self) -> None:
        """Calendar-related natural-language request should be delegated to agent."""
        await self.event_bus.publish(
            "telegram.command.received",
            {"chat_id": 7007, "command": "Что у меня завтра в календаре?"},
        )
        # Debounce 5s + processing
        await asyncio.sleep(5.5)
        self.assertTrue(self.replies, msg="Expected at least one reply event")
        reply = self.replies[-1]
        self.assertEqual(reply["text"], "agent-result")
        self._gateway_mock.assert_called_once_with(
            task="Что у меня завтра в календаре?",
            session_key="telegram:7007",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
