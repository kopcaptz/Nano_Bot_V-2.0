"""OpenRouter LLM integration layer."""

from __future__ import annotations

import logging

import openai
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMRouter:
    """Route commands to OpenRouter models."""

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    async def process_command(self, command: str, context: list[dict]) -> str:
        """Send user command + context to OpenRouter and return plain text response."""
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "You are Nano Bot V-2.0, a local system assistant. "
                    "Use context to answer coherently and concisely."
                ),
            }
        ]
        for item in context:
            role = item.get("role")
            content = item.get("content")
            if isinstance(role, str) and isinstance(content, str):
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": command})

        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            content = completion.choices[0].message.content
            return (content or "").strip() or "LLM вернул пустой ответ."
        except openai.RateLimitError:
            logger.exception("OpenRouter rate limit exceeded")
            return "Сервис LLM временно перегружен (rate limit). Попробуйте чуть позже."
        except openai.APITimeoutError:
            logger.exception("OpenRouter timeout")
            return "LLM не ответил вовремя. Повторите запрос."
        except openai.APIError:
            logger.exception("OpenRouter API error")
            return "Произошла ошибка API при обращении к LLM. Попробуйте снова."

