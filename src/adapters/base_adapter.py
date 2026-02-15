"""Abstract base class for all Nano Bot V-2.0 adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAdapter(ABC):
    """Defines the common interface for all adapters."""

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    def get_tool_definitions(self) -> list[dict]:
        """Return tool definitions for this adapter. Override in subclasses."""
        return []

    async def call_tool(self, tool_name: str, params: dict[str, Any]) -> str:
        """Call a tool on this adapter. Override in subclasses."""
        _ = tool_name, params
        raise NotImplementedError("This adapter does not support direct tool calls.")
