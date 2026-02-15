"""Adapter for calling tools via the Model Context Protocol (MCP)."""
from __future__ import annotations

import asyncio
import json
import logging
import shlex
from typing import Any

try:
    from adapters.base_adapter import BaseAdapter
except ModuleNotFoundError:
    from src.adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)


class MCPAdapter(BaseAdapter):
    """Adapter for calling external tools via the manus-mcp-cli."""

    def __init__(self, command_timeout: int = 20) -> None:
        self.command_timeout = command_timeout
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("MCP adapter started.")

    async def stop(self) -> None:
        self._running = False
        logger.info("MCP adapter stopped.")

    async def call_tool(
        self, server: str, tool_name: str, params: dict[str, Any] | None = None
    ) -> str:
        """Call an MCP tool and return its output as a string."""
        if not self._running:
            raise RuntimeError("MCP adapter is not running.")

        input_json = json.dumps(params) if params else "{}"
        cmd = (
            f"manus-mcp-cli tool call {shlex.quote(tool_name)} "
            f"--server {shlex.quote(server)} --input {shlex.quote(input_json)}"
        )
        logger.info("Executing MCP command: %s", cmd)

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), self.command_timeout
            )
        except asyncio.TimeoutError:
            logger.error("MCP command timed out after %d seconds.", self.command_timeout)
            return f"Error: Command timed out after {self.command_timeout} seconds."
        except FileNotFoundError:
            logger.error("manus-mcp-cli not found. Is it installed and in PATH?")
            return "Error: manus-mcp-cli not found."

        if proc.returncode != 0:
            err_msg = stderr.decode().strip()
            logger.error("MCP command failed (code %d): %s", proc.returncode, err_msg)
            return f"Error: {err_msg}"

        return stdout.decode().strip()
