"""In-memory dialogue context storage for Nano Bot V-2.0."""

from __future__ import annotations


class CrystalMemory:
    """Simple chat memory store (MVP in-memory implementation)."""

    def __init__(self) -> None:
        self._messages: dict[int, list[dict]] = {}

    def add_message(self, chat_id: int, role: str, content: str) -> None:
        """Append message to chat history."""
        if chat_id not in self._messages:
            self._messages[chat_id] = []
        self._messages[chat_id].append({"role": role, "content": content})

    def get_history(self, chat_id: int) -> list[dict]:
        """Return history for the given chat id."""
        return list(self._messages.get(chat_id, []))

    def clear_history(self, chat_id: int) -> None:
        """Clear history for the given chat id."""
        self._messages.pop(chat_id, None)

