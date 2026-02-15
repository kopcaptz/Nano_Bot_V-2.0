"""Unit tests for Reflection module and reflection DB functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.reflection import Reflection
from nanobot.memory.db import DB_PATH, add_reflection, get_recent_reflections, init_db
from nanobot.providers.base import LLMResponse


# ---------- Reflection._format_user_prompt ----------


def test_format_user_prompt_includes_recent_messages_and_error() -> None:
    """_format_user_prompt formats messages, tool call, and error."""
    mock_provider = MagicMock()
    reflection = Reflection(provider=mock_provider, model="test-model")

    messages = [
        {"role": "user", "content": "Read config.yaml"},
        {"role": "assistant", "content": ""},
    ]
    failed_tool_call = {"name": "read_file", "arguments": {"path": "config.yaml"}}
    error_result = "Error: File not found."

    result = reflection._format_user_prompt(messages, failed_tool_call, error_result)

    assert "Recent conversation:" in result
    assert "[user]" in result
    assert "Read config.yaml" in result
    assert "[assistant]" in result
    assert "Failed tool call:" in result
    assert "read_file" in result
    assert "config.yaml" in result
    assert "Error result:" in result
    assert "File not found" in result


def test_format_user_prompt_limits_history_to_last_5() -> None:
    """_format_user_prompt uses only last 5 messages when more are provided."""
    mock_provider = MagicMock()
    reflection = Reflection(provider=mock_provider, model="test-model")

    # Use distinct strings to avoid substring overlap (e.g. "msg_1" in "msg_15")
    messages = [{"role": "user", "content": f"msg_{i:02d}"} for i in range(20)]
    failed_tool_call = {"name": "exec", "arguments": {"command": "ls"}}
    error_result = "Error: failed"

    result = reflection._format_user_prompt(messages, failed_tool_call, error_result)

    # Only last 5 should appear (messages 15-19)
    for i in range(15):
        assert f"msg_{i:02d}" not in result
    for i in range(15, 20):
        assert f"msg_{i:02d}" in result


def test_format_user_prompt_handles_tool_name_and_tool_args_aliases() -> None:
    """_format_user_prompt accepts both 'name'/'arguments' and 'tool_name'/'tool_args'."""
    mock_provider = MagicMock()
    reflection = Reflection(provider=mock_provider, model="test-model")

    messages = []
    failed_tool_call = {"tool_name": "edit_file", "tool_args": {"path": "/tmp/x"}}
    error_result = "Error: permission denied"

    result = reflection._format_user_prompt(messages, failed_tool_call, error_result)

    assert "edit_file" in result
    assert "/tmp/x" in result


# ---------- Reflection.analyze_trajectory ----------


@pytest.mark.asyncio
async def test_analyze_trajectory_returns_insight() -> None:
    """analyze_trajectory returns LLM content when provider succeeds."""
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(
        return_value=LLMResponse(content="Reflection: The file path was wrong.")
    )
    reflection = Reflection(provider=mock_provider, model="test-model")

    messages = [{"role": "user", "content": "read config"}]
    failed_tool_call = {"name": "read_file", "arguments": {"path": "config.yaml"}}
    error_result = "Error: File not found."

    result = await reflection.analyze_trajectory(
        messages=messages,
        failed_tool_call=failed_tool_call,
        error_result=error_result,
    )

    assert result is not None
    assert "Reflection:" in result
    mock_provider.chat.assert_called_once()
    call_kwargs = mock_provider.chat.call_args.kwargs
    assert call_kwargs.get("tools") is None
    assert call_kwargs.get("max_tokens") == 500
    assert call_kwargs.get("temperature") == 0.3


@pytest.mark.asyncio
async def test_analyze_trajectory_handles_llm_error() -> None:
    """analyze_trajectory returns None and does not raise when LLM fails."""
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(side_effect=Exception("API unavailable"))
    reflection = Reflection(provider=mock_provider, model="test-model")

    result = await reflection.analyze_trajectory(
        messages=[],
        failed_tool_call={"name": "exec", "arguments": {}},
        error_result="Error: failed",
    )

    assert result is None


# ---------- add_reflection / get_recent_reflections ----------


def test_add_reflection_and_get_recent_reflections(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """add_reflection saves to DB; get_recent_reflections retrieves it."""
    db_file = tmp_path / "test_memory.db"
    monkeypatch.setattr("nanobot.memory.db.DB_PATH", db_file)

    # Force re-init with new path (module may have been imported with old path)
    init_db()

    add_reflection(
        tool_name="read_file",
        tool_args='{"path": "config.yaml"}',
        error_text="Error: File not found.",
        insight="Reflection: Use absolute path or list_dir first.",
        session_key="cli:test",
    )

    reflections = get_recent_reflections(limit=10)
    assert len(reflections) == 1
    assert reflections[0]["tool_name"] == "read_file"
    assert "config.yaml" in reflections[0]["tool_args"]
    assert "File not found" in reflections[0]["error_text"]
    assert "Reflection:" in reflections[0]["insight"]
    assert reflections[0]["session_key"] == "cli:test"
    assert "created_at" in reflections[0]


def test_get_recent_reflections_filters_by_tool_name(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_recent_reflections with tool_name filters results."""
    db_file = tmp_path / "test_memory.db"
    monkeypatch.setattr("nanobot.memory.db.DB_PATH", db_file)
    init_db()

    add_reflection("read_file", "{}", "err1", "insight1", session_key=None)
    add_reflection("exec", "{}", "err2", "insight2", session_key=None)
    add_reflection("read_file", "{}", "err3", "insight3", session_key=None)

    all_refs = get_recent_reflections(limit=10)
    assert len(all_refs) == 3

    read_refs = get_recent_reflections(tool_name="read_file", limit=10)
    assert len(read_refs) == 2
    assert all(r["tool_name"] == "read_file" for r in read_refs)

    exec_refs = get_recent_reflections(tool_name="exec", limit=10)
    assert len(exec_refs) == 1
    assert exec_refs[0]["tool_name"] == "exec"
