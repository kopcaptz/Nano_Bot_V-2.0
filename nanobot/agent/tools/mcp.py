"""MCP tools: bridge to Model Context Protocol via @wong2/mcp-cli."""

import asyncio
import json
import shlex
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.policy import ToolPolicy


class MCPCallTool(Tool):
    """Call an MCP tool via @wong2/mcp-cli."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "mcp_call"

    @property
    def description(self) -> str:
        return (
            "Call a tool from an MCP (Model Context Protocol) server. "
            "Use when you need: web browsing, Google search, code execution in sandbox, "
            "or other MCP-server capabilities. Requires @wong2/mcp-cli installed."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server": {
                    "type": "string",
                    "description": "MCP server name (e.g. gmail, sheets, drive)",
                },
                "tool_name": {
                    "type": "string",
                    "description": "Name of the MCP tool to call",
                },
                "arguments": {
                    "type": "object",
                    "description": "Arguments for the tool (JSON object). Empty {} if none.",
                },
                "config_path": {
                    "type": "string",
                    "description": "Optional path to MCP config file",
                },
            },
            "required": ["server", "tool_name"],
        }

    @property
    def policy(self) -> ToolPolicy:
        return ToolPolicy.REQUIRE_CONFIRMATION

    async def execute(
        self,
        server: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        config_path: str | None = None,
        **kwargs: Any,
    ) -> str:
        args_json = json.dumps(arguments or {}, ensure_ascii=False)
        
        # Build command: npx @wong2/mcp-cli call-tool server:tool_name --args '{...}'
        cmd_parts = ["npx", "@wong2/mcp-cli"]
        
        if config_path:
            cmd_parts.extend(["--config", shlex.quote(config_path)])
            
        cmd_parts.extend([
            "call-tool", 
            f"{server}:{tool_name}",
            "--args", 
            shlex.quote(args_json)
        ])
        
        cmd = " ".join(cmd_parts)
        
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
                f"Error: MCP call timed out after {self.timeout} seconds."
            )
        except FileNotFoundError:
            return (
                "Error: @wong2/mcp-cli not found. "
                "Install: npm i -g @wong2/mcp-cli"
            )

        if proc.returncode != 0:
            err_msg = stderr.decode().strip()
            return f"Error: {err_msg}"

        return stdout.decode().strip()
