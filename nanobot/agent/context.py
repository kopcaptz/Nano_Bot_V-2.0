"""Context builder for assembling agent prompts."""

import base64
import logging
import mimetypes
import platform
from pathlib import Path
from typing import Any

from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills import SkillsLoader
from nanobot.memory.db import semantic_search, get_facts_filtered

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Builds the context (system prompt + messages) for the agent.
    
    Assembles bootstrap files, memory, skills, and conversation history
    into a coherent prompt for the LLM.

    Memory hierarchy (primary → auxiliary):
      1. Structured facts in SQLite + ChromaDB  (nanobot.memory.db)
      2. MEMORY.md file-based store             (MemoryStore)
    """
    
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)
    
    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """
        Build the system prompt from bootstrap files, memory, and skills.

        Memory is assembled in order of priority:
        1. Structured facts from DB  — primary, authoritative source.
        2. MEMORY.md / daily notes   — auxiliary, free-form notes.
        
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
        
        # --- Primary memory: structured facts from DB ---
        db_memory = self._load_db_facts_context()
        if db_memory:
            parts.append(db_memory)
        
        # --- Auxiliary memory: MEMORY.md / daily notes ---
        file_memory = self.memory.get_memory_context()
        if file_memory:
            parts.append(
                "# Auxiliary Memory (MEMORY.md)\n\n"
                "The following are free-form notes from MEMORY.md. "
                "For structured facts use `memory_search` / `add_fact` tools.\n\n"
                + file_memory
            )
        
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
        
        return "\n\n---\n\n".join(parts)

    # ------------------------------------------------------------------
    # DB facts loader
    # ------------------------------------------------------------------

    def _load_db_facts_context(self, limit: int = 20) -> str:
        """
        Load the most recently updated structured facts from the database
        and format them as a context block for the system prompt.
        """
        try:
            facts = get_facts_filtered(limit=limit)
        except Exception as exc:
            logger.debug("Failed to load facts from DB for system prompt: %s", exc)
            facts = []

        if not facts:
            return ""

        lines: list[str] = []
        for f in facts:
            domain = f.get("domain") or "general"
            category = f.get("category", "—")
            sub = f.get("sub_category") or ""
            key = f.get("key", "—")
            value = f.get("value", "—")
            if sub and str(sub).strip():
                lines.append(f"- [{domain}] {category} > {sub} > {key}: {value}")
            else:
                lines.append(f"- [{domain}] {category} > {key}: {value}")

        header = (
            "# Long-term Memory (structured facts)\n\n"
            "These facts are your **primary** persistent memory stored in the database "
            "(SQLite + ChromaDB). Use `memory_search` to find more facts and `add_fact` "
            "to save new ones.\n"
        )
        return header + "\n".join(lines)
    
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
- Search and manage your long-term memory (`memory_search` and `add_fact` tools)

## Your Memory

You have **long-term memory** that persists across sessions:

1. **Operational (session)**: The current conversation — you remember everything discussed in this chat.
2. **Long-term (persistent)** — **primary source**:
   - **Structured facts in DB** — the authoritative store of knowledge (domain, category, sub_category, key, value).
   - **memory_search** — semantic search over facts; use it to recall user preferences, project details, past decisions.
   - **add_fact** — save a new structured fact to the database. **Prefer this** over writing to MEMORY.md.
3. **Auxiliary (file-based)**:
   - **MEMORY.md** — free-form notes, used as a secondary source. You may still read it, but prefer `add_fact` for new information.
   - **Daily notes** — YYYY-MM-DD.md files for dated context.

Relevant facts from the DB are **automatically** included in your context. Use `memory_search` when you need to look up something specific. Use `add_fact` to remember new information.

## Current Time
{now}

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Structured memory DB: ~/.nanobot/memory.db (SQLite) + ~/.nanobot/chroma/ (vectors)
- Auxiliary notes: {workspace_path}/memory/MEMORY.md
- Daily notes: {workspace_path}/memory/YYYY-MM-DD.md
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

IMPORTANT: When responding to direct questions or conversations, reply directly with your text response.
Only use the 'message' tool when you need to send a message to a specific chat channel (like WhatsApp).
For normal conversation, just respond with text - do not call the message tool.

Always be helpful, accurate, and concise. When using tools, explain what you're doing.
When remembering important information, use the `add_fact` tool to save it to your structured memory."""
    
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
        system_prompt = self.build_system_prompt(skill_names)
        if channel and chat_id:
            system_prompt += f"\n\n## Current Session\nChannel: {channel}\nChat ID: {chat_id}"
        messages.append({"role": "system", "content": system_prompt})

        # Auto-enrich context with semantically relevant facts from the DB.
        if current_message and len(current_message) > 10:
            try:
                relevant_facts = semantic_search(current_message, limit=8)
                if relevant_facts:
                    facts_lines: list[str] = []
                    for f in relevant_facts:
                        dist = f.get("distance", 1.0)
                        if dist is not None and dist >= 0.75:
                            continue
                        domain = f.get("domain") or "general"
                        cat = f.get("category") or "?"
                        sub = f.get("sub_category") or ""
                        key = f.get("key") or "?"
                        val = f.get("value") or "?"
                        if sub and str(sub).strip():
                            facts_lines.append(f"- [{domain}] {cat} > {sub} > {key}: {val}")
                        else:
                            facts_lines.append(f"- [{domain}] {cat} > {key}: {val}")
                    if facts_lines:
                        messages.append({
                            "role": "system",
                            "content": (
                                "Relevant facts from your structured memory (auto-retrieved):\n"
                                + "\n".join(facts_lines)
                            ),
                        })
            except Exception as exc:
                logger.debug("Semantic enrichment failed: %s", exc)

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
