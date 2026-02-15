"""Browser automation adapter based on Playwright."""

from __future__ import annotations

import logging

from playwright.async_api import Browser, Page, Playwright, async_playwright

from adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)


class BrowserAdapter(BaseAdapter):
    """Adapter for basic browser automation tasks."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._page = await self._browser.new_page()
        logger.info("Browser adapter started.")

    async def stop(self) -> None:
        if self._page:
            await self._page.close()
            self._page = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Browser adapter stopped.")

    async def open_url(self, url: str) -> None:
        if self._page is None:
            raise RuntimeError("Browser adapter is not started.")
        await self._page.goto(url, wait_until="domcontentloaded")

    async def get_page_text(self, url: str | None = None) -> str:
        if self._page is None:
            raise RuntimeError("Browser adapter is not started.")
        if url:
            await self.open_url(url)
        return await self._page.inner_text("body")

