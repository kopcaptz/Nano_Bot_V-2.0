"""MCP (Model Context Protocol) tool for calling remote MCP servers."""

import asyncio
import json
import shlex
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool


class MCPTool(Tool):
    """Call tools on remote MCP servers via manus-mcp-cli.

    Enables the agent to interact with external services (Asana, Notion,
    Google Calendar, etc.) that expose an MCP-compatible interface.
    """

    DEFAULT_TIMEOUT = 30

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "mcp"

    @property
    def description(self) -> str:
        return (
            "Выполняет вызов инструмента на удаленном MCP-сервере. "
            "Используй для работы с внешними сервисами, такими как "
            "Asana, Notion, Google Calendar и др."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server": {
                    "type": "string",
                    "description": (
                        'Имя MCP-сервера (например, "asana", "notion", "googlecalendar")'
                    ),
                },
                "tool_name": {
                    "type": "string",
                    "description": (
                        'Имя инструмента на сервере (например, "search_tasks", "list-events")'
                    ),
                },
                "params": {
                    "type": "object",
                    "description": "Словарь с параметрами для вызова инструмента",
                },
            },
            "required": ["server", "tool_name", "params"],
        }

    async def execute(
        self,
        server: str,
        tool_name: str,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Execute a tool on a remote MCP server.

        Builds and runs the command:
            manus-mcp-cli tool call <tool_name> \
                --server <server> --input '<json_params>'

        Returns:
            stdout on success, or a prefixed error message on failure.
        """
        params = params or {}
        input_json = json.dumps(params, ensure_ascii=False)

        cmd = (
            f"manus-mcp-cli tool call {shlex.quote(tool_name)} "
            f"--server {shlex.quote(server)} "
            f"--input {shlex.quote(input_json)}"
        )

        logger.info("MCP call: server={} tool={} params={}", server, tool_name, input_json)

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                logger.error(
                    "MCP call timed out after {}s: server={} tool={}",
                    self.timeout, server, tool_name,
                )
                return f"Error: MCP command timed out after {self.timeout} seconds"

        except FileNotFoundError:
            logger.error("manus-mcp-cli not found in PATH")
            return "Error: manus-mcp-cli not found. Is it installed and in PATH?"

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            error_detail = stderr_text or stdout_text or "unknown error"
            logger.error(
                "MCP call failed (code {}): server={} tool={} error={}",
                proc.returncode, server, tool_name, error_detail,
            )
            return f"Error: MCP call failed (exit {proc.returncode}): {error_detail}"

        if stderr_text:
            logger.warning("MCP stderr: {}", stderr_text)

        logger.info("MCP call success: server={} tool={}", server, tool_name)

        max_len = 10000
        if len(stdout_text) > max_len:
            stdout_text = (
                stdout_text[:max_len]
                + f"\n... (truncated, {len(stdout_text) - max_len} more chars)"
            )

        return stdout_text or "(no output)"
