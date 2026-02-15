"""Tests for SkillGenerator and CreateSkillTool."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.skill_generator import SkillGenerator
from nanobot.agent.tools.skill import CreateSkillTool
from nanobot.providers.base import LLMResponse
from nanobot.session.manager import SessionManager


# ---------- Test 1: _extract_tool_sequence ----------


def test_extract_tool_sequence() -> None:
    """_extract_tool_sequence correctly extracts tool calls and results from messages."""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "list_dir",
                        "arguments": '{"path": "/workspace"}',
                    },
                },
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "file1.txt\nfile2.py",
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "/workspace/file1.txt"}',
                    },
                },
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_2",
            "content": "Error: File not found",
        },
    ]

    generator = SkillGenerator(Path("/tmp"), MagicMock(), "test")
    result = generator._extract_tool_sequence(messages)

    assert "list_dir" in result
    assert '"/workspace"' in result
    assert "OK" in result
    assert "ERROR" in result
    assert "file1.txt" in result or "File not found" in result


# ---------- Test 2: create_skill_from_trajectory ----------


@pytest.mark.asyncio
async def test_create_skill_from_trajectory(tmp_path: Path) -> None:
    """create_skill_from_trajectory creates SKILL.md with correct content."""
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(
        return_value=LLMResponse(
            content="## Steps\n1. Use list_dir\n2. Use read_file",
        )
    )

    generator = SkillGenerator(tmp_path, mock_provider, "test-model")
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "function": {"name": "list_dir", "arguments": '{"path": "."}'},
                },
            ],
        },
        {"role": "tool", "content": "file1.txt"},
    ]

    result = await generator.create_skill_from_trajectory(
        skill_name="test_skill",
        skill_description="Test description",
        messages=messages,
    )

    assert "created successfully" in result
    skill_file = tmp_path / "test_skill" / "SKILL.md"
    assert skill_file.exists()

    content = skill_file.read_text()
    assert 'description: "Test description"' in content
    assert "## Steps" in content
    assert "Use list_dir" in content


# ---------- Test 3: create_skill_no_tool_calls ----------


@pytest.mark.asyncio
async def test_create_skill_no_tool_calls(tmp_path: Path) -> None:
    """create_skill_from_trajectory returns error when no tool calls in messages."""
    generator = SkillGenerator(tmp_path, MagicMock(), "test")

    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    result = await generator.create_skill_from_trajectory(
        skill_name="empty_skill",
        skill_description="Empty",
        messages=messages,
    )

    assert "No tool calls found" in result


# ---------- Test 4: CreateSkillTool.execute ----------


@pytest.mark.asyncio
async def test_create_skill_tool_execute() -> None:
    """CreateSkillTool.execute correctly calls SkillGenerator.create_skill_from_trajectory."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_skill_generator = MagicMock()
    mock_skill_generator.create_skill_from_trajectory = AsyncMock(
        return_value="Skill created successfully"
    )

    tool = CreateSkillTool(
        skill_generator=mock_skill_generator,
        session_manager=mock_session_manager,
    )

    tool.set_session_key("test_session")
    tool.set_messages([{"role": "assistant", "content": "test"}])

    result = await tool.execute(skill_name="test_skill", skill_description="Test")

    assert result == "Skill created successfully"
    mock_skill_generator.create_skill_from_trajectory.assert_called_once_with(
        skill_name="test_skill",
        skill_description="Test",
        messages=[{"role": "assistant", "content": "test"}],
    )


# ---------- Test 5: CreateSkillTool no session ----------


@pytest.mark.asyncio
async def test_create_skill_tool_no_session() -> None:
    """CreateSkillTool.execute returns error when session_key is not set."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_skill_generator = MagicMock()

    tool = CreateSkillTool(
        skill_generator=mock_skill_generator,
        session_manager=mock_session_manager,
    )

    result = await tool.execute(skill_name="test", skill_description="Test")

    assert "Error: No active session" in result
    mock_skill_generator.create_skill_from_trajectory.assert_not_called()
