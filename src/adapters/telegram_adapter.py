"""Telegram adapter implementation."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

try:  # script mode
    from adapters.base_adapter import BaseAdapter
    from core.event_bus import EventBus
except ModuleNotFoundError:  # package mode
    from src.adapters.base_adapter import BaseAdapter
    from src.core.event_bus import EventBus

logger = logging.getLogger(__name__)


class TelegramAdapter(BaseAdapter):
    """Telegram channel adapter."""
    MAX_MESSAGE_LENGTH = 4000
    SEND_CHUNK_DELAY_SECONDS = 0.15
    BOT_COMMANDS = [
        BotCommand("start", "Запустить Nano Bot"),
        BotCommand("help", "Показать список команд"),
        BotCommand("status", "Показать состояние адаптеров"),
        BotCommand("clear_history", "Очистить историю текущего чата"),
        BotCommand("system", "Выполнить безопасную системную команду"),
        BotCommand("browser_open", "Открыть URL в браузере"),
        BotCommand("browser_text", "Получить текст страницы"),
        BotCommand("screenshot", "Сделать скриншот"),
        BotCommand("ocr", "Запустить OCR (заглушка)"),
    ]

    def __init__(self, event_bus: EventBus, token: str) -> None:
        self.event_bus = event_bus
        self.token = token
        self._app: Application | None = None
        self._running = False
        self._reply_subscribed = False

    async def start(self) -> None:
        """Start telegram polling and register handlers."""
        if self._running:
            logger.debug("Telegram adapter already running.")
            return

        if not self.token:
            logger.warning("Telegram adapter skipped: TELEGRAM_BOT_TOKEN is empty.")
            return
        if not self._reply_subscribed:
            await self.event_bus.subscribe("telegram.send.reply", self.send_message)
            self._reply_subscribed = True

        self._app = Application.builder().token(self.token).build()
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("help", self._handle_help_command))
        self._app.add_handler(CommandHandler("status", self._handle_status_command))
        self._app.add_handler(CommandHandler("clear_history", self._handle_clear_history_command))
        self._app.add_handler(CommandHandler("system", self._handle_system_command))
        self._app.add_handler(CommandHandler("browser_open", self._handle_browser_open_command))
        self._app.add_handler(CommandHandler("browser_text", self._handle_browser_text_command))
        self._app.add_handler(CommandHandler("screenshot", self._handle_screenshot_command))
        self._app.add_handler(CommandHandler("ocr", self._handle_ocr_command))
        self._app.add_handler(MessageHandler(filters.COMMAND, self._handle_unknown_command))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text_message)
        )

        logger.info("Starting Telegram adapter...")
        await self._app.initialize()
        await self._app.start()
        try:
            await self._app.bot.set_my_commands(self.BOT_COMMANDS)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to register telegram bot commands.")
        await self._app.updater.start_polling(drop_pending_updates=True)
        self._running = True
        logger.info("Telegram adapter started.")

    async def stop(self) -> None:
        """Stop telegram polling gracefully."""
        if not self._running and self._app is None and not self._reply_subscribed:
            logger.debug("Telegram adapter already stopped.")
            return

        self._running = False
        if self._app is not None:
            logger.info("Stopping Telegram adapter...")
            try:
                await self._app.updater.stop()
            except Exception:  # noqa: BLE001
                logger.debug("Telegram updater already stopped.")
            await self._app.stop()
            await self._app.shutdown()
            self._app = None

        if self._reply_subscribed:
            await self.event_bus.unsubscribe("telegram.send.reply", self.send_message)
            self._reply_subscribed = False

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Reply to /start command."""
        if not update.message:
            return
        await update.message.reply_text("Nano Bot V-2.0 запущен. Отправьте команду текстом.")

    async def _handle_text_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Publish telegram.command.received event for incoming text."""
        if not update.message or not update.effective_chat or not update.effective_user:
            return
        await self._publish_command_event(update=update, command_text=update.message.text or "")

    async def _handle_help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._publish_command_event(update=update, command_text="/help")

    async def _handle_status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._publish_command_event(update=update, command_text="/status")

    async def _handle_clear_history_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._publish_command_event(update=update, command_text="/clear_history")

    async def _handle_system_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        command_text = self._compose_command("/system", context.args)
        await self._publish_command_event(update=update, command_text=command_text)

    async def _handle_browser_open_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        command_text = self._compose_command("/browser_open", context.args)
        await self._publish_command_event(update=update, command_text=command_text)

    async def _handle_browser_text_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        command_text = self._compose_command("/browser_text", context.args)
        await self._publish_command_event(update=update, command_text=command_text)

    async def _handle_screenshot_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        command_text = self._compose_command("/screenshot", context.args)
        await self._publish_command_event(update=update, command_text=command_text)

    async def _handle_ocr_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        command_text = self._compose_command("/ocr", context.args)
        await self._publish_command_event(update=update, command_text=command_text)

    async def _handle_unknown_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Forward unknown slash commands into the same command pipeline."""
        if not update.message:
            return
        command_text = (update.message.text or "").strip()
        if not command_text:
            return
        await self._publish_command_event(update=update, command_text=command_text)

    @staticmethod
    def _compose_command(base: str, args: list[str] | None) -> str:
        """Build normalized command string from command and args."""
        if not args:
            return base
        return f"{base} {' '.join(arg for arg in args if arg)}".strip()

    async def _publish_command_event(self, update: Update, command_text: str) -> None:
        """Publish normalized command payload to event bus."""
        if not update.message or not update.effective_chat or not update.effective_user:
            return

        event_payload: dict[str, Any] = {
            "chat_id": update.effective_chat.id,
            "user_id": update.effective_user.id,
            "command": command_text,
        }
        await self.event_bus.publish("telegram.command.received", event_payload)

    async def send_message(self, event_data: dict[str, Any]) -> None:
        """Send reply message to Telegram chat."""
        if self._app is None:
            logger.warning("Cannot send Telegram message: adapter not running.")
            return

        raw_chat_id = event_data.get("chat_id")
        text = str(event_data.get("text", ""))
        if not text.strip():
            text = "(empty response)"
        if raw_chat_id is None:
            logger.warning("telegram.send.reply missed chat_id: %s", event_data)
            return

        try:
            chat_id = int(raw_chat_id)
        except (TypeError, ValueError):
            logger.warning("telegram.send.reply has invalid chat_id: %s", raw_chat_id)
            return

        try:
            chunks = self._split_text(text)
            for idx, chunk in enumerate(chunks):
                await self._app.bot.send_message(chat_id=chat_id, text=chunk)
                if idx < len(chunks) - 1:
                    logger.debug("Sent telegram chunk %d/%d", idx + 1, len(chunks))
                    await asyncio.sleep(self.SEND_CHUNK_DELAY_SECONDS)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to send telegram message to chat_id=%s", chat_id)

    def _split_text(self, text: str) -> list[str]:
        """Split outgoing message into Telegram-safe chunks."""
        if len(text) <= self.MAX_MESSAGE_LENGTH:
            return [text]

        chunks: list[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= self.MAX_MESSAGE_LENGTH:
                chunks.append(remaining)
                break

            window = remaining[: self.MAX_MESSAGE_LENGTH]
            split_at = window.rfind("\n")
            if split_at <= 0:
                split_at = window.rfind(" ")
            if split_at <= 0:
                split_at = self.MAX_MESSAGE_LENGTH

            chunk = remaining[:split_at].strip()
            if chunk:
                chunks.append(chunk)
            remaining = remaining[split_at:].lstrip()

        return chunks or ["(empty response)"]

