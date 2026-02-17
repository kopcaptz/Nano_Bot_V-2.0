"""Async regression tests for CommandHandler shortcuts."""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.event_bus import EventBus  # noqa: E402
from core.handler import CommandHandler  # noqa: E402
from nanobot.session.manager import SessionManager  # noqa: E402


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
        self._tmp_dir = tempfile.mkdtemp()
        self.session_manager = SessionManager(
            workspace=Path(self._tmp_dir),
            sessions_dir=Path(self._tmp_dir) / "sessions",
        )
        self.llm = DummyLLMRouter()
        self.handler = CommandHandler(
            self.event_bus, self.llm, self.session_manager,
        )
        await self.handler.initialize()
        self.replies: list[dict[str, Any]] = []
        await self.event_bus.subscribe("telegram.send.reply", self._capture_reply)

    async def asyncTearDown(self) -> None:
        await self.handler.shutdown()
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    async def _capture_reply(self, payload: dict[str, Any]) -> None:
        self.replies.append(dict(payload))

    def _get_history(self, chat_id: int) -> list[dict]:
        """Helper: fetch history from SessionManager the same way handler does."""
        return self.handler._get_session_history(chat_id)

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
        self.assertEqual(self._get_history(7001), [])

    async def test_unknown_slash_returns_help_hint_without_llm_call(self) -> None:
        """Unknown slash commands should not hit the LLM path."""
        reply = await self._publish_command(chat_id=7002, command="/unknown arg")
        self.assertEqual(reply["text"], "Неизвестная команда. Используйте /help.")
        self.assertEqual(self.llm.calls, [])
        self.assertEqual(self._get_history(7002), [])

    async def test_status_shortcut_is_not_persisted(self) -> None:
        """Known slash shortcuts should stay out of conversation history."""
        reply = await self._publish_command(chat_id=7004, command="/status")
        self.assertIn("Статус Nano Bot V-2.0:", reply["text"])
        self.assertEqual(self.llm.calls, [])
        self.assertEqual(self._get_history(7004), [])

    async def test_regular_text_goes_to_llm_and_persists_turns(self) -> None:
        """Non-slash text must call LLM and persist user+assistant messages."""
        reply = await self._publish_command(chat_id=7003, command="hello bot", wait_for_debounce=True)
        self.assertEqual(reply["text"], "llm-result")
        self.assertEqual(len(self.llm.calls), 1)
        self.assertEqual(self.llm.calls[0][0], "hello bot")

        history = self._get_history(7003)
        self.assertEqual(
            history,
            [
                {"role": "user", "content": "hello bot"},
                {"role": "assistant", "content": "llm-result"},
            ],
        )

    async def test_debounce_accumulates_multiple_messages(self) -> None:
        """Multiple rapid messages should be accumulated and sent as one."""
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
        self.assertEqual(self.replies[0]["text"], "llm-result")
        
        # LLM should have been called once with concatenated message
        self.assertEqual(len(self.llm.calls), 1)
        self.assertEqual(self.llm.calls[0][0], "Hello this is a test")
        
        # History should show the combined message
        history = self._get_history(chat_id)
        self.assertEqual(
            history,
            [
                {"role": "user", "content": "Hello this is a test"},
                {"role": "assistant", "content": "llm-result"},
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

    async def test_calendar_action_triggers_bridge_and_returns_error_when_not_authed(
        self,
    ) -> None:
        """When LLM returns [ACTION:CALENDAR_LIST], handler calls bridge and surfaces auth error."""
        orig = self.llm.process_command

        async def return_calendar_action(**kwargs: Any) -> str:
            await orig(**kwargs)
            return "[ACTION:CALENDAR_LIST]"

        self.llm.process_command = return_calendar_action

        await self.event_bus.publish(
            "telegram.command.received",
            {"chat_id": 7007, "command": "Что у меня завтра в календаре?"},
        )
        # Debounce 5s + bridge call ~3s
        await asyncio.sleep(9.0)
        self.assertTrue(self.replies, msg="Expected at least one reply event")
        reply = self.replies[-1]
        self.assertIn("Календарь недоступен", reply["text"])
        self.assertIn("smithery", reply["text"].lower())


class SessionManagerPersistenceTests(unittest.IsolatedAsyncioTestCase):
    """Verify that conversation history persists across handler restarts."""

    async def test_history_survives_handler_restart(self) -> None:
        """Messages saved by one handler instance are visible after re-creation."""
        tmp_dir = tempfile.mkdtemp()
        sessions_dir = Path(tmp_dir) / "sessions"
        try:
            sm = SessionManager(workspace=Path(tmp_dir), sessions_dir=sessions_dir)
            bus = EventBus()
            llm = DummyLLMRouter()

            # --- first handler lifetime ---
            h1 = CommandHandler(bus, llm, sm)
            await h1.initialize()
            await bus.subscribe("telegram.send.reply", lambda _: None)

            await bus.publish(
                "telegram.command.received",
                {"chat_id": 9001, "command": "remember me"},
            )
            await asyncio.sleep(5.2)
            await h1.shutdown()

            history_after_first = h1._get_session_history(9001)
            self.assertEqual(len(history_after_first), 2)

            # --- simulate restart: new SessionManager, new handler, same dir ---
            sm2 = SessionManager(workspace=Path(tmp_dir), sessions_dir=sessions_dir)
            bus2 = EventBus()
            llm2 = DummyLLMRouter()
            h2 = CommandHandler(bus2, llm2, sm2)
            await h2.initialize()

            history_after_restart = h2._get_session_history(9001)
            self.assertEqual(len(history_after_restart), 2)
            self.assertEqual(history_after_restart[0]["role"], "user")
            self.assertEqual(history_after_restart[0]["content"], "remember me")
            self.assertEqual(history_after_restart[1]["role"], "assistant")
            self.assertEqual(history_after_restart[1]["content"], "llm-result")
            await h2.shutdown()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def test_clear_history_removes_persistent_data(self) -> None:
        """After /clear_history, a restarted handler should see empty history."""
        tmp_dir = tempfile.mkdtemp()
        sessions_dir = Path(tmp_dir) / "sessions"
        try:
            sm = SessionManager(workspace=Path(tmp_dir), sessions_dir=sessions_dir)
            bus = EventBus()
            llm = DummyLLMRouter()

            h1 = CommandHandler(bus, llm, sm)
            await h1.initialize()
            replies: list[dict] = []
            await bus.subscribe("telegram.send.reply", lambda p: replies.append(p))

            # Add some history
            await bus.publish(
                "telegram.command.received",
                {"chat_id": 9002, "command": "some message"},
            )
            await asyncio.sleep(5.2)
            self.assertEqual(len(h1._get_session_history(9002)), 2)

            # Clear
            await bus.publish(
                "telegram.command.received",
                {"chat_id": 9002, "command": "/clear_history"},
            )
            await asyncio.sleep(0.1)
            self.assertEqual(len(h1._get_session_history(9002)), 0)

            await h1.shutdown()

            # Restart
            sm2 = SessionManager(workspace=Path(tmp_dir), sessions_dir=sessions_dir)
            h2 = CommandHandler(EventBus(), DummyLLMRouter(), sm2)
            self.assertEqual(len(h2._get_session_history(9002)), 0)
            await h2.shutdown()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
