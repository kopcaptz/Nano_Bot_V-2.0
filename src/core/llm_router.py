"""OpenRouter LLM integration layer."""

from __future__ import annotations

import logging

import openai
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMRouter:
    """Route commands to OpenRouter models."""

    def __init__(
        self,
        api_key: str,
        model: str,
        request_timeout_seconds: float = 45.0,
        max_context_messages: int = 40,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.request_timeout_seconds = request_timeout_seconds
        self.max_context_messages = max_context_messages if max_context_messages > 0 else 40
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    async def process_command(self, command: str, context: list[dict]) -> str:
        """Send user command + context to OpenRouter and return plain text response."""
        if not self.api_key:
            return "OPENROUTER_API_KEY не задан. Добавьте ключ в .env."

        messages = self._build_messages(command=command, context=context)

        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                timeout=self.request_timeout_seconds,
            )
            content = completion.choices[0].message.content
            text = self._normalize_text_content(content)
            return text or "LLM вернул пустой ответ."
        except openai.RateLimitError:
            logger.exception("OpenRouter rate limit exceeded")
            return "Сервис LLM временно перегружен (rate limit). Попробуйте чуть позже."
        except openai.APITimeoutError:
            logger.exception("OpenRouter timeout")
            return "LLM не ответил вовремя. Повторите запрос."
        except openai.APIError:
            logger.exception("OpenRouter API error")
            return "Произошла ошибка API при обращении к LLM. Попробуйте снова."
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error while calling OpenRouter")
            return "Неожиданная ошибка при обращении к LLM. Попробуйте позже."

    def _build_messages(self, command: str, context: list[dict]) -> list[dict[str, str]]:
        """Build bounded message list for OpenRouter call."""
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "You are Nano Bot V-2.0, a local system assistant. "
                    "Use context to answer coherently and concisely."
                ),
            }
        ]
        for item in context[-self.max_context_messages :]:
            role = item.get("role")
            content = item.get("content")
            if isinstance(role, str) and isinstance(content, str):
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": command})
        return messages

    @staticmethod
    def _normalize_text_content(content: object) -> str:
        """Normalize OpenAI response content into a plain text string."""
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            text_chunks: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    maybe_text = item.get("text")
                    if isinstance(maybe_text, str):
                        text_chunks.append(maybe_text)
                    continue

                maybe_text_attr = getattr(item, "text", None)
                if isinstance(maybe_text_attr, str):
                    text_chunks.append(maybe_text_attr)
            return "\n".join(chunk.strip() for chunk in text_chunks if chunk.strip())

        return ""

