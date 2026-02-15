"""Vision adapter for screenshot capture and OCR stub."""

from __future__ import annotations

import logging
from pathlib import Path

import mss
from PIL import Image
from mss.exception import ScreenShotError

try:  # script mode
    from adapters.base_adapter import BaseAdapter
except ModuleNotFoundError:  # package mode
    from src.adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)


class VisionAdapter(BaseAdapter):
    """Adapter for screenshot operations."""
    ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

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

    def _ensure_running(self) -> None:
        if not self._running:
            raise RuntimeError("Vision adapter is not running.")

    def _resolve_workspace_path(self, path: str) -> Path:
        """Resolve path within workspace boundaries."""
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        resolved = candidate.resolve()
        workspace_resolved = self.workspace.resolve()
        if resolved != workspace_resolved and workspace_resolved not in resolved.parents:
            raise PermissionError("Path is outside agent workspace.")
        return resolved

    def take_screenshot(self, filename: str) -> str:
        """Capture and save screenshot to AGENT_WORKSPACE/screenshots/."""
        self._ensure_running()
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        safe_name = filename.strip()
        if not safe_name:
            raise PermissionError("Filename cannot be empty.")
        if "." not in safe_name:
            safe_name = f"{safe_name}.png"

        requested = Path(safe_name)
        if requested.name != safe_name:
            raise PermissionError("Filename must not include directory traversal.")
        ext = requested.suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise PermissionError(
                f"Unsupported screenshot extension '{ext}'. Allowed: {sorted(self.ALLOWED_EXTENSIONS)}"
            )
        output_path = (self.screenshots_dir / requested.name).resolve()
        screenshots_root = self.screenshots_dir.resolve()
        if output_path != screenshots_root and screenshots_root not in output_path.parents:
            raise PermissionError("Screenshot path is outside screenshots directory.")

        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(monitor)
                image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                image.save(output_path)
        except ScreenShotError as exc:
            raise RuntimeError(f"Cannot capture screenshot in current environment: {exc}") from exc

        return str(output_path)

    def ocr_image(self, image_path: str) -> str:
        """OCR stub for future extension."""
        self._ensure_running()
        safe_path = self._resolve_workspace_path(image_path)
        if not safe_path.exists() or not safe_path.is_file():
            raise FileNotFoundError(f"Image not found: {safe_path}")
        return "OCR not implemented yet"

