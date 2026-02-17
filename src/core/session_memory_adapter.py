"""SessionMemoryAdapter - фасад для совместимости CrystalMemory API с SessionManager."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

try:
    from nanobot.session.manager import SessionManager
except ImportError:
    SessionManager = None  # type: ignore[misc, assignment]

if TYPE_CHECKING:
    from nanobot.session.manager import SessionManager


class SessionMemoryAdapter:
    """Фасад: CrystalMemory-совместимый API поверх SessionManager."""

    def __init__(
        self,
        session_manager: SessionManager | Path,
        max_messages_per_chat: int = 200,
    ) -> None:
        if SessionManager is None:
            raise ImportError(
                "SessionManager не найден. Нужно установить nanobot или скопировать модули."
            )
        if isinstance(session_manager, Path):
            self._manager = SessionManager(session_manager)
        else:
            self._manager = session_manager
        self.max_messages_per_chat = max_messages_per_chat

    def _key(self, chat_id: int) -> str:
        """Преобразует chat_id в ключ сессии."""
        return f"telegram:{chat_id}"

    def add_message(self, chat_id: int, role: str, content: str) -> None:
        """Добавляет сообщение в историю чата."""
        session = self._manager.get_or_create(self._key(chat_id))
        session.add_message(role, content)

        # Обрезка истории по лимиту
        if len(session.messages) > self.max_messages_per_chat:
            session.messages = session.messages[-self.max_messages_per_chat :]

        self._manager.save(session)

    def get_history(self, chat_id: int) -> list[dict]:
        """Возвращает историю сообщений чата."""
        session = self._manager.get_or_create(self._key(chat_id))
        return session.get_history(max_messages=self.max_messages_per_chat)

    def clear_history(self, chat_id: int) -> None:
        """Очищает историю чата."""
        self._manager.delete(self._key(chat_id))
