"""Base adapter abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAdapter(ABC):
    """Abstract base class for all adapters."""

    @property
    def is_running(self) -> bool:
        """Return adapter running state if available."""
        return bool(getattr(self, "_running", False))

    @abstractmethod
    async def start(self) -> None:
        """Start adapter resources."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop adapter resources."""

