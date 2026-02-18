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
    # Emergency token guards (keep context compact by default)
    MAX_MEMORY_CONTEXT_CHARS = 2500
    MAX_SKILLS_SECTION_CHARS = 2200
    MAX_RELEVANT_SKILLS = 3
    MAX_AVAILABLE_SKILLS = 12
    MAX_SKILL_DESCRIPTION_CHARS = 140
    MIN_RELEVANT_SKILL_SCORE = 0.45
    MAX_RELEVANT_SKILL_DISTANCE = 0.55
    
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
        
        # Memory context (guarded by budget)
        raw_memory = self.memory.get_memory_context()
        memory = self._truncate_text(raw_memory, self.MAX_MEMORY_CONTEXT_CHARS)
        if memory:
            parts.append(f"# Memory\n\n{memory}")
        
        # Skills via SkillManager (fallback if skill_manager is None).
        # Emergency mitigation: include compact summaries only (no full SKILL content).
        skills_parts = []
        seen: set[str] = set()
        elapsed_always_load_ms = 0.0
        elapsed_search_ms = 0.0
        search_error: str | None = None
        relevant_count = 0
        available_count = 0
        
        if self.skill_manager:
            try:
                # 1. Always-load skills (with timing)
                t0_always = time.perf_counter()
                always_skills = self.skill_manager.list_always_load_skills()
                elapsed_always_load_ms = (time.perf_counter() - t0_always) * 1000
                
                pinned_lines = []
                for skill in always_skills:
                    name = str(skill.get("name", "")).strip()
                    if not name:
                        continue
                    seen.add(name)
                    desc = self._format_skill_description(
                        skill.get("description", name),
                        self.MAX_SKILL_DESCRIPTION_CHARS,
                    )
                    pinned_lines.append(f"- {name}: {desc} (pinned)")
                if pinned_lines:
                    skills_parts.append("# Pinned Skills\n\n" + "\n".join(pinned_lines))
                
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
                    relevant_lines = []
                    for r in search_results:
                        if not self._is_relevant_skill_result(r):
                            continue
                        name = str(r.get("skill_name", "")).strip()
                        if not name or name in seen:
                            continue
                        seen.add(name)
                        skill = self.skill_manager.get_skill(name) or {}
                        desc = self._format_skill_description(
                            skill.get("description", name),
                            self.MAX_SKILL_DESCRIPTION_CHARS,
                        )
                        score = self._get_score(r)
                        distance = self._get_distance(r)
                        suffix = []
                        if score is not None:
                            suffix.append(f"score={score:.2f}")
                        if distance is not None:
                            suffix.append(f"distance={distance:.2f}")
                        tag = f" ({', '.join(suffix)})" if suffix else ""
                        relevant_lines.append(f"- {name}: {desc}{tag}")
                        if len(relevant_lines) >= self.MAX_RELEVANT_SKILLS:
                            break
                    relevant_count = len(relevant_lines)
                    if relevant_lines:
                        skills_parts.append("# Relevant Skills\n\n" + "\n".join(relevant_lines))
                
                # 3. Available Skills (summary of remaining)
                all_skills = self.skill_manager.list_skills()
                available = [s for s in all_skills if s.get("name") not in seen]
                if available:
                    summary_lines = []
                    for s in available[: self.MAX_AVAILABLE_SKILLS]:
                        name = str(s.get("name", "")).strip()
                        if not name:
                            continue
                        desc = self._format_skill_description(
                            s.get("description", name),
                            self.MAX_SKILL_DESCRIPTION_CHARS,
                        )
                        summary_lines.append(f"- {name}: {desc}")
                    remaining = max(0, len(available) - len(summary_lines))
                    available_count = len(summary_lines)
                    if remaining:
                        summary_lines.append(f"- ... and {remaining} more skills")
                    skills_parts.append(
                        "# Available Skills\n\n"
                        + "\n".join(summary_lines)
                        + "\n\nUse read_file to load a skill only when needed."
                    )
            except Exception as e:
                logger.warning("SkillManager error in build_system_prompt: {}", e)
        
        if skills_parts:
            skills_text = self._truncate_text(
                "\n\n".join(skills_parts),
                self.MAX_SKILLS_SECTION_CHARS,
            )
            if skills_text:
                parts.append(skills_text)
        
        elapsed_total_ms = (time.perf_counter() - t_total_start) * 1000
        final_prompt = "\n\n---\n\n".join(parts)
        metrics = {
            "event": "build_system_prompt",
            "always_load_ms": round(elapsed_always_load_ms, 2),
            "semantic_search_ms": round(elapsed_search_ms, 2),
            "total_ms": round(elapsed_total_ms, 2),
            "memory_chars": len(memory),
            "skills_chars": len(parts[-1]) if skills_parts else 0,
            "relevant_skills_count": relevant_count,
            "available_skills_count": available_count,
            "prompt_chars": len(final_prompt),
        }
        if not self.skill_manager:
            metrics["skill_manager"] = False
        if search_error:
            metrics["error"] = search_error
        logger.info(json.dumps(metrics))
        
        return final_prompt

    def _truncate_text(self, text: str, max_chars: int) -> str:
        """Truncate long text safely with a visible marker."""
        if not text:
            return ""
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        marker = "\n\n[...truncated to reduce token usage...]"
        keep = max(0, max_chars - len(marker))
        return text[:keep].rstrip() + marker

    def _format_skill_description(self, description: str | Any, max_chars: int) -> str:
        """Normalize and compact skill description text."""
        text = " ".join(str(description or "").strip().split())
        if not text:
            return "No description."
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…"

    def _get_score(self, result: dict[str, Any]) -> float | None:
        """Extract numeric relevance score if present."""
        value = result.get("score")
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _get_distance(self, result: dict[str, Any]) -> float | None:
        """Extract numeric vector distance if present."""
        value = result.get("distance")
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _is_relevant_skill_result(self, result: dict[str, Any]) -> bool:
        """Apply relevance threshold guard for semantic skill results."""
        score = self._get_score(result)
        if score is not None:
            return score >= self.MIN_RELEVANT_SKILL_SCORE
        distance = self._get_distance(result)
        if distance is not None:
            return distance <= self.MAX_RELEVANT_SKILL_DISTANCE
        # If score/distance absent, keep conservative and do not auto-inject.
        return False
    
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
