"""Unit tests for MCPCallTool."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from nanobot.agent.tools.mcp import MCPCallTool


def test_mcp_call_tool_import():
    """MCPCallTool can be imported and instantiated."""
    tool = MCPCallTool()
    assert tool.name == "mcp_call"
    assert "MCP" in tool.description
    assert "server" in tool.parameters["properties"]


@pytest.mark.asyncio
async def test_mcp_call_tool_execute_mock():
    """MCPCallTool executes with correct arguments via subprocess."""
    tool = MCPCallTool(timeout=5)
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as m:
        m.return_value = mock_proc
        result = await tool.execute(
            server="manus-mcp",
            tool_name="create_task",
            arguments={"prompt": "hello", "mode": "speed"},
        )

    assert result == "ok"
    call_args = m.call_args[0][0]
    assert "manus-mcp-cli" in call_args
    assert "tool call" in call_args
    assert "create_task" in call_args
    assert "manus-mcp" in call_args
    assert "create_task" in call_args or "prompt" in call_args or "hello" in call_args


@pytest.mark.asyncio
async def test_mcp_call_tool_not_found():
    """MCPCallTool returns expected message when manus-mcp-cli not found."""
    tool = MCPCallTool(timeout=5)

    with patch("asyncio.create_subprocess_shell", side_effect=FileNotFoundError):
        result = await tool.execute(
            server="test-server",
            tool_name="test_tool",
        )

    assert "manus-mcp-cli not found" in result
    assert "Install" in result or "npm" in result
