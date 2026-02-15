"""Central command coordinator for Nano Bot V-2.0."""

from __future__ import annotations

import logging
from typing import Any

try:  # script mode: python src/main.py
    from core.event_bus import EventBus
    from core.llm_router import LLMRouter
    from core.memory import CrystalMemory
except ModuleNotFoundError:  # package mode: import src.main
    from src.core.event_bus import EventBus
    from src.core.llm_router import LLMRouter
    from src.core.memory import CrystalMemory

logger = logging.getLogger(__name__)


class CommandHandler:
    """Coordinates incoming commands, LLM processing, and adapter actions."""

    def __init__(
        self,
        event_bus: EventBus,
        llm_router: LLMRouter,
        memory: CrystalMemory,
        **adapters: Any,
    ) -> None:
        self.event_bus = event_bus
        self.llm_router = llm_router
        self.memory = memory
        self.adapters = adapters

    async def initialize(self) -> None:
        """Register handler subscriptions on the event bus."""
        await self.event_bus.subscribe("telegram.command.received", self.handle_command)

    async def handle_command(self, event_data: dict[str, Any]) -> None:
        """Handle user command received from Telegram."""
        chat_id = int(event_data["chat_id"])
        command = str(event_data.get("command", "")).strip()
        logger.info("Handling command for chat_id=%s: %s", chat_id, command)

        if not command:
            await self.event_bus.publish(
                "telegram.send.reply",
                {"chat_id": chat_id, "text": "Пустая команда. Отправьте текстовый запрос."},
            )
            return

        self.memory.add_message(chat_id, "user", command)

        try:
            adapter_result = await self._try_adapter_shortcuts(command)
            if adapter_result is not None:
                reply_text = adapter_result
            else:
                history = self.memory.get_history(chat_id)
                reply_text = await self.llm_router.process_command(command=command, context=history)
        except Exception:  # noqa: BLE001
            logger.exception("Command processing failed")
            reply_text = "Не удалось обработать команду из-за внутренней ошибки."

        self.memory.add_message(chat_id, "assistant", reply_text)
        await self.event_bus.publish(
            "telegram.send.reply",
            {"chat_id": chat_id, "text": reply_text},
        )

    async def _try_adapter_shortcuts(self, command: str) -> str | None:
        """
        Handle simple MVP adapter commands.

        Supported:
        - /system <cmd>
        - /browser_open <url>
        - /browser_text [url]
        - /screenshot <filename>
        """
        if command.startswith("/system "):
            system = self.adapters.get("system")
            if system is None:
                return "System adapter недоступен."
            command_to_run = command.removeprefix("/system ").strip()
            if not command_to_run:
                return "Укажите команду: /system <команда>"
            return await system.run_app(command_to_run)

        if command.startswith("/browser_open "):
            browser = self.adapters.get("browser")
            if browser is None:
                return "Browser adapter недоступен."
            url = command.removeprefix("/browser_open ").strip()
            if not url:
                return "Укажите URL: /browser_open <url>"
            await browser.open_url(url)
            return f"Открыл страницу: {url}"

        if command.startswith("/browser_text"):
            browser = self.adapters.get("browser")
            if browser is None:
                return "Browser adapter недоступен."
            url = command.removeprefix("/browser_text").strip() or None
            return await browser.get_page_text(url)

        if command.startswith("/screenshot "):
            vision = self.adapters.get("vision")
            if vision is None:
                return "Vision adapter недоступен."
            filename = command.removeprefix("/screenshot ").strip()
            if not filename:
                return "Укажите имя файла: /screenshot <filename.png>"
            saved = vision.take_screenshot(filename)
            return f"Скриншот сохранён: {saved}"

        return None

