"""Create skill tool: allows agent to save successful task sequences as reusable skills."""

from typing import Any

from nanobot.agent.skill_generator import SkillGenerator
from nanobot.agent.tools.base import Tool
from nanobot.session.manager import SessionManager


class CreateSkillTool(Tool):
    """Tool for creating new skills from conversation history."""

    def __init__(
        self,
        skill_generator: SkillGenerator,
        session_manager: SessionManager,
    ) -> None:
        """
        Initialize CreateSkillTool.

        Args:
            skill_generator: SkillGenerator instance for creating skills
            session_manager: SessionManager instance for accessing conversation history
        """
        self._skill_generator = skill_generator
        self._session_manager = session_manager
        self._current_session_key: str | None = None
        self._current_messages: list[dict[str, Any]] | None = None

    def set_session_key(self, key: str) -> None:
        """Set the current session key for accessing conversation history."""
        self._current_session_key = key

    def set_messages(self, messages: list[dict[str, Any]]) -> None:
        """Set the current message list (with tool_calls) for skill extraction."""
        self._current_messages = messages

    @property
    def name(self) -> str:
        return "create_skill"

    @property
    def description(self) -> str:
        return (
            "Create a new reusable skill from the current conversation. "
            "Use this when you have successfully completed a complex task "
            "and want to remember the approach for future use. "
            "The skill will be saved as a SKILL.md file."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "A descriptive snake_case name (e.g., 'analyze_project_structure').",
                },
                "skill_description": {
                    "type": "string",
                    "description": "A one-sentence description of what the skill does.",
                },
            },
            "required": ["skill_name", "skill_description"],
        }

    async def execute(
        self,
        skill_name: str,
        skill_description: str,
        **kwargs: Any,
    ) -> str:
        """
        Create a new skill from the current conversation history.

        Args:
            skill_name: Name of the skill (snake_case)
            skill_description: Short description of the skill
            **kwargs: Additional arguments (ignored)

        Returns:
            Success message with file path or error message
        """
        if not self._current_session_key:
            return "Error: No active session. Cannot access conversation history."

        # Prefer injected messages (full structure with tool_calls) over session history
        if self._current_messages:
            messages = self._current_messages
        else:
            session = self._session_manager.get_or_create(self._current_session_key)
            if not session.messages:
                return "Error: No messages in current session."
            messages = session.get_history(max_messages=100)

        return await self._skill_generator.create_skill_from_trajectory(
            skill_name=skill_name,
            skill_description=skill_description,
            messages=messages,
        )
