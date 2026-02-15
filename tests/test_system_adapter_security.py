"""Security and sandbox tests for SystemAdapter."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from adapters.system_adapter import SystemAdapter  # noqa: E402


@unittest.skipIf(shutil.which("echo") is None, "echo command is unavailable")
class SystemAdapterSecurityTests(unittest.IsolatedAsyncioTestCase):
    """Validate command allow-list and workspace sandbox protections."""

    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "agent_workspace"
        self.adapter = SystemAdapter(workspace=self.workspace)
        await self.adapter.start()

    async def asyncTearDown(self) -> None:
        await self.adapter.stop()
        self.tmp.cleanup()

    async def test_allowlisted_command_executes(self) -> None:
        result = await self.adapter.run_app("echo hello")
        self.assertIn("hello", result.lower())

    async def test_non_allowlisted_command_is_blocked(self) -> None:
        with self.assertRaises(PermissionError):
            await self.adapter.run_app("ls -la")

    async def test_shell_operator_injection_is_blocked(self) -> None:
        with self.assertRaises(PermissionError):
            await self.adapter.run_app("echo hello && whoami")

    async def test_file_io_stays_inside_workspace(self) -> None:
        self.adapter.write_file("nested/hello.txt", "hello world")
        read_back = self.adapter.read_file("nested/hello.txt")
        listing = self.adapter.list_dir("nested")

        self.assertEqual(read_back, "hello world")
        self.assertIn("hello.txt", listing)

    async def test_path_escape_is_blocked(self) -> None:
        outside_file = Path(self.tmp.name) / "outside.txt"
        outside_file.write_text("outside", encoding="utf-8")

        with self.assertRaises(PermissionError):
            self.adapter.read_file("../outside.txt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
