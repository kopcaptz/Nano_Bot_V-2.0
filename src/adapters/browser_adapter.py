"""Browser automation adapter based on Playwright."""

from __future__ import annotations

import logging

from playwright.async_api import Browser, Page, Playwright, async_playwright

try:  # script mode
    from adapters.base_adapter import BaseAdapter
except ModuleNotFoundError:  # package mode
    from src.adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)


class BrowserAdapter(BaseAdapter):
    """Adapter for basic browser automation tasks."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            logger.debug("Browser adapter already running.")
            return
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            self._page = await self._browser.new_page()
            self._running = True
            logger.info("Browser adapter started.")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to start browser adapter.")
            await self.stop()
            raise

    async def stop(self) -> None:
        if not self._running and self._playwright is None and self._browser is None and self._page is None:
            logger.debug("Browser adapter already stopped.")
            return
        if self._page:
            await self._page.close()
            self._page = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._running = False
        logger.info("Browser adapter stopped.")

    def _ensure_running(self) -> None:
        if not self._running or self._page is None:
            raise RuntimeError("Browser adapter is not running.")

    async def open_url(self, url: str) -> None:
        self._ensure_running()
        await self._page.goto(url, wait_until="domcontentloaded")

    async def get_page_text(self, url: str | None = None) -> str:
        self._ensure_running()
        if url:
            await self.open_url(url)
        return await self._page.inner_text("body")

