"""Context builder for assembling agent prompts."""

import base64
import json
import mimetypes
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills import SkillsLoader
from nanobot.memory.db import semantic_search

# TTL for the cached MCP tool list (seconds).
_MCP_CACHE_TTL = 300


class ContextBuilder:
    """
    Builds the context (system prompt + messages) for the agent.
    
    Assembles bootstrap files, memory, skills, and conversation history
    into a coherent prompt for the LLM.
    """
    
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)
        self._mcp_cache: str = ""
        self._mcp_cache_ts: float = 0.0
    
    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """
        Build the system prompt from bootstrap files, memory, and skills.
        
        Args:
            skill_names: Optional list of skills to include.
        
        Returns:
            Complete system prompt.
        """
        parts = []
        
        # Core identity
        parts.append(self._get_identity())
        
        # Bootstrap files
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)
        
        # Memory context
        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")
        
        # Skills - progressive loading
        # 1. Always-loaded skills: include full content
        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")
        
        # 2. Available skills: only show summary (agent uses read_file to load)
        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")

        # 3. MCP tools discovered from connected servers
        mcp_summary = self._build_mcp_tools_summary()
        if mcp_summary:
            parts.append(mcp_summary)
        
        return "\n\n---\n\n".join(parts)
    
    def _get_identity(self) -> str:
        """Get the core identity section."""
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"
        
        return f"""# nanobot 🐈

You are nanobot, a helpful AI assistant. You have access to tools that allow you to:
- Read, write, and edit files
- Execute shell commands
- Search the web and fetch web pages
- Send messages to users on chat channels
- Spawn subagents for complex background tasks
- Search your long-term memory (memory_search tool)
- Call remote MCP servers for external services (mcp tool)

## MCP (External Services)

Для работы с внешними сервисами (Asana, Notion, Google Calendar и др.) используй
инструмент **mcp**, передавая в него `server`, `tool_name` и `params` из списка
доступных MCP-инструментов, приведённого в конце системного промпта.
Если список пуст — MCP-серверы не подключены, и вызывать инструмент mcp не нужно.

## Your Memory

You have **long-term memory** that persists across sessions:

1. **Operational (session)**: The current conversation — you remember everything discussed in this chat.
2. **Long-term (persistent)**:
   - **MEMORY.md** — facts you write here persist; you can add important information about the user.
   - **Structured facts** — extracted from dialogues (domain, category, sub_category); auto-loaded when relevant.
   - **memory_search** — use this tool to recall facts (user preferences, project details, past decisions).
3. **Daily notes** — YYYY-MM-DD.md files for dated context.

Relevant facts from your memory are automatically added to your context. Use memory_search when you need to recall something specific.

## Current Time
{now}

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Memory files: {workspace_path}/memory/MEMORY.md
- Daily notes: {workspace_path}/memory/YYYY-MM-DD.md
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

IMPORTANT: When responding to direct questions or conversations, reply directly with your text response.
Only use the 'message' tool when you need to send a message to a specific chat channel (like WhatsApp).
For normal conversation, just respond with text - do not call the message tool.

Always be helpful, accurate, and concise. When using tools, explain what you're doing.
When remembering something, write to {workspace_path}/memory/MEMORY.md"""
    
    def _load_bootstrap_files(self) -> str:
        """Load all bootstrap files from workspace."""
        parts = []
        
        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")
        
        return "\n\n".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # MCP discovery
    # ------------------------------------------------------------------

    def _build_mcp_tools_summary(self) -> str:
        """Discover available MCP tools and return a formatted summary.

        Runs ``manus-mcp-cli tool list --json``, parses the output, and
        produces a concise listing the LLM can reference when deciding
        which MCP tool to call.

        The result is cached for ``_MCP_CACHE_TTL`` seconds so that we
        don't shell out on every message.

        Returns:
            Formatted section string, or empty string when no tools are
            available or the CLI is missing.
        """
        now = time.monotonic()
        if self._mcp_cache and (now - self._mcp_cache_ts) < _MCP_CACHE_TTL:
            return self._mcp_cache

        summary = self._fetch_mcp_tools_summary()
        self._mcp_cache = summary
        self._mcp_cache_ts = now
        return summary

    def _fetch_mcp_tools_summary(self) -> str:
        """Execute the CLI and build the summary string (no caching)."""
        try:
            result = subprocess.run(
                ["manus-mcp-cli", "tool", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except FileNotFoundError:
            logger.debug("manus-mcp-cli not found — MCP tools section skipped")
            return ""
        except subprocess.TimeoutExpired:
            logger.warning("manus-mcp-cli tool list timed out")
            return ""

        if result.returncode != 0:
            stderr = result.stderr.strip()
            logger.warning("manus-mcp-cli tool list failed (exit {}): {}", result.returncode, stderr)
            return ""

        stdout = result.stdout.strip()
        if not stdout:
            return ""

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            logger.warning("manus-mcp-cli returned invalid JSON: {}", exc)
            return ""

        tools: list[dict[str, Any]] = []
        if isinstance(data, list):
            tools = data
        elif isinstance(data, dict):
            tools = data.get("tools", [])

        if not tools:
            return ""

        return self._format_mcp_tools(tools)

    @staticmethod
    def _format_mcp_tools(tools: list[dict[str, Any]]) -> str:
        """Format a list of MCP tool descriptors into a prompt section."""
        lines: list[str] = []

        for tool in tools:
            name = tool.get("name", "")
            server = tool.get("server", "")
            description = tool.get("description", "")
            if not name:
                continue

            params_schema = tool.get("inputSchema") or tool.get("parameters") or {}
            props = params_schema.get("properties", {})
            required = set(params_schema.get("required", []))

            param_parts: list[str] = []
            for pname, pdef in props.items():
                ptype = pdef.get("type", "any")
                marker = "" if pname in required else "?"
                param_parts.append(f"{pname}{marker}: {ptype}")

            sig = ", ".join(param_parts)
            prefix = f"{server}.{name}" if server else name
            line = f"- {prefix}({sig})"
            if description:
                line += f"  — {description}"
            lines.append(line)

        if not lines:
            return ""

        header = (
            "# Доступные MCP-инструменты\n\n"
            "Для вызова используй инструмент **mcp** с параметрами "
            "`server`, `tool_name`, `params`.\n"
        )
        return header + "\n".join(lines)
    
    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Build the complete message list for an LLM call.

        Args:
            history: Previous conversation messages.
            current_message: The new user message.
            skill_names: Optional skills to include.
            media: Optional list of local file paths for images/media.
            channel: Current channel (telegram, feishu, etc.).
            chat_id: Current chat/user ID.

        Returns:
            List of messages including system prompt.
        """
        messages = []

        # System prompt
        system_prompt = self.build_system_prompt(skill_names)
        if channel and chat_id:
            system_prompt += f"\n\n## Current Session\nChannel: {channel}\nChat ID: {chat_id}"
        messages.append({"role": "system", "content": system_prompt})

        # Автоматическое обогащение контекста из памяти
        if current_message and len(current_message) > 10:
            try:
                relevant_facts = semantic_search(current_message, limit=5)
                if relevant_facts:
                    facts_text = "\n".join(
                        f"- [{f.get('domain', 'general')}] {f.get('category', '?')} → {f.get('key', '?')}: {f.get('value', '?')}"
                        for f in relevant_facts
                        if f.get("distance", 1.0) < 0.7
                    )
                    if facts_text:
                        messages.append({
                            "role": "system",
                            "content": f"Relevant facts from your memory:\n{facts_text}",
                        })
            except Exception:
                pass

        # History
        messages.extend(history)

        # Current message (with optional image attachments)
        user_content = self._build_user_content(current_message, media)
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """Build user message content with optional base64-encoded images."""
        if not media:
            return text
        
        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        
        if not images:
            return text
        return images + [{"type": "text", "text": text}]
    
    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str
    ) -> list[dict[str, Any]]:
        """
        Add a tool result to the message list.
        
        Args:
            messages: Current message list.
            tool_call_id: ID of the tool call.
            tool_name: Name of the tool.
            result: Tool execution result.
        
        Returns:
            Updated message list.
        """
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result
        })
        return messages
    
    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Add an assistant message to the message list.
        
        Args:
            messages: Current message list.
            content: Message content.
            tool_calls: Optional tool calls.
            reasoning_content: Thinking output (Kimi, DeepSeek-R1, etc.).
        
        Returns:
            Updated message list.
        """
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
        
        if tool_calls:
            msg["tool_calls"] = tool_calls
        
        # Thinking models reject history without this
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        
        messages.append(msg)
        return messages
