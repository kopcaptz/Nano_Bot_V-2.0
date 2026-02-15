"""In-memory dialogue context storage for Nano Bot V-2.0."""

from __future__ import annotations


class CrystalMemory:
    """Simple chat memory store (MVP in-memory implementation)."""

    def __init__(self, max_messages_per_chat: int = 200) -> None:
        self._messages: dict[int, list[dict[str, str]]] = {}
        self.max_messages_per_chat = max_messages_per_chat

    def add_message(self, chat_id: int, role: str, content: str) -> None:
        """Append message to chat history."""
        if chat_id not in self._messages:
            self._messages[chat_id] = []
        normalized_role = (role or "user").strip().lower()
        if normalized_role not in {"user", "assistant", "system"}:
            normalized_role = "user"
        self._messages[chat_id].append({"role": normalized_role, "content": str(content)})
        if len(self._messages[chat_id]) > self.max_messages_per_chat:
            overflow = len(self._messages[chat_id]) - self.max_messages_per_chat
            self._messages[chat_id] = self._messages[chat_id][overflow:]

    def get_history(self, chat_id: int) -> list[dict]:
        """Return history for the given chat id."""
        history = self._messages.get(chat_id, [])
        return [dict(item) for item in history]

    def clear_history(self, chat_id: int) -> None:
        """Clear history for the given chat id."""
        self._messages.pop(chat_id, None)

