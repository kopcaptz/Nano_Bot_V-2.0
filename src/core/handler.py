"""Central command coordinator for Nano Bot V-2.0 (Tool-Using Agent)."""
from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

try:
    from core.event_bus import EventBus
    from core.llm_router import LLMRouter
    from core.memory import CrystalMemory
except ModuleNotFoundError:
    from src.core.event_bus import EventBus
    from src.core.llm_router import LLMRouter
    from src.core.memory import CrystalMemory

if TYPE_CHECKING:
    from src.core.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 5


class CommandHandler:
    """Coordinates incoming commands, LLM processing, and tool execution."""

    def __init__(
        self,
        event_bus: EventBus,
        llm_router: LLMRouter,
        memory: CrystalMemory,
        tool_registry: ToolRegistry,
        **adapters: Any,
    ) -> None:
        self.event_bus = event_bus
        self.llm_router = llm_router
        self.memory = memory
        self.tool_registry = tool_registry
        self.system = adapters.get("system")
        self.browser = adapters.get("browser")
        self.vision = adapters.get("vision")

    async def initialize(self) -> None:
        """Subscribe to relevant events."""
        await self.event_bus.subscribe(
            "telegram.command.received", self.handle_command
        )

    def _build_system_prompt(self) -> str:
        """Build the dynamic system prompt with all available tools."""
        tool_names = ", ".join(self.tool_registry.get_tool_names())
        return (
            "You are Nano Bot — a helpful AI assistant running locally on the user's Windows machine. "
            "You have real tools to interact with the system: manage files, run commands, open browser, "
            "take screenshots, search Gmail, and more.\n\n"
            "IMPORTANT RULES:\n"
            "1. When the user asks to DO something (create file, check email, open browser), "
            "you MUST use the appropriate tool. Do NOT just describe what you would do.\n"
            "2. You can chain multiple tool calls in sequence.\n"
            "3. If a tool returns an error, explain it to the user and suggest alternatives.\n"
            "4. For simple conversation (greetings, questions), respond normally without tools.\n\n"
            f"Available tools: {tool_names}"
        )

    async def _agent_loop(self, command: str, chat_id: int) -> str:
        """The main agent loop: Think -> Act -> Observe -> Repeat."""
        system_prompt = self._build_system_prompt()
        history = self.memory.get_history(chat_id)

        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": command},
        ]

        tools = self.tool_registry.get_tools_for_llm()

        for iteration in range(MAX_AGENT_ITERATIONS):
            logger.info("Agent loop iteration %d for chat %d", iteration + 1, chat_id)

            llm_response = await self.llm_router.process_command(
                command="",
                context=[],
                tools=tools,
                messages_override=messages,
            )

            tool_calls = llm_response.get("tool_calls")

            # No tool calls — this is the final text answer
            if not tool_calls:
                return LLMRouter.extract_text(llm_response.get("content", ""))

            # Append assistant message with tool_calls to conversation
            messages.append(llm_response)

            # Execute each tool call
            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")

                try:
                    params = json.loads(raw_args)
                except json.JSONDecodeError:
                    tool_result = f"Error: Could not parse tool arguments: {raw_args}"
                else:
                    tool_result = await self.tool_registry.dispatch(tool_name, params)

                # Ensure tool_result is a string
                if not isinstance(tool_result, str):
                    tool_result = str(tool_result)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

        # Max iterations reached — ask LLM for a final summary
        messages.append({
            "role": "user",
            "content": "Please summarize what you have done so far.",
        })
        final = await self.llm_router.process_command(
            command="", context=[], messages_override=messages
        )
        return LLMRouter.extract_text(final.get("content", ""))

    async def _try_shortcuts(self, command: str) -> str | None:
        """Handle slash commands that bypass the LLM."""
        parts = command.strip().split()
        if not parts:
            return None
        cmd, args = parts[0], parts[1:]

        try:
            if cmd == "/system" and args and self.system:
                return await self.system.run_app(" ".join(args))
            if cmd == "/browser_open" and args and self.browser:
                await self.browser.open_url(args[0])
                return f"Opened: {args[0]}"
            if cmd == "/browser_text" and self.browser:
                return await self.browser.get_page_text(args[0] if args else None)
            if cmd == "/screenshot" and args and self.vision:
                return self.vision.take_screenshot(args[0])
        except Exception as e:
            logger.exception("Shortcut error: %s", command)
            return f"Error: {e}"

        return None

    async def handle_command(self, event_data: dict[str, Any]) -> None:
        """Main entry point for handling user commands."""
        raw_chat_id = event_data.get("chat_id")
        try:
            chat_id = int(raw_chat_id)
        except (TypeError, ValueError):
            logger.warning("Invalid chat_id in command event: %s", raw_chat_id)
            return
        command = str(event_data.get("command", "")).strip()
        if not command:
            await self.event_bus.publish(
                "telegram.send.reply",
                {"chat_id": chat_id, "text": "Empty command. Send a text request."},
            )
            return

        self.memory.add_message(chat_id, "user", command)

        # Try slash shortcuts first
        shortcut = await self._try_shortcuts(command)
        if shortcut is not None:
            response_text = shortcut
        else:
            # Run the full agent loop
            response_text = await self._agent_loop(command, chat_id)

        self.memory.add_message(chat_id, "assistant", response_text)
        await self.event_bus.publish(
            "telegram.send.reply", {"chat_id": chat_id, "text": response_text}
        )
