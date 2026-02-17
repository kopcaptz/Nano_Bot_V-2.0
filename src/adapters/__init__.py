"""Adapters for Nano Bot V-2.0."""
from .base_adapter import BaseAdapter
from .browser_adapter import BrowserAdapter
from .gmail_adapter import GmailAdapter
from .system_adapter import SystemAdapter
from .telegram_adapter import TelegramAdapter
from .vision_adapter import VisionAdapter

__all__ = [
    "BaseAdapter",
    "BrowserAdapter",
    "GmailAdapter",
    "SystemAdapter",
    "TelegramAdapter",
    "VisionAdapter",
]
