"""Regression tests for context token-cost emergency mitigation."""

from __future__ import annotations

import sys
import types
from pathlib import Path
import re


def _load_context_builder(memory_text: str):
    """Load ContextBuilder with lightweight dependency stubs."""

    class _Logger:
        def info(self, *args, **kwargs):
            return None

        def warning(self, *args, **kwargs):
            return None

    class _MemoryStore:
        def __init__(self, workspace):
            self.workspace = workspace

        def get_memory_context(self) -> str:
            return memory_text

    def _semantic_search(query: str, limit: int = 5):
        return []

    sys.modules["loguru"] = types.SimpleNamespace(logger=_Logger())
    sys.modules["nanobot.agent.memory"] = types.SimpleNamespace(MemoryStore=_MemoryStore)
    sys.modules["nanobot.memory.db"] = types.SimpleNamespace(semantic_search=_semantic_search)

    module = types.ModuleType("context_under_test")
    code = Path("/workspace/nanobot/agent/context.py").read_text(encoding="utf-8")
    exec(code, module.__dict__)
    return module.ContextBuilder


class _FakeSkillManager:
    def __init__(self):
        self._skills = {
            "skill-creator": {
                "name": "skill-creator",
                "description": "Huge skill for creating reusable skills",
                "content": "HUGE_SKILL_CREATOR_CONTENT_" + ("x" * 18000),
            },
            "tmux": {
                "name": "tmux",
                "description": "Terminal multiplexing workflows",
                "content": "TMUX_CONTENT_" + ("y" * 4000),
            },
            "vision": {
                "name": "vision",
                "description": "Screenshot and visual analysis",
                "content": "VISION_CONTENT_" + ("z" * 3900),
            },
            "weak": {
                "name": "weak",
                "description": "Low relevance skill",
                "content": "WEAK_CONTENT_" + ("q" * 1000),
            },
        }

    def list_always_load_skills(self):
        return []

    def search_skills(self, query, limit=3):
        return [
            {"skill_name": "skill-creator", "score": 0.93, "distance": 0.07},
            {"skill_name": "tmux", "score": 0.66, "distance": 0.34},
            {"skill_name": "weak", "score": 0.12, "distance": 0.88},
            {"skill_name": "vision", "score": 0.58, "distance": 0.42},
        ]

    def get_skill(self, name):
        return self._skills.get(name)

    def list_skills(self):
        return list(self._skills.values())


def _extract_relevant_block(prompt: str) -> str:
    match = re.search(
        r"# Relevant Skills\n\n([\s\S]*?)(\n\n# Available Skills|$)",
        prompt,
    )
    return match.group(1).strip() if match else ""


def test_semantic_results_are_summaries_not_full_skill_payloads():
    """System prompt must never auto-inject full semantic skill content."""
    context_builder = _load_context_builder(memory_text="")
    cb = context_builder(Path("/workspace/workspace"), skill_manager=_FakeSkillManager())

    prompt = cb.build_system_prompt("создай pull request и прогони тесты")

    assert "# Relevant Skills" in prompt
    assert "- skill-creator:" in prompt
    assert "- tmux:" in prompt
    assert "HUGE_SKILL_CREATOR_CONTENT_" not in prompt
    assert "TMUX_CONTENT_" not in prompt
    assert "VISION_CONTENT_" not in prompt


def test_relevance_threshold_filters_low_relevance_from_relevant_block():
    """Low-score semantic hits should not be listed as relevant."""
    context_builder = _load_context_builder(memory_text="")
    cb = context_builder(Path("/workspace/workspace"), skill_manager=_FakeSkillManager())

    prompt = cb.build_system_prompt("помоги с задачей")
    relevant_block = _extract_relevant_block(prompt)

    assert "- weak:" not in relevant_block
    assert "- skill-creator:" in relevant_block
    assert "- tmux:" in relevant_block


def test_memory_and_skill_sections_are_guarded_by_budgets():
    """Large memory/skills inputs should be trimmed to configured caps."""
    context_builder = _load_context_builder(memory_text="LONG_MEMORY_BLOCK\n" * 2000)
    cb = context_builder(Path("/workspace/workspace"), skill_manager=_FakeSkillManager())

    prompt = cb.build_system_prompt("помоги с задачей")

    assert "[...truncated to reduce token usage...]" in prompt

    skills_start = prompt.find("# Relevant Skills")
    if skills_start == -1:
        skills_start = prompt.find("# Available Skills")
    assert skills_start != -1

    # Prompt slice includes only the final skills block content.
    skills_block = prompt[skills_start:]
    assert len(skills_block) <= cb.MAX_SKILLS_SECTION_CHARS + 250
