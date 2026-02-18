"""MCP tools: bridge to Model Context Protocol via manus-mcp-cli."""

import asyncio
import json
import shlex
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.policy import ToolPolicy


class MCPCallTool(Tool):
    """Call an MCP tool via manus-mcp-cli."""

    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "mcp_call"

    @property
    def description(self) -> str:
        return (
            "Call a tool from an MCP (Model Context Protocol) server. "
            "Use when you need: web browsing, Google search, code execution in sandbox, "
            "or other MCP-server capabilities. Requires manus-mcp-cli installed."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server": {
                    "type": "string",
                    "description": "MCP server name (e.g. manus-mcp, cursor-ide-browser)",
                },
                "tool_name": {
                    "type": "string",
                    "description": "Name of the MCP tool to call",
                },
                "arguments": {
                    "type": "object",
                    "description": "Arguments for the tool (JSON object). Empty {} if none.",
                },
            },
            "required": ["server", "tool_name"],
        }

    @property
    def policy(self) -> ToolPolicy:
        return ToolPolicy.CONFIRM

    async def execute(
        self,
        server: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        input_json = json.dumps(arguments or {}, ensure_ascii=False)
        cmd = (
            f"manus-mcp-cli tool call {shlex.quote(tool_name)} "
            f"--server {shlex.quote(server)} --input {shlex.quote(input_json)}"
        )
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            return (
                f"Error: manus-mcp-cli timed out after {self.timeout} seconds."
            )
        except FileNotFoundError:
            return (
                "Error: manus-mcp-cli not found. "
                "Install: npm i -g manus-mcp-cli (or npx manus-mcp-cli)"
            )

        if proc.returncode != 0:
            err_msg = stderr.decode().strip()
            return f"Error: {err_msg}"

        return stdout.decode().strip()
