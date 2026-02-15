"""Skill generator: creates reusable skills from successful tool call trajectories."""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.providers.base import LLMProvider


SKILL_GENERATION_PROMPT = """Analyze the following successful tool call sequence from an AI agent session. Your task is to convert this into a generalized, reusable skill instruction.

**Tool Sequence:**
{tool_sequence}

**Instructions:**
1. Describe the overall GOAL of this sequence in one sentence.
2. Write a STEP-BY-STEP guide using the available tools (read_file, write_file, edit_file, list_dir, exec, web_search, web_fetch, memory_search).
3. GENERALIZE specific parameters: replace specific filenames with descriptions like "the target file", specific URLs with "the target URL", etc.
4. Include PREREQUISITES: what needs to be true before this skill can be used.
5. Include COMMON PITFALLS: based on any errors that occurred during the sequence.
6. Output clean, well-structured Markdown.

Example output:
## Goal
Find and analyze large files in a project directory.

## Prerequisites
- A project directory path must be known.

## Steps
1. Use `list_dir` to scan the project directory.
2. Use `exec` with `find . -size +10M` to locate large files.
3. For each large file, use `read_file` to check its content type.
4. Use `write_file` to create a summary report.

## Common Pitfalls
- The `find` command syntax differs between Windows and Linux. Use `dir` on Windows.
"""


SKILL_TEMPLATE = '''---
description: "{description}"
---

# {name}

{body}
'''


class SkillGenerator:
    """Generates reusable skills (SKILL.md) from successful tool call trajectories."""

    def __init__(
        self,
        skills_dir: Path,
        provider: LLMProvider,
        model: str,
    ) -> None:
        """
        Initialize SkillGenerator.

        Args:
            skills_dir: Directory where skills are stored (e.g., Path("workspace/skills"))
            provider: LLM provider for generating skill content
            model: Model name to use for generation
        """
        self.skills_dir = Path(skills_dir)
        self.provider = provider
        self.model = model

    def _extract_tool_sequence(self, messages: list[dict[str, Any]]) -> str:
        """
        Extract tool call sequence from message history.

        Args:
            messages: List of messages in OpenAI format

        Returns:
            Formatted string with tool calls and results
        """
        sequence_parts: list[str] = []

        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    name = func.get("name", "unknown")
                    args = func.get("arguments", "{}")

                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            pass

                    sequence_parts.append(
                        f"Tool: {name}\nArguments: {json.dumps(args, indent=2, ensure_ascii=False)}"
                    )

            elif msg.get("role") == "tool":
                content = msg.get("content", "")

                if len(content) > 200:
                    content = content[:200] + "..."

                is_error = content.startswith("Error:")
                status = "ERROR" if is_error else "OK"

                sequence_parts.append(f"Result ({status}): {content}")

        return "\n\n".join(sequence_parts) if sequence_parts else "No tool calls found."

    async def create_skill_from_trajectory(
        self,
        skill_name: str,
        skill_description: str,
        messages: list[dict[str, Any]],
    ) -> str:
        """
        Generate a new skill from conversation history.

        Args:
            skill_name: Name of the skill (used as directory name)
            skill_description: Short description of the skill
            messages: Conversation history in OpenAI format

        Returns:
            Success message with file path or error message
        """
        tool_sequence = self._extract_tool_sequence(messages)

        if tool_sequence == "No tool calls found.":
            return "Error: No tool calls found in the conversation history."

        prompt = SKILL_GENERATION_PROMPT.format(tool_sequence=tool_sequence)

        try:
            response = await self.provider.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a technical writer. Generate clear, reusable skill documentation.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.3,
                max_tokens=2000,
            )
            body = response.content or "No content generated."
        except Exception as e:
            logger.error(f"Skill generation LLM call failed: {e}")
            return f"Error: Failed to generate skill content: {e}"

        skill_content = SKILL_TEMPLATE.format(
            name=skill_name,
            description=skill_description,
            body=body,
        )

        skill_dir = self.skills_dir / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(skill_content, encoding="utf-8")

        logger.info(f"Skill '{skill_name}' created at {skill_file}")
        return f"Skill '{skill_name}' created successfully at {skill_file}"
