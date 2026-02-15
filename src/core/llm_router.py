"""LLM routing and interaction layer for Nano Bot V-2.0."""
from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMRouter:
    """Handles communication with the LLM provider (OpenRouter)."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("OpenRouter API key is not set.")
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self.model = model

    async def process_command(
        self,
        command: str,
        context: list[dict[str, Any]],
        tools: list[dict] | None = None,
        messages_override: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Send command to LLM and get a response, optionally with tools."""
        if messages_override:
            messages = messages_override
        else:
            messages = [*context, {"role": "user", "content": command}]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.model_dump()
        except Exception as e:
            logger.exception("Error communicating with LLM provider.")
            return {
                "role": "assistant",
                "content": f"Error: Could not get response from LLM. {e}",
            }

    @staticmethod
    def extract_text(content: Any) -> str:
        """Safely extract text from LLM response content."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks = []
            for item in content:
                if isinstance(item, dict):
                    t = item.get("text")
                    if isinstance(t, str):
                        chunks.append(t)
                else:
                    t = getattr(item, "text", None)
                    if isinstance(t, str):
                        chunks.append(t)
            return "\n".join(c.strip() for c in chunks if c.strip())
        return ""
