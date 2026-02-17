"""Core components for Nano Bot V-2.0."""
from .event_bus import EventBus
from .handler import CommandHandler
from .llm_router import LLMRouter
from .memory import CrystalMemory  # legacy, kept for backward compatibility
from .smithery_bridge import SmitheryBridge
from .tool_registry import ToolRegistry

from nanobot.session.manager import SessionManager

__all__ = [
    "EventBus",
    "CommandHandler",
    "LLMRouter",
    "CrystalMemory",
    "SessionManager",
    "SmitheryBridge",
    "ToolRegistry",
]
