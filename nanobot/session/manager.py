"""Session management for conversation history."""

import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.utils.helpers import ensure_dir, safe_filename

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider


@dataclass
class Session:
    """
    A conversation session.
    
    Stores messages in JSONL format for easy reading and persistence.
    """
    
    key: str  # channel:chat_id
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    pending_confirmation: dict[str, Any] | None = None
    
    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Add a message to the session."""
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.messages.append(msg)
        self.updated_at = datetime.now()
    
    def get_history(self, max_messages: int = 50) -> list[dict[str, Any]]:
        """
        Get message history for LLM context.
        
        Args:
            max_messages: Maximum messages to return.
        
        Returns:
            List of messages in LLM format.
        """
        # Get recent messages
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        
        # Convert to LLM format (just role and content)
        return [{"role": m["role"], "content": m["content"]} for m in recent]
    
    def clear(self) -> None:
        """Clear all messages in the session."""
        self.messages = []
        self.updated_at = datetime.now()


class SessionManager:
    """
    Manages conversation sessions.
    
    Sessions are stored as JSONL files in the sessions directory.
    """
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.sessions_dir = ensure_dir(Path.home() / ".nanobot" / "sessions")
        self._cache: dict[str, Session] = {}
    
    def _get_session_path(self, key: str) -> Path:
        """Get the file path for a session."""
        safe_key = safe_filename(key.replace(":", "_"))
        return self.sessions_dir / f"{safe_key}.jsonl"
    
    def get_or_create(self, key: str) -> Session:
        """
        Get an existing session or create a new one.
        
        Args:
            key: Session key (usually channel:chat_id).
        
        Returns:
            The session.
        """
        # Check cache
        if key in self._cache:
            return self._cache[key]
        
        # Try to load from disk
        session = self._load(key)
        if session is None:
            session = Session(key=key)
        
        self._cache[key] = session
        return session
    
    def _load(self, key: str) -> Session | None:
        """Load a session from disk."""
        path = self._get_session_path(key)
        
        if not path.exists():
            return None
        
        try:
            messages = []
            metadata = {}
            created_at = None
            pending_confirmation = None

            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    data = json.loads(line)
                    
                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
                        pending_confirmation = data.get("pending_confirmation")
                    else:
                        messages.append(data)
            
            return Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                metadata=metadata,
                pending_confirmation=pending_confirmation,
            )
        except Exception as e:
            logger.warning(f"Failed to load session {key}: {e}")
            return None
    
    def save(self, session: Session) -> None:
        """Save a session to disk."""
        path = self._get_session_path(session.key)
        
        with open(path, "w") as f:
            # Write metadata first
            metadata_line = {
                "_type": "metadata",
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "metadata": session.metadata,
                "pending_confirmation": session.pending_confirmation,
            }
            f.write(json.dumps(metadata_line) + "\n")
            
            # Write messages
            for msg in session.messages:
                f.write(json.dumps(msg) + "\n")
        
        self._cache[session.key] = session
    
    def delete(self, key: str) -> bool:
        """
        Delete a session.
        
        Args:
            key: Session key.
        
        Returns:
            True if deleted, False if not found.
        """
        # Remove from cache
        self._cache.pop(key, None)
        
        # Remove file
        path = self._get_session_path(key)
        if path.exists():
            path.unlink()
            return True
        return False
    
    def list_sessions(self) -> list[dict[str, Any]]:
        """
        List all sessions.
        
        Returns:
            List of session info dicts.
        """
        sessions = []
        
        for path in self.sessions_dir.glob("*.jsonl"):
            try:
                # Read just the metadata line
                with open(path) as f:
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            sessions.append({
                                "key": path.stem.replace("_", ":"),
                                "created_at": data.get("created_at"),
                                "updated_at": data.get("updated_at"),
                                "path": str(path)
                            })
            except Exception:
                continue
        
        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)

    # -------------------------------------------------------------------------
    # LLM summarization
    # -------------------------------------------------------------------------

    _SUMMARIZATION_PROMPT = """Сожми следующий диалог в краткое изложение ключевых моментов.
Ответь на том же языке, что и диалог. Сохрани важные факты, решения и контекст.
Формат: несколько абзацев, без лишних деталей.

Диалог:
---
{messages}
---"""

    async def maybe_summarize(
        self,
        session: "Session",
        provider: "LLMProvider",
        *,
        threshold: int = 50,
        summarization_model: str = "gpt-4o-mini",
        keep_recent: int = 20,
    ) -> None:
        """
        Summarize old messages when session exceeds threshold.

        Replaces older messages with a single system summary message.
        Uses a cheap model via LiteLLMProvider. Logs the process and token savings.

        Args:
            session: Session to possibly summarize.
            provider: LLM provider (LiteLLMProvider) for summarization.
            threshold: Min messages to trigger summarization (default 50).
            summarization_model: Cheap model for summarization (default gpt-4o-mini).
            keep_recent: Number of recent messages to keep (default 20).
        """
        n = len(session.messages)
        if n < threshold:
            return

        to_summarize_count = n - keep_recent
        if to_summarize_count < 10:
            return

        to_summarize = session.messages[:-keep_recent]
        messages_text = "\n".join(
            f"{m.get('role', '?')}: {m.get('content', '')}" for m in to_summarize
        )

        summary = await self._summarize_messages(
            provider, messages_text, summarization_model
        )
        if not summary or summary.strip() == "":
            logger.warning(f"Session {session.key}: summarization returned empty result")
            return

        est_tokens_before = sum(len(str(m.get("content", ""))) for m in to_summarize) // 4
        est_tokens_after = len(summary) // 4
        saved = max(0, est_tokens_before - est_tokens_after)

        summary_msg = {
            "role": "system",
            "content": f"[Контекст предыдущего диалога]:\n{summary.strip()}",
            "timestamp": datetime.now().isoformat(),
        }

        session.messages = [summary_msg] + session.messages[-keep_recent:]
        session.updated_at = datetime.now()

        logger.info(
            f"Session {session.key}: compressed {to_summarize_count} messages into 1 "
            f"(est. {est_tokens_before}→{est_tokens_after} tokens, saved ~{saved})"
        )

    async def _summarize_messages(
        self,
        provider: "LLMProvider",
        messages_text: str,
        model: str,
    ) -> str:
        """
        Compress messages into a brief summary using LLM.

        Args:
            provider: LLM provider.
            messages_text: Concatenated dialog text.
            model: Model identifier for summarization.

        Returns:
            Summary text in the same language as the dialog.
        """
        prompt = self._SUMMARIZATION_PROMPT.format(messages=messages_text)
        msgs = [{"role": "user", "content": prompt}]

        try:
            response = await provider.chat(
                msgs,
                model=model,
                max_tokens=1024,
                temperature=0.3,
            )
            if response.finish_reason == "error" and response.content:
                logger.warning(f"Summarization error: {response.content[:200]}")
                return ""
            return response.content or ""
        except Exception as e:
            logger.warning(f"Summarization failed: {e}")
            return ""
