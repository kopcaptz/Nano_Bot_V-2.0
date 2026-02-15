"""Agent loop: the core processing engine."""

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.agent.context import ContextBuilder
from nanobot.agent.reflection import Reflection
from nanobot.agent.tools.policy import ToolPolicy
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.memory import MemorySearchTool
from nanobot.agent.subagent import SubagentManager
from nanobot.memory.db import add_reflection
from nanobot.session.manager import Session, SessionManager


class AgentLoop:
    """
    The agent loop is the core processing engine.
    
    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """
    
    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        cron_service: "CronService | None" = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
    ):
        from nanobot.config.schema import ExecToolConfig
        from nanobot.cron.service import CronService
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        
        self.context = ContextBuilder(workspace)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.reflection = Reflection(provider=provider, model=self.model)
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )
        
        self._running = False
        self._register_default_tools()
    
    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        # File tools (restrict to workspace if configured)
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        self.tools.register(ReadFileTool(allowed_dir=allowed_dir))
        self.tools.register(WriteFileTool(allowed_dir=allowed_dir))
        self.tools.register(EditFileTool(allowed_dir=allowed_dir))
        self.tools.register(ListDirTool(allowed_dir=allowed_dir))
        
        # Shell tool
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
        ))
        
        # Web tools
        self.tools.register(WebSearchTool(api_key=self.brave_api_key))
        self.tools.register(WebFetchTool())

        # Memory search
        self.tools.register(MemorySearchTool())

        # Message tool
        message_tool = MessageTool(send_callback=self.bus.publish_outbound)
        self.tools.register(message_tool)
        
        # Spawn tool (for subagents)
        spawn_tool = SpawnTool(manager=self.subagents)
        self.tools.register(spawn_tool)
        
        # Cron tool (for scheduling)
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))
    
    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        logger.info("Agent loop started")
        
        while self._running:
            try:
                # Wait for next message
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(),
                    timeout=1.0
                )
                
                # Process it
                try:
                    response = await self._process_message(msg)
                    if response:
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    # Send error response
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Sorry, I encountered an error: {str(e)}"
                    ))
            except asyncio.TimeoutError:
                continue
    
    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")
    
    async def _process_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a single inbound message.
        
        Args:
            msg: The inbound message to process.
        
        Returns:
            The response message, or None if no response needed.
        """
        # Handle system messages (subagent announces)
        # The chat_id contains the original "channel:chat_id" to route back to
        if msg.channel == "system":
            return await self._process_system_message(msg)
        
        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info(f"Processing message from {msg.channel}:{msg.sender_id}: {preview}")
        
        # Get or create session
        session = self.sessions.get_or_create(msg.session_key)

        # Check if we're waiting for confirmation
        if session.pending_confirmation:
            return await self._handle_confirmation(session, msg)

        # Update tool contexts
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(msg.channel, msg.chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(msg.channel, msg.chat_id)
        
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(msg.channel, msg.chat_id)
        
        # Build initial messages (use get_history for LLM-formatted messages)
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
        )
        
        # Agent loop
        iteration = 0
        final_content = None
        
        while iteration < self.max_iterations:
            iteration += 1
            
            # Call LLM
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )
            
            # Handle tool calls
            if response.has_tool_calls:
                # Add assistant message with tool calls
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)  # Must be JSON string
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )
                
                # Execute tools (with policy check)
                for tool_call in response.tool_calls:
                    tool_name = tool_call.name
                    tool_args = tool_call.arguments
                    args_str = json.dumps(tool_args, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_name}({args_str[:200]})")

                    # Check tool policy
                    policy = self.tools.get_policy(tool_name)

                    if policy == ToolPolicy.DENY:
                        result = f"Error: Tool '{tool_name}' is not allowed to execute."
                        messages = self.context.add_tool_result(
                            messages, tool_call.id, tool_name, result
                        )
                        continue

                    if policy == ToolPolicy.REQUIRE_CONFIRMATION:
                        # Ask user for confirmation
                        session.pending_confirmation = {
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "tool_call_id": tool_call.id,
                            "description": f"Execute {tool_name} with args: {tool_args}",
                            "messages": copy.deepcopy(messages),
                            "assistant_content": response.content,
                            "reasoning_content": response.reasoning_content,
                            "original_user_message": msg.content,
                        }
                        self.sessions.save(session)

                        await self.bus.publish_outbound(OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=f"⚠️ Confirmation required:\n\nTool: `{tool_name}`\nArguments: `{args_str[:500]}`\n\nProceed? (yes/no)",
                            metadata=msg.metadata or {},
                        ))
                        return None

                    # policy == ToolPolicy.ALLOW - execute normally
                    result = await self.tools.execute(tool_name, tool_args)

                    # Reflection on tool error (insight logged only, LLM gets error via tool_result)
                    if result.startswith("Error:"):
                        logger.warning(f"Tool {tool_name} failed: {result[:200]}")
                        try:
                            insight = await self.reflection.analyze_trajectory(
                                messages=messages,
                                failed_tool_call={"name": tool_name, "arguments": tool_args},
                                error_result=result,
                            )
                            if insight:
                                logger.info(f"Reflection: {insight[:200]}")
                                add_reflection(
                                    tool_name=tool_name,
                                    tool_args=args_str[:500],
                                    error_text=result[:500],
                                    insight=insight[:1000],
                                    session_key=msg.session_key,
                                )
                        except Exception as e:
                            logger.warning(f"Reflection failed: {e}")

                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_name, result
                    )
            else:
                # No tool calls, we're done
                final_content = response.content
                break
        
        if final_content is None:
            final_content = "I've completed processing but have no response to give."
        
        # Log response preview
        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info(f"Response to {msg.channel}:{msg.sender_id}: {preview}")
        
        # Save to session
        session.add_message("user", msg.content)
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=msg.metadata or {},  # Pass through for channel-specific needs (e.g. Slack thread_ts)
        )

    async def _handle_confirmation(self, session: Session, msg: InboundMessage) -> OutboundMessage | None:
        """Handle user confirmation for pending tool execution."""
        user_response = msg.content.strip().lower()
        pending = session.pending_confirmation

        if user_response in ["yes", "y", "да", "д"]:
            # User confirmed - execute the tool
            tool_name = pending["tool_name"]
            tool_args = pending["tool_args"]

            result = await self.tools.execute(tool_name, tool_args)

            # Reflection on tool error
            if result.startswith("Error:"):
                logger.warning(f"Tool {tool_name} failed: {result[:200]}")
                try:
                    insight = await self.reflection.analyze_trajectory(
                        messages=pending["messages"],
                        failed_tool_call={"name": tool_name, "arguments": tool_args},
                        error_result=result,
                    )
                    if insight:
                        logger.info(f"Reflection: {insight[:200]}")
                        add_reflection(
                            tool_name=tool_name,
                            tool_args=json.dumps(tool_args, ensure_ascii=False)[:500],
                            error_text=result[:500],
                            insight=insight[:1000],
                            session_key=msg.session_key,
                        )
                except Exception as e:
                    logger.warning(f"Reflection failed: {e}")

            messages = self.context.add_tool_result(
                pending["messages"],
                pending["tool_call_id"],
                tool_name,
                result,
            )

            # Clear pending confirmation and get original user message before clearing
            original_user_message = pending.get("original_user_message", msg.content)
            session.pending_confirmation = None
            self.sessions.save(session)

            # Continue processing
            return await self._continue_after_tool(
                session, msg, messages, original_user_message
            )

        elif user_response in ["no", "n", "нет", "н"]:
            # User declined
            session.add_message(
                "user",
                pending.get("original_user_message", "User declined"),
            )
            session.add_message("assistant", "Tool execution cancelled by user.")
            session.pending_confirmation = None
            self.sessions.save(session)

            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="Understood. I won't execute that command. How can I help you?",
                metadata=msg.metadata or {},
            ))
            return None
        else:
            # Invalid response - ask again
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=f"Please respond with 'yes' or 'no' to confirm: {pending['description']}",
                metadata=msg.metadata or {},
            ))
            return None

    async def _continue_after_tool(
        self,
        session: Session,
        msg: InboundMessage,
        messages: list[dict[str, Any]],
        original_user_message: str,
    ) -> OutboundMessage | None:
        """Continue agent loop after tool execution (post-confirmation)."""
        iteration = 0
        final_content = None

        while iteration < self.max_iterations:
            iteration += 1

            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
            )

            if response.has_tool_calls:
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )

                for tool_call in response.tool_calls:
                    tool_name = tool_call.name
                    tool_args = tool_call.arguments
                    args_str = json.dumps(tool_args, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_name}({args_str[:200]})")

                    policy = self.tools.get_policy(tool_name)

                    if policy == ToolPolicy.DENY:
                        result = f"Error: Tool '{tool_name}' is not allowed to execute."
                        messages = self.context.add_tool_result(
                            messages, tool_call.id, tool_name, result
                        )
                        continue

                    if policy == ToolPolicy.REQUIRE_CONFIRMATION:
                        session.pending_confirmation = {
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "tool_call_id": tool_call.id,
                            "description": f"Execute {tool_name} with args: {tool_args}",
                            "messages": copy.deepcopy(messages),
                            "assistant_content": response.content,
                            "reasoning_content": response.reasoning_content,
                            "original_user_message": original_user_message,
                        }
                        self.sessions.save(session)

                        await self.bus.publish_outbound(OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=f"⚠️ Confirmation required:\n\nTool: `{tool_name}`\nArguments: `{args_str[:500]}`\n\nProceed? (yes/no)",
                            metadata=msg.metadata or {},
                        ))
                        return None

                    result = await self.tools.execute(tool_name, tool_args)

                    # Reflection on tool error
                    if result.startswith("Error:"):
                        logger.warning(f"Tool {tool_name} failed: {result[:200]}")
                        try:
                            insight = await self.reflection.analyze_trajectory(
                                messages=messages,
                                failed_tool_call={"name": tool_name, "arguments": tool_args},
                                error_result=result,
                            )
                            if insight:
                                logger.info(f"Reflection: {insight[:200]}")
                                add_reflection(
                                    tool_name=tool_name,
                                    tool_args=args_str[:500],
                                    error_text=result[:500],
                                    insight=insight[:1000],
                                    session_key=msg.session_key,
                                )
                        except Exception as e:
                            logger.warning(f"Reflection failed: {e}")

                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_name, result
                    )
            else:
                final_content = response.content
                break

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        session.add_message("user", original_user_message)
        session.add_message("assistant", final_content)
        self.sessions.save(session)

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=msg.metadata or {},
        )

    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a system message (e.g., subagent announce).
        
        The chat_id field contains "original_channel:original_chat_id" to route
        the response back to the correct destination.
        """
        logger.info(f"Processing system message from {msg.sender_id}")
        
        # Parse origin from chat_id (format: "channel:chat_id")
        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel = parts[0]
            origin_chat_id = parts[1]
        else:
            # Fallback
            origin_channel = "cli"
            origin_chat_id = msg.chat_id
        
        # Use the origin session for context
        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.sessions.get_or_create(session_key)
        
        # Update tool contexts
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(origin_channel, origin_chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(origin_channel, origin_chat_id)
        
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(origin_channel, origin_chat_id)
        
        # Build messages with the announce content
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
        )
        
        # Agent loop (limited for announce handling)
        iteration = 0
        final_content = None
        
        while iteration < self.max_iterations:
            iteration += 1
            
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )
            
            if response.has_tool_calls:
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )
                
                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)

                    # Reflection on tool error
                    if result.startswith("Error:"):
                        logger.warning(f"Tool {tool_call.name} failed: {result[:200]}")
                        try:
                            insight = await self.reflection.analyze_trajectory(
                                messages=messages,
                                failed_tool_call={
                                    "name": tool_call.name,
                                    "arguments": tool_call.arguments,
                                },
                                error_result=result,
                            )
                            if insight:
                                logger.info(f"Reflection: {insight[:200]}")
                                add_reflection(
                                    tool_name=tool_call.name,
                                    tool_args=args_str[:500],
                                    error_text=result[:500],
                                    insight=insight[:1000],
                                    session_key=f"{origin_channel}:{origin_chat_id}",
                                )
                        except Exception as e:
                            logger.warning(f"Reflection failed: {e}")

                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                final_content = response.content
                break

        if final_content is None:
            final_content = "Background task completed."
        
        # Save to session (mark as system message in history)
        session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content
        )
    
    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
    ) -> str:
        """
        Process a message directly (for CLI or cron usage).
        
        Args:
            content: The message content.
            session_key: Session identifier.
            channel: Source channel (for context).
            chat_id: Source chat ID (for context).
        
        Returns:
            The agent's response.
        """
        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content
        )
        
        response = await self._process_message(msg)
        return response.content if response else ""
