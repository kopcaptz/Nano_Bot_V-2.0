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
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._page = await self._browser.new_page()
        self._running = True
        logger.info("Browser adapter started.")

    async def stop(self) -> None:
        if not self._running:
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

    def get_tool_definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "open_url",
                    "description": "Open a URL in the browser.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "The full URL to open."}
                        },
                        "required": ["url"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_page_text",
                    "description": "Get the text content of the current page or a new URL.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "(Optional) URL to navigate to first."}
                        },
                    },
                },
            },
        ]

