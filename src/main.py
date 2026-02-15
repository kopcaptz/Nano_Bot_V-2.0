"""Application entrypoint for Nano Bot V-2.0."""
from __future__ import annotations

import asyncio
import logging
import signal

try:
    from adapters.browser_adapter import BrowserAdapter
    from adapters.mcp_adapter import MCPAdapter
    from adapters.system_adapter import SystemAdapter
    from adapters.telegram_adapter import TelegramAdapter
    from adapters.vision_adapter import VisionAdapter
    from config import load_config
    from core.event_bus import EventBus
    from core.handler import CommandHandler
    from core.llm_router import LLMRouter
    from core.memory import CrystalMemory
    from core.tool_registry import ToolRegistry
except ModuleNotFoundError:
    from src.adapters.browser_adapter import BrowserAdapter
    from src.adapters.mcp_adapter import MCPAdapter
    from src.adapters.system_adapter import SystemAdapter
    from src.adapters.telegram_adapter import TelegramAdapter
    from src.adapters.vision_adapter import VisionAdapter
    from src.config import load_config
    from src.core.event_bus import EventBus
    from src.core.handler import CommandHandler
    from src.core.llm_router import LLMRouter
    from src.core.memory import CrystalMemory
    from src.core.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

# Static MCP tool definitions
MCP_TOOL_DEFINITIONS = {
    "gmail": [
        {
            "type": "function",
            "function": {
                "name": "gmail_search_messages",
                "description": "Search for messages in Gmail.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query."},
                        "limit": {"type": "integer", "description": "Max results.", "default": 10},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "gmail_get_thread",
                "description": "Get full content of an email thread.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thread_id": {"type": "string", "description": "Thread ID."},
                    },
                    "required": ["thread_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "gmail_send_message",
                "description": "Send an email from Gmail.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email."},
                        "subject": {"type": "string", "description": "Email subject."},
                        "body": {"type": "string", "description": "Email body."},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
        },
    ],
}


async def main() -> None:
    """Initialize all components and run until shutdown signal."""
    config = load_config()
    event_bus = EventBus()
    memory = CrystalMemory()
    llm_router = LLMRouter(
        api_key=config.openrouter_api_key,
        model=config.openrouter_model,
    )

    # Initialize adapters
    telegram_adapter = TelegramAdapter(event_bus=event_bus, token=config.telegram_bot_token)
    system_adapter = SystemAdapter(workspace=config.agent_workspace)
    browser_adapter = BrowserAdapter()
    vision_adapter = VisionAdapter(workspace=config.agent_workspace)
    mcp_adapter = MCPAdapter()

    adapters = {
        "telegram": telegram_adapter,
        "system": system_adapter,
        "browser": browser_adapter,
        "vision": vision_adapter,
        "mcp": mcp_adapter,
    }

    # Initialize tool registry
    tool_registry = ToolRegistry(mcp_adapter=mcp_adapter)
    tool_registry.register_adapter(system_adapter, "system")
    tool_registry.register_adapter(browser_adapter, "browser")
    tool_registry.register_adapter(vision_adapter, "vision")

    for server, tools in MCP_TOOL_DEFINITIONS.items():
        tool_registry.register_mcp_tools(server, tools)

    logger.info("Registered tools: %s", tool_registry.get_tool_names())

    # Initialize command handler
    command_handler = CommandHandler(
        event_bus=event_bus,
        llm_router=llm_router,
        memory=memory,
        tool_registry=tool_registry,
        telegram=telegram_adapter,
        system=system_adapter,
        browser=browser_adapter,
        vision=vision_adapter,
    )
    await command_handler.initialize()

    # Shutdown handling
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
            await adapter.start()
            is_running = bool(getattr(adapter, "is_running", getattr(adapter, "_running", True)))
            if is_running:
                logger.info("Adapter '%s' started.", name)
            else:
                logger.warning("Adapter '%s' did not enter running state.", name)
            return is_running
        except Exception:
            logger.exception("Adapter '%s' failed to start.", name)
            return False

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(request_shutdown(f"signal {s.name}")),
            )
        except NotImplementedError:
            logger.warning("Signal handlers are not supported on this platform.")

    try:
        start_results = await asyncio.gather(
            *(start_adapter(name, adapter) for name, adapter in adapters.items())
        )
        started_count = sum(1 for ok in start_results if ok)
        if started_count == 0:
            logger.error("No adapters running; requesting shutdown.")
            await request_shutdown("no adapters running")

        logger.info("Nano Bot V-2.0 started. %d adapters active.", started_count)
        await shutdown_event.wait()
    except KeyboardInterrupt:
        await request_shutdown("keyboard interrupt")
    except Exception:
        logger.exception("Fatal error in main runtime loop.")
    finally:
        logger.info("Stopping adapters...")
        await asyncio.gather(
            *(adapter.stop() for adapter in adapters.values()),
            return_exceptions=True,
        )
        logger.info("Nano Bot V-2.0 stopped.")


if __name__ == "__main__":
    asyncio.run(main())
