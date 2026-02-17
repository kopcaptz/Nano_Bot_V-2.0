"""Context builder for assembling agent prompts."""

import base64
import json
import mimetypes
import platform
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.agent.memory import MemoryStore
from nanobot.memory.db import semantic_search

if TYPE_CHECKING:
    from nanobot.agent.skill_manager import SkillManager


class ContextBuilder:
    """
    Builds the context (system prompt + messages) for the agent.
    
    Assembles bootstrap files, memory, skills, and conversation history
    into a coherent prompt for the LLM.
    """
    
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]
    
    def __init__(self, workspace: Path, skill_manager: "SkillManager | None" = None):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skill_manager = skill_manager
    
    def build_system_prompt(
        self,
        user_query: str = "",
        skill_names: list[str] | None = None,
    ) -> str:
        """
        Build the system prompt from bootstrap files, memory, and skills.
        
        Args:
            user_query: Current user message for semantic skill search.
            skill_names: Optional list of skills to include (kept for compatibility).
        
        Returns:
            Complete system prompt.
        """
        t_total_start = time.perf_counter()
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
        
        # Skills via SkillManager (fallback if skill_manager is None)
        skills_parts = []
        seen: set[str] = set()
        elapsed_always_load_ms = 0.0
        elapsed_search_ms = 0.0
        search_error: str | None = None
        
        if self.skill_manager:
            try:
                # 1. Always-load skills (with timing)
                t0_always = time.perf_counter()
                always_skills = self.skill_manager.list_always_load_skills()
                elapsed_always_load_ms = (time.perf_counter() - t0_always) * 1000
                
                active_content_parts = []
                for skill in always_skills:
                    content = skill.get("content", "")
                    if content:
                        name = skill.get("name", "")
                        if name:
                            seen.add(name)
                        active_content_parts.append(f"### Skill: {name}\n\n{content}")
                
                # 2. Semantic search (with timing)
                search_results = []
                if user_query and len(user_query.strip()) > 3:
                    t0_search = time.perf_counter()
                    try:
                        search_results = self.skill_manager.search_skills(
                            user_query, limit=3
                        )
                        elapsed_search_ms = (time.perf_counter() - t0_search) * 1000
                    except Exception as e:
                        elapsed_search_ms = (time.perf_counter() - t0_search) * 1000
                        search_error = str(e)
                        logger.warning("search_skills failed: {}", e)
                    for r in search_results:
                        name = r.get("skill_name")
                        if name and name not in seen:
                            seen.add(name)
                            skill = self.skill_manager.get_skill(name)
                            if skill and skill.get("content"):
                                active_content_parts.append(
                                    f"### Skill: {name} (relevant to query)\n\n{skill['content']}"
                                )
                
                if active_content_parts:
                    skills_parts.append(
                        "# Active Skills\n\n"
                        + "\n\n---\n\n".join(active_content_parts)
                    )
                
                # 3. Available Skills (summary of remaining)
                all_skills = self.skill_manager.list_skills()
                available = [s for s in all_skills if s.get("name") not in seen]
                if available:
                    summary_lines = [
                        f"- {s['name']}: {s.get('description', s['name'])}"
                        for s in available
                    ]
                    skills_parts.append(
                        "# Available Skills\n\n"
                        + "\n".join(summary_lines)
                        + "\n\nUse read_file to load a skill."
                    )
            except Exception as e:
                logger.warning("SkillManager error in build_system_prompt: {}", e)
        
        if skills_parts:
            parts.append("\n\n".join(skills_parts))
        
        elapsed_total_ms = (time.perf_counter() - t_total_start) * 1000
        metrics = {
            "event": "build_system_prompt",
            "always_load_ms": round(elapsed_always_load_ms, 2),
            "semantic_search_ms": round(elapsed_search_ms, 2),
            "total_ms": round(elapsed_total_ms, 2),
        }
        if not self.skill_manager:
            metrics["skill_manager"] = False
        if search_error:
            metrics["error"] = search_error
        logger.info(json.dumps(metrics))
        
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
        system_prompt = self.build_system_prompt(user_query=current_message or "")
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
