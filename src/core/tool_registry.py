"""Central registry and dispatcher for all agent tools."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.adapters.base_adapter import BaseAdapter
    from src.adapters.mcp_adapter import MCPAdapter

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Manages registration and dispatching of tools for the LLM agent."""

    def __init__(self, mcp_adapter: MCPAdapter) -> None:
        self._mcp_adapter = mcp_adapter
        self._local_tools: dict[str, dict[str, Any]] = {}
        self._mcp_tools: dict[str, dict[str, Any]] = {}

    def register_adapter(self, adapter: BaseAdapter, adapter_name: str) -> None:
        """Register tools from a local adapter."""
        tool_definitions = adapter.get_tool_definitions()
        for tool in tool_definitions:
            tool_id = f"{adapter_name}.{tool['function']['name']}"
            self._local_tools[tool_id] = {"definition": tool, "adapter": adapter}
            logger.info("Registered local tool: %s", tool_id)

    def register_mcp_tools(self, server: str, tool_definitions: list[dict]) -> None:
        """Register tools from an MCP server."""
        for tool in tool_definitions:
            tool_id = f"mcp_{server}.{tool['function']['name']}"
            self._mcp_tools[tool_id] = {"definition": tool, "server": server}
            logger.info("Registered MCP tool: %s", tool_id)

    def get_tools_for_llm(self) -> list[dict]:
        """Return all tool definitions formatted for the LLM."""
        local_defs = [info["definition"] for info in self._local_tools.values()]
        mcp_defs = [info["definition"] for info in self._mcp_tools.values()]
        return local_defs + mcp_defs

    def get_tool_names(self) -> list[str]:
        """Return a list of all registered tool names."""
        return list(self._local_tools.keys()) + list(self._mcp_tools.keys())

    def _find_tool(self, tool_name: str) -> tuple[str, dict[str, Any]] | None:
        """Find tool by full tool_id or by function name."""
        if tool_name in self._local_tools:
            return tool_name, self._local_tools[tool_name]
        if tool_name in self._mcp_tools:
            return tool_name, self._mcp_tools[tool_name]
        for tid, info in self._local_tools.items():
            if info["definition"]["function"]["name"] == tool_name:
                return tid, info
        for tid, info in self._mcp_tools.items():
            if info["definition"]["function"]["name"] == tool_name:
                return tid, info
        return None

    async def dispatch(self, tool_name: str, params: dict[str, Any]) -> str:
        """Dispatch a tool call to the appropriate adapter."""
        logger.info("Dispatching tool: %s with params: %s", tool_name, params)

        found = self._find_tool(tool_name)
        if not found:
            return f"Error: Tool '{tool_name}' not found in registry."

        tool_id, tool_info = found

        if tool_id in self._local_tools:
            adapter = tool_info["adapter"]
            method_name = tool_info["definition"]["function"]["name"]
            method = getattr(adapter, method_name, None)
            if not method:
                return f"Error: Method '{method_name}' not found on adapter."
            try:
                if asyncio.iscoroutinefunction(method):
                    result = await method(**params)
                else:
                    result = method(**params)
                return str(result) if result is not None else "Done."
            except TypeError as e:
                return f"Error: Invalid parameters for '{tool_name}': {e}"
            except Exception as e:
                logger.exception("Error calling local tool '%s'", tool_name)
                return f"Error executing '{tool_name}': {e}"

        if tool_id in self._mcp_tools:
            server = tool_info["server"]
            mcp_tool_name = tool_info["definition"]["function"]["name"]
            return await self._mcp_adapter.call_tool(server, mcp_tool_name, params)

        return f"Error: Tool '{tool_name}' not found in registry."
