"""Unit tests for LLMRouter message and content helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.llm_router import LLMRouter  # noqa: E402


class _TextChunk:
    def __init__(self, text: str) -> None:
        self.text = text


class LLMRouterHelpersTests(unittest.IsolatedAsyncioTestCase):
    """Regression coverage for local message normalization logic."""

    def test_build_messages_filters_roles_and_applies_context_limit(self) -> None:
        router = LLMRouter(api_key="x", model="m", max_context_messages=2)
        context = [
            {"role": "system", "content": "persisted system"},
            {"role": "assistant", "content": "old answer"},
            {"role": "invalid", "content": "should be skipped"},
            {"role": "user", "content": "latest user"},
        ]

        messages = router._build_messages(command="new question", context=context)

        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[-1], {"role": "user", "content": "new question"})
        # Only the last two context items are considered; invalid role is dropped.
        self.assertEqual(messages[1:-1], [{"role": "user", "content": "latest user"}])

    def test_normalize_text_content_handles_string_and_chunks(self) -> None:
        self.assertEqual(LLMRouter._normalize_text_content("  ok  "), "ok")
        self.assertEqual(
            LLMRouter._normalize_text_content(
                [
                    {"text": " first "},
                    _TextChunk("second"),
                    {"not_text": "ignored"},
                    _TextChunk("   "),
                ]
            ),
            "first\nsecond",
        )
        self.assertEqual(LLMRouter._normalize_text_content(123), "")

    async def test_missing_api_key_returns_explicit_message(self) -> None:
        router = LLMRouter(api_key="", model="m")
        result = await router.process_command(command="hi", context=[])
        self.assertIn("OPENROUTER_API_KEY не задан", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
