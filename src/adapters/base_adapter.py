"""Base adapter abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAdapter(ABC):
    """Abstract base class for all adapters."""

    @abstractmethod
    async def start(self) -> None:
        """Start adapter resources."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop adapter resources."""

