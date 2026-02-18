"""Tests for token usage tracking in LiteLLMProvider."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from nanobot.providers.litellm_provider import LiteLLMProvider


def _fake_litellm_response() -> SimpleNamespace:
    message = SimpleNamespace(content="ok", tool_calls=None, reasoning_content=None)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(prompt_tokens=123, completion_tokens=45, total_tokens=168)
    return SimpleNamespace(choices=[choice], usage=usage)


@pytest.mark.asyncio
async def test_chat_tracks_tokens_when_usage_present(monkeypatch: pytest.MonkeyPatch):
    provider = LiteLLMProvider(api_key="k", default_model="anthropic/claude-3-5-sonnet")

    async def fake_acompletion(**kwargs):
        return _fake_litellm_response()

    tracked: dict[str, object] = {}

    def fake_track_tokens(model: str, usage: dict[str, int]) -> None:
        tracked["model"] = model
        tracked["usage"] = usage

    monkeypatch.setattr(
        "nanobot.providers.litellm_provider.acompletion",
        fake_acompletion,
    )
    monkeypatch.setattr(
        provider,
        "_track_tokens",
        fake_track_tokens,
    )

    result = await provider.chat(messages=[{"role": "user", "content": "hi"}], tools=None)

    assert result.usage["total_tokens"] == 168
    assert tracked["model"] == "anthropic/claude-3-5-sonnet"
    assert tracked["usage"] == {
        "prompt_tokens": 123,
        "completion_tokens": 45,
        "total_tokens": 168,
    }


def test_track_tokens_calls_memory_add_token_usage(monkeypatch: pytest.MonkeyPatch):
    provider = LiteLLMProvider(api_key="k", default_model="anthropic/claude-3-5-sonnet")
    calls: list[dict[str, object]] = []

    def fake_add_token_usage(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("nanobot.memory.add_token_usage", fake_add_token_usage)

    provider._track_tokens(
        model="anthropic/claude-3-5-sonnet",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )

    assert len(calls) == 1
    assert calls[0] == {
        "model": "anthropic/claude-3-5-sonnet",
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }
