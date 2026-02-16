"""Tests for SmitheryBridge."""
import asyncio
import logging

import pytest

from src.core.smithery_bridge import SmitheryBridge, DEFAULT_TIMEOUT


@pytest.fixture
def bridge():
    return SmitheryBridge(timeout=15)


@pytest.mark.asyncio
async def test_call_tool_returns_error_when_not_authenticated(bridge: SmitheryBridge):
    """Without smithery auth, call_tool returns error dict."""
    result = await bridge.call_tool(
        server="googlecalendar",
        tool_name="list-events",
        params={"timeMin": "2026-02-16T00:00:00Z", "timeMax": "2026-02-16T23:59:59Z"},
    )
    assert isinstance(result, dict)
    assert result.get("isError") is True
    assert "error" in result


@pytest.mark.asyncio
async def test_list_tools_returns_error_when_not_authenticated(bridge: SmitheryBridge):
    """Without smithery auth, list_tools returns error dict."""
    result = await bridge.list_tools(server="googlecalendar")
    assert isinstance(result, dict)
    assert result.get("isError") is True
    assert "error" in result


@pytest.mark.asyncio
async def test_smithery_not_found():
    """When smithery is not in PATH, raises FileNotFoundError."""
    bridge = SmitheryBridge(timeout=5)
    bridge._smithery_path = "/nonexistent/smithery"
    with pytest.raises(FileNotFoundError):
        await bridge.call_tool("x", "y", {})


def test_default_timeout():
    assert SmitheryBridge().timeout == DEFAULT_TIMEOUT
    assert SmitheryBridge(timeout=10).timeout == 10


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = SmitheryBridge(timeout=15)
    result = asyncio.run(
        bridge.call_tool(
            server="googlecalendar",
            tool_name="list-events",
            params={"timeMin": "2026-02-16T00:00:00Z", "timeMax": "2026-02-16T23:59:59Z"},
        )
    )
    print("call_tool result:", result)
    tools = asyncio.run(bridge.list_tools(server="googlecalendar"))
    print("list_tools result:", tools)
