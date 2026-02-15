"""Tests for hierarchical memory (domain, sub_category, migrations, tools)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock heavy deps before nanobot imports
sys.modules["loguru"] = MagicMock()
sys.modules["litellm"] = MagicMock()

from nanobot.memory import db
from nanobot.memory.migrate import run_migrations


# --- Test 1: migration adds columns ---


def test_migration_adds_columns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run migrations and verify domain, sub_category columns exist in facts."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db.init_db()
    run_migrations()

    with db._connect() as conn:
        cursor = conn.execute("PRAGMA table_info(facts)")
        columns = {row[1] for row in cursor.fetchall()}

    assert "domain" in columns
    assert "sub_category" in columns


# --- Test 2: add_fact with domain ---


def test_add_fact_with_domain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Add fact with domain/sub_category, verify via get_fact."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db.init_db()
    run_migrations()

    db.add_fact(
        category="Arch",
        key="DB",
        value="SQLite",
        domain="Project: NanoBot",
        sub_category="Storage",
    )

    f = db.get_fact("Arch", "DB")
    assert f is not None
    assert f["category"] == "Arch"
    assert f["key"] == "DB"
    assert f["value"] == "SQLite"
    assert f["domain"] == "Project: NanoBot"
    assert f["sub_category"] == "Storage"


# --- Test 3: get_facts_filtered ---


def test_get_facts_filtered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Add 5 facts, verify filtering by domain and category."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db.init_db()
    run_migrations()

    db.add_fact("Cat1", "k1", "v1", domain="X", sub_category="s1")
    db.add_fact("Cat2", "k2", "v2", domain="X", sub_category="s2")
    db.add_fact("Cat1", "k3", "v3", domain="Y", sub_category="s1")
    db.add_fact("Cat2", "k4", "v4", domain="Y")
    db.add_fact("Cat1", "k5", "v5", domain="X")

    by_domain_x = db.get_facts_filtered(domain="X")
    assert len(by_domain_x) == 3

    by_both = db.get_facts_filtered(domain="X", category="Cat1")
    assert len(by_both) == 2

    by_domain_y = db.get_facts_filtered(domain="Y")
    assert len(by_domain_y) == 2


# --- Test 4: MemorySearchTool semantic ---


@pytest.mark.asyncio
async def test_memory_search_tool_semantic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock semantic_search, call MemorySearchTool.execute, verify output format."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    from nanobot.agent.tools.memory import MemorySearchTool

    mock_facts = [
        {"domain": "Project", "category": "Arch", "key": "DB", "value": "SQLite", "distance": 0.3},
    ]
    with patch("nanobot.memory.db.semantic_search", return_value=mock_facts):
        tool = MemorySearchTool()
        result = await tool.execute(query="database")

    assert "Found 1 fact(s)" in result
    assert "Project" in result
    assert "Arch" in result
    assert "DB" in result
    assert "SQLite" in result
    assert "relevance" in result


# --- Test 5: MemorySearchTool no params ---


@pytest.mark.asyncio
async def test_memory_search_tool_no_params(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Call execute without params, expect error message."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)

    from nanobot.agent.tools.memory import MemorySearchTool

    tool = MemorySearchTool()
    result = await tool.execute()
    assert "Error:" in result
    assert "At least one parameter" in result


# --- Test 6: crystallize with hierarchy ---


@pytest.mark.asyncio
async def test_crystallize_with_hierarchy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock LLMProvider.chat to return JSON with domain/sub_category, verify facts saved."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db.init_db()
    run_migrations()

    db.add_message("test", "user", "I prefer Python")
    db.add_message("test", "assistant", "Noted")

    mock_content = '''[
        {"domain": "User Preferences", "category": "Language", "sub_category": null, "key": "Preferred", "value": "Python"},
        {"domain": "Project: Nano Bot", "category": "Tech", "sub_category": "Stack", "key": "Runtime", "value": "Python 3.12"}
    ]'''

    from nanobot.providers.base import LLMProvider, LLMResponse

    mock_provider = MagicMock(spec=LLMProvider)
    mock_provider.chat = AsyncMock(return_value=LLMResponse(content=mock_content))

    from nanobot.memory.crystallize import crystallize_memories

    result = await crystallize_memories(provider=mock_provider, messages_limit=10)

    assert result["saved_facts"] == 2

    facts_domain1 = db.get_facts_filtered(domain="User Preferences")
    assert len(facts_domain1) == 1
    assert facts_domain1[0]["category"] == "Language"
    assert facts_domain1[0]["key"] == "Preferred"
    assert facts_domain1[0]["value"] == "Python"

    facts_domain2 = db.get_facts_filtered(domain="Project: Nano Bot")
    assert len(facts_domain2) == 1
    assert facts_domain2[0]["sub_category"] == "Stack"
    assert facts_domain2[0]["key"] == "Runtime"
    assert facts_domain2[0]["value"] == "Python 3.12"
