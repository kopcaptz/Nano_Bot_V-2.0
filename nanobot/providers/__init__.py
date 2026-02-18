"""LLM provider abstraction module."""

from nanobot.providers.base import LLMProvider, LLMResponse

try:
    from nanobot.providers.litellm_provider import LiteLLMProvider
except ImportError:  # pragma: no cover - allows lightweight imports without litellm
    LiteLLMProvider = None  # type: ignore[assignment]

__all__ = ["LLMProvider", "LLMResponse", "LiteLLMProvider"]
