"""Application entrypoint for Nano Bot V-2.0."""

from __future__ import annotations

import asyncio
import logging
import signal

try:  # script mode: python src/main.py
    from adapters.browser_adapter import BrowserAdapter
    from adapters.system_adapter import SystemAdapter
    from adapters.telegram_adapter import TelegramAdapter
    from adapters.vision_adapter import VisionAdapter
    from config import load_config
    from core.event_bus import EventBus
    from core.handler import CommandHandler
    from core.llm_router import LLMRouter
    from core.memory import CrystalMemory
except ModuleNotFoundError:  # package mode: import src.main
    from src.adapters.browser_adapter import BrowserAdapter
    from src.adapters.system_adapter import SystemAdapter
    from src.adapters.telegram_adapter import TelegramAdapter
    from src.adapters.vision_adapter import VisionAdapter
    from src.config import load_config
    from src.core.event_bus import EventBus
    from src.core.handler import CommandHandler
    from src.core.llm_router import LLMRouter
    from src.core.memory import CrystalMemory

logger = logging.getLogger(__name__)


async def main() -> None:
    """Initialize all components and run until shutdown signal."""
    config = load_config()

    event_bus = EventBus()
    memory = CrystalMemory()
    llm_router = LLMRouter(
        api_key=config.openrouter_api_key,
        model=config.openrouter_model,
    )

    telegram_adapter = TelegramAdapter(event_bus=event_bus, token=config.telegram_bot_token)
    system_adapter = SystemAdapter(workspace=config.agent_workspace)
    browser_adapter = BrowserAdapter()
    vision_adapter = VisionAdapter(workspace=config.agent_workspace)

    adapters = {
        "telegram": telegram_adapter,
        "system": system_adapter,
        "browser": browser_adapter,
        "vision": vision_adapter,
    }

    CommandHandler(
        event_bus=event_bus,
        llm_router=llm_router,
        memory=memory,
        telegram=telegram_adapter,
        system=system_adapter,
        browser=browser_adapter,
        vision=vision_adapter,
    )

    shutdown_event = asyncio.Event()
    shutdown_started = False

    async def request_shutdown(reason: str) -> None:
        nonlocal shutdown_started
        if shutdown_started:
            return
        shutdown_started = True
        logger.info("Shutdown requested: %s", reason)
        shutdown_event.set()

    async def run_adapters() -> None:
        await asyncio.gather(*(adapter.start() for adapter in adapters.values()))

    adapter_runner = asyncio.create_task(run_adapters(), name="adapter-runner")

    def _runner_done(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.exception("Adapter runner failed: %s", exc)
        if not shutdown_event.is_set():
            shutdown_event.set()

    adapter_runner.add_done_callback(_runner_done)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(request_shutdown(f"signal {s.name}")),
            )
        except NotImplementedError:
            logger.warning("Signal handlers are not supported on this platform.")

    logger.info("Nano Bot V-2.0 started.")
    await shutdown_event.wait()

    logger.info("Stopping adapters...")
    await asyncio.gather(*(adapter.stop() for adapter in adapters.values()), return_exceptions=True)

    if not adapter_runner.done():
        adapter_runner.cancel()
        await asyncio.gather(adapter_runner, return_exceptions=True)

    logger.info("Nano Bot V-2.0 stopped.")


if __name__ == "__main__":
    asyncio.run(main())

