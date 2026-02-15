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

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self._running = False

    async def start(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._running = True
        logger.info("System adapter started. Workspace=%s", self.workspace.resolve())

    async def stop(self) -> None:
        self._running = False
        logger.info("System adapter stopped.")

    def _is_safe_path(self, path: str) -> bool:
        """Validate that path resolves under workspace root."""
        resolved_path = Path(path).expanduser().resolve()
        return str(resolved_path).startswith(str(self.workspace.resolve()))

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

        try:
            if os.name == "nt":
                process = await asyncio.create_subprocess_exec(
                    "cmd",
                    "/c",
                    *parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.workspace,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.workspace,
                )
        except FileNotFoundError:
            return f"Command not found: {executable}"

        stdout, stderr = await process.communicate()
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

