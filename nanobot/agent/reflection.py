"""Reflection module for analyzing failed tool calls."""

import json
from typing import Any

from loguru import logger

from nanobot.providers.base import LLMProvider


REFLECTION_SYSTEM_PROMPT = """You are a Self-Correction module for an AI agent called nanobot.
Your task: analyze a failed tool call and provide a concise, actionable insight.

Rules:
1. Identify the ROOT CAUSE: wrong parameter? wrong assumption? wrong tool? missing prerequisite step?
2. Propose a SPECIFIC fix: suggest a corrected tool call or an alternative approach.
3. Be CONCISE: one paragraph, starting with "Reflection: ...".
4. Do NOT repeat the error message. Focus on the solution.

Example:
Reflection: The read_file tool failed because the path "config.yaml" is relative. The workspace is at C:/Users/kopca/Nano_Bot_V2/workspace/, so the correct path should be "C:/Users/kopca/Nano_Bot_V2/workspace/config.yaml". I should use list_dir first to verify the file exists."""


class Reflection:
    """Analyzes failed tool calls and generates corrective insights via LLM."""

    def __init__(self, provider: LLMProvider, model: str) -> None:
        self.provider = provider
        self.model = model

    def _format_user_prompt(
        self,
        messages: list[dict[str, Any]],
        failed_tool_call: dict[str, Any],
        error_result: str,
    ) -> str:
        """Format a user prompt for reflection with recent context and error details."""
        recent = messages[-5:] if len(messages) > 5 else messages

        parts = ["Recent conversation:\n"]
        for m in recent:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if isinstance(content, list):
                content = str(content)
            parts.append(f"  [{role}]: {content[:500]}{'...' if len(str(content)) > 500 else ''}\n")

        tool_name = failed_tool_call.get("name", failed_tool_call.get("tool_name", "unknown"))
        tool_args = failed_tool_call.get("arguments", failed_tool_call.get("tool_args", {}))
        if isinstance(tool_args, dict):
            args_str = json.dumps(tool_args, ensure_ascii=False)
        else:
            args_str = str(tool_args)

        parts.append(f"\nFailed tool call:\n  Tool: {tool_name}\n  Arguments: {args_str}\n")
        parts.append(f"\nError result:\n{error_result}")

        return "".join(parts)

    async def analyze_trajectory(
        self,
        messages: list[dict[str, Any]],
        failed_tool_call: dict[str, Any],
        error_result: str,
    ) -> str | None:
        """
        Analyze a failed tool call and return an actionable insight.

        Args:
            messages: Recent conversation messages.
            failed_tool_call: Dict with 'name' and 'arguments' (or 'tool_name', 'tool_args').
            error_result: The error message from the failed execution.

        Returns:
            LLM-generated reflection text, or None on error.
        """
        try:
            user_prompt = self._format_user_prompt(messages, failed_tool_call, error_result)
            llm_messages = [
                {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            response = await self.provider.chat(
                messages=llm_messages,
                tools=None,
                model=self.model,
                max_tokens=500,
                temperature=0.3,
            )
            return response.content
        except Exception as e:
            logger.warning(f"Reflection failed: {e}")
            return None
