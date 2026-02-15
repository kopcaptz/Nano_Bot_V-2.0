"""System adapter with workspace sandbox and command allow-list."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
from pathlib import Path

import pyperclip

try:  # script mode
    from adapters.base_adapter import BaseAdapter
except ModuleNotFoundError:  # package mode
    from src.adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)


class SystemAdapter(BaseAdapter):
    """Adapter for interacting with local OS in a restricted way."""

    SAFE_COMMANDS = {"dir", "tasklist", "ping", "echo"}
    SHELL_META_PATTERN = re.compile(r"(?:&&|\|\||[;|<>`]|[$][(])")
    POSIX_ALIASES: dict[str, list[str]] = {
        "dir": ["ls"],
        "tasklist": ["ps", "-e"],
    }

    def __init__(self, workspace: Path, command_timeout: float = 20.0) -> None:
        self.workspace = workspace
        self.command_timeout = command_timeout
        self._running = False

    async def start(self) -> None:
        if self._running:
            logger.debug("System adapter already running.")
            return
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._running = True
        logger.info("System adapter started. Workspace=%s", self.workspace.resolve())

    async def stop(self) -> None:
        if not self._running:
            logger.debug("System adapter already stopped.")
            return
        self._running = False
        logger.info("System adapter stopped.")

    def _is_safe_path(self, path: str) -> bool:
        """Validate that path resolves under workspace root."""
        resolved_path = Path(path).expanduser().resolve()
        workspace_resolved = self.workspace.resolve()
        return resolved_path == workspace_resolved or workspace_resolved in resolved_path.parents

    def _resolve_safe_path(self, path: str) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        resolved = candidate.resolve()
        if not self._is_safe_path(str(resolved)):
            raise PermissionError(f"Unsafe path (outside workspace): {path}")
        return resolved

    async def run_app(self, command: str) -> str:
        """Run an allow-listed command only."""
        command = command.strip()
        if not command:
            raise PermissionError("Empty command is not allowed.")

        if self.SHELL_META_PATTERN.search(command):
            raise PermissionError("Command contains forbidden shell operators.")

        parts = shlex.split(command, posix=(os.name != "nt"))
        executable = parts[0].lower() if parts else ""
        if executable not in self.SAFE_COMMANDS:
            raise PermissionError(
                f"Command '{executable}' is not allowed. Allowed: {sorted(self.SAFE_COMMANDS)}"
            )

        exec_parts = parts
        if os.name != "nt" and executable in self.POSIX_ALIASES:
            alias = self.POSIX_ALIASES[executable]
            exec_parts = [*alias, *parts[1:]]
        if os.name != "nt" and executable == "ping":
            has_count = any(arg in {"-c", "-n"} for arg in exec_parts[1:])
            if not has_count:
                exec_parts = [*exec_parts, "-c", "4"]

        try:
            if os.name == "nt":
                process = await asyncio.create_subprocess_exec(
                    "cmd",
                    "/c",
                    *exec_parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.workspace,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *exec_parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.workspace,
                )
        except FileNotFoundError:
            return f"Command not found: {executable}"

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.command_timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return f"Command timed out after {self.command_timeout:.1f}s"

        output = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        if process.returncode != 0 and err:
            return f"Command failed ({process.returncode}): {err}"
        if err:
            return f"{output}\n{err}".strip()
        return output or "(no output)"

    def read_file(self, path: str) -> str:
        safe_path = self._resolve_safe_path(path)
        if not safe_path.exists() or not safe_path.is_file():
            raise FileNotFoundError(f"File not found: {safe_path}")
        return safe_path.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        safe_path = self._resolve_safe_path(path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding="utf-8")

    def list_dir(self, path: str) -> list[str]:
        safe_path = self._resolve_safe_path(path)
        if not safe_path.exists() or not safe_path.is_dir():
            raise NotADirectoryError(f"Directory not found: {safe_path}")
        return sorted(item.name for item in safe_path.iterdir())

    def get_clipboard(self) -> str:
        try:
            return pyperclip.paste()
        except pyperclip.PyperclipException as exc:
            logger.warning("Clipboard read failed: %s", exc)
            return ""

    def set_clipboard(self, content: str) -> None:
        try:
            pyperclip.copy(content)
        except pyperclip.PyperclipException as exc:
            logger.warning("Clipboard write failed: %s", exc)

    def delete_file(self, path: str) -> None:
        safe_path = self._resolve_safe_path(path)
        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: {safe_path}")
        if safe_path.is_dir():
            raise IsADirectoryError(f"Cannot delete directory: {safe_path}")
        safe_path.unlink()

    def get_tool_definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_dir",
                    "description": "List files and directories in a path within the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative path from workspace root. Use '.' for root."}
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read the content of a file within the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative path to the file."}
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write content to a file within the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative path to the file."},
                            "content": {"type": "string", "description": "Content to write."},
                        },
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_file",
                    "description": "Delete a file within the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative path to the file."}
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_app",
                    "description": "Run a system command. Use with caution.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "The command to execute."}
                        },
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_clipboard",
                    "description": "Get the current system clipboard content.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_clipboard",
                    "description": "Set the system clipboard content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "Text to place in clipboard."}
                        },
                        "required": ["content"],
                    },
                },
            },
        ]

