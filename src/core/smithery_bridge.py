"""
Smithery Bridge — интеграция MCP-серверов через Smithery CLI.

Позволяет вызывать инструменты MCP (например, Google Calendar) через
smithery tool call и получать список доступных инструментов.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30


class SmitheryBridge:
    """
    Мост для вызова MCP-инструментов через Smithery CLI.

    Требования:
    - smithery CLI установлен глобально: npm install -g @smithery/cli
    - Выполнена авторизация: smithery auth login
    - MCP-сервер добавлен: smithery mcp add <server>
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._smithery_path: str | None = None

    def _get_smithery_path(self) -> str:
        """Возвращает путь к smithery CLI."""
        if self._smithery_path is not None:
            return self._smithery_path
        path = shutil.which("smithery")
        if not path:
            raise FileNotFoundError(
                "smithery CLI не найден. Установите: npm install -g @smithery/cli"
            )
        self._smithery_path = path
        return path

    async def call_tool(
        self,
        server: str,
        tool_name: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: int | None = None,
    ) -> dict[str, Any] | str:
        """
        Вызывает MCP-инструмент через smithery tool call.

        Args:
            server: Имя MCP-сервера (например, "googlecalendar").
            tool_name: Имя инструмента (например, "list-events").
            params: Параметры вызова в виде словаря (сериализуются в JSON).
            timeout: Таймаут в секундах (по умолчанию — из __init__).

        Returns:
            При успехе — распарсенный результат (dict или строка из result).
            При ошибке — dict с ключами isError=True и error.

        Raises:
            FileNotFoundError: smithery CLI не найден.
            asyncio.TimeoutError: Превышен таймаут.
        """
        effective_timeout = timeout if timeout is not None else self.timeout
        params_json = json.dumps(params) if params else "{}"

        cmd = [
            self._get_smithery_path(),
            "tool",
            "call",
            server,
            tool_name,
            params_json,
            "--json",
        ]

        logger.info(
            "SmitheryBridge.call_tool: server=%s tool=%s params=%s",
            server,
            tool_name,
            params_json,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=effective_timeout
            )
        except asyncio.TimeoutError:
            logger.error(
                "SmitheryBridge.call_tool: timeout after %ds (server=%s, tool=%s)",
                effective_timeout,
                server,
                tool_name,
            )
            raise

        out = stdout.decode().strip()
        err = stderr.decode().strip()

        if err:
            logger.warning("SmitheryBridge stderr: %s", err)

        try:
            data = json.loads(out) if out else {}
        except json.JSONDecodeError as e:
            logger.error("SmitheryBridge.call_tool: invalid JSON: %s", out)
            return {"isError": True, "error": f"Invalid JSON response: {e}", "raw": out}

        if data.get("isError"):
            logger.error(
                "SmitheryBridge.call_tool failed: %s",
                data.get("error", "Unknown error"),
            )
            return data

        result = data.get("result")
        logger.info("SmitheryBridge.call_tool: success")
        return result if result is not None else data

    async def list_tools(
        self,
        server: str | None = None,
        *,
        limit: int = 50,
        timeout: int | None = None,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """
        Получает список доступных инструментов для MCP-сервера.

        Args:
            server: Имя MCP-сервера или None для всех подключённых.
            limit: Максимум инструментов (по умолчанию 50).
            timeout: Таймаут в секундах.

        Returns:
            Список инструментов (каждый — dict с name, description и т.д.)
            или dict с ошибкой при isError=True.

        Raises:
            FileNotFoundError: smithery CLI не найден.
            asyncio.TimeoutError: Превышен таймаут.
        """
        effective_timeout = timeout if timeout is not None else self.timeout

        cmd = [
            self._get_smithery_path(),
            "tool",
            "list",
        ]
        if server:
            cmd.append(server)
        cmd.extend(["--json", f"--limit={limit}"])

        logger.info("SmitheryBridge.list_tools: server=%s", server or "all")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=effective_timeout
            )
        except asyncio.TimeoutError:
            logger.error(
                "SmitheryBridge.list_tools: timeout after %ds",
                effective_timeout,
            )
            raise

        out = stdout.decode().strip()
        err = stderr.decode().strip()

        if proc.returncode != 0 and err:
            logger.error("SmitheryBridge.list_tools failed: %s", err)
            return {"isError": True, "error": err, "returncode": proc.returncode}

        if err:
            logger.warning("SmitheryBridge list_tools stderr: %s", err)

        try:
            data = json.loads(out) if out else []
        except json.JSONDecodeError as e:
            logger.error("SmitheryBridge.list_tools: invalid JSON: %s", out)
            return {"isError": True, "error": f"Invalid JSON: {e}", "raw": out}

        if isinstance(data, dict) and data.get("isError"):
            return data

        tools = data if isinstance(data, list) else data.get("tools", [])
        logger.info("SmitheryBridge.list_tools: found %d tools", len(tools))
        return tools
