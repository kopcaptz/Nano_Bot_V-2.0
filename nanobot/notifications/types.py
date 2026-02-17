"""Notification types for nanobot push notifications."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Sequence


class Priority(str, Enum):
    """Notification priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Notification:
    """Represents a notification to be sent via Telegram."""

    chat_id: str | int
    message: str
    priority: Priority = Priority.NORMAL
    scheduled_at: datetime | None = None
    tags: Sequence[str] = ()
