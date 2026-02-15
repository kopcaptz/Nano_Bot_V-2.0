"""Vision adapter for screenshot capture and OCR stub."""

from __future__ import annotations

import logging
from pathlib import Path

import mss
from PIL import Image

try:  # script mode
    from adapters.base_adapter import BaseAdapter
except ModuleNotFoundError:  # package mode
    from src.adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)


class VisionAdapter(BaseAdapter):
    """Adapter for screenshot operations."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.screenshots_dir = self.workspace / "screenshots"
        self._running = False

    async def start(self) -> None:
        if self._running:
            logger.debug("Vision adapter already running.")
            return
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self._running = True
        logger.info("Vision adapter started. screenshots_dir=%s", self.screenshots_dir)

    async def stop(self) -> None:
        if not self._running:
            logger.debug("Vision adapter already stopped.")
            return
        self._running = False
        logger.info("Vision adapter stopped.")

    def take_screenshot(self, filename: str) -> str:
        """Capture and save screenshot to AGENT_WORKSPACE/screenshots/."""
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        requested = Path(filename)
        if requested.name != filename:
            raise PermissionError("Filename must not include directory traversal.")
        output_path = (self.screenshots_dir / requested.name).resolve()
        if not str(output_path).startswith(str(self.screenshots_dir.resolve())):
            raise PermissionError("Screenshot path is outside screenshots directory.")

        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            shot = sct.grab(monitor)
            image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            image.save(output_path)

        return str(output_path)

    def ocr_image(self, image_path: str) -> str:
        """OCR stub for future extension."""
        _ = image_path
        return "OCR not implemented yet"

