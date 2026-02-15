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
START_TIMEOUT_SECONDS = 20.0
STOP_TIMEOUT_SECONDS = 10.0


async def main() -> None:
    """Initialize all components and run until shutdown signal."""
    config = load_config()

    event_bus = EventBus()
    memory = CrystalMemory(max_messages_per_chat=config.memory_max_messages)
    llm_router = LLMRouter(
        api_key=config.openrouter_api_key,
        model=config.openrouter_model,
        max_context_messages=config.llm_context_max_messages,
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

    command_handler = CommandHandler(
        event_bus=event_bus,
        llm_router=llm_router,
        memory=memory,
        telegram=telegram_adapter,
        system=system_adapter,
        browser=browser_adapter,
        vision=vision_adapter,
    )
    await command_handler.initialize()

    shutdown_event = asyncio.Event()
    shutdown_started = False

    async def request_shutdown(reason: str) -> None:
        nonlocal shutdown_started
        if shutdown_started:
            return
        shutdown_started = True
        logger.info("Shutdown requested: %s", reason)
        shutdown_event.set()

    async def start_adapter(name: str, adapter: object) -> bool:
        try:
            await asyncio.wait_for(adapter.start(), timeout=START_TIMEOUT_SECONDS)
            is_running = bool(getattr(adapter, "is_running", getattr(adapter, "_running", True)))
            if is_running:
                logger.info("Adapter '%s' started.", name)
            else:
                logger.warning("Adapter '%s' did not enter running state.", name)
            return is_running
        except asyncio.TimeoutError:
            logger.error(
                "Adapter '%s' start timed out after %.1fs", name, START_TIMEOUT_SECONDS
            )
            try:
                await asyncio.wait_for(adapter.stop(), timeout=STOP_TIMEOUT_SECONDS)
            except Exception:  # noqa: BLE001
                logger.exception("Adapter '%s' cleanup after start timeout failed.", name)
            return False
        except Exception:  # noqa: BLE001
            logger.exception("Adapter '%s' failed to start.", name)
            return False

    async def stop_adapter(name: str, adapter: object) -> None:
        """Stop adapter with timeout guard to avoid hanging shutdown."""
        try:
            await asyncio.wait_for(adapter.stop(), timeout=STOP_TIMEOUT_SECONDS)
            logger.info("Adapter '%s' stopped.", name)
        except asyncio.TimeoutError:
            logger.error(
                "Adapter '%s' stop timed out after %.1fs", name, STOP_TIMEOUT_SECONDS
            )
        except Exception:  # noqa: BLE001
            logger.exception("Adapter '%s' failed during stop.", name)

    loop = asyncio.get_running_loop()

    def _signal_fallback_handler(sig_num: int, _frame: object) -> None:
        """Fallback signal handler when loop.add_signal_handler is unsupported."""
        try:
            sig_name = signal.Signals(sig_num).name
        except Exception:  # noqa: BLE001
            sig_name = str(sig_num)
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(request_shutdown(f"signal {sig_name} (fallback)"))
        )

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(request_shutdown(f"signal {s.name}")),
            )
        except NotImplementedError:
            try:
                signal.signal(sig, _signal_fallback_handler)
                logger.warning(
                    "loop.add_signal_handler unsupported; installed fallback for %s", sig.name
                )
            except Exception:  # noqa: BLE001
                logger.warning("Signal handlers are not supported on this platform.")

    try:
        # Per specification: start all adapters concurrently via asyncio.gather
        start_results = await asyncio.gather(
            *(start_adapter(name, adapter) for name, adapter in adapters.items())
        )
        started_names = [
            name for name, is_started in zip(adapters.keys(), start_results, strict=False) if is_started
        ]
        skipped_names = [
            name for name, is_started in zip(adapters.keys(), start_results, strict=False) if not is_started
        ]
        started_count = len(started_names)
        logger.info("Running adapters: %s", ", ".join(started_names) if started_names else "(none)")
        if skipped_names:
            logger.warning("Not running adapters: %s", ", ".join(skipped_names))
        if started_count == 0:
            logger.error("No adapters are running; requesting shutdown.")
            await request_shutdown("no adapters running")
        logger.info("Nano Bot V-2.0 started.")
        await shutdown_event.wait()
    except KeyboardInterrupt:
        await request_shutdown("keyboard interrupt")
    except Exception:  # noqa: BLE001
        logger.exception("Fatal error in main runtime loop.")
    finally:
        await command_handler.shutdown()
        logger.info("Stopping adapters...")
        await asyncio.gather(
            *(stop_adapter(name, adapter) for name, adapter in adapters.items()),
            return_exceptions=True,
        )
        logger.info("Nano Bot V-2.0 stopped.")


if __name__ == "__main__":
    asyncio.run(main())

