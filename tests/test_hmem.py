"""Unit tests for hierarchical memory (H-MEM) - Step 2."""

from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.agent.tools.memory import MemorySearchTool
from nanobot.memory.crystallize import crystallize_memories
from nanobot.memory.db import add_fact, get_facts_filtered, init_db
from nanobot.providers.base import LLMResponse


# ---------- Schema: domain and sub_category columns ----------


def test_facts_table_has_domain_and_sub_category_columns(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Facts table has domain and sub_category columns (from init_db)."""
    db_file = tmp_path / "test_hmem.db"
    monkeypatch.setattr("nanobot.memory.db.DB_PATH", db_file)
    init_db()

    conn = sqlite3.connect(db_file)
    cursor = conn.execute("PRAGMA table_info(facts)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()

    assert "domain" in columns
    assert "sub_category" in columns


# ---------- add_fact with domain and sub_category ----------


def test_add_fact_with_domain(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """add_fact saves domain and sub_category; get_fact retrieves them."""
    db_file = tmp_path / "test_hmem.db"
    monkeypatch.setattr("nanobot.memory.db.DB_PATH", db_file)
    init_db()

    # Mock vector memory to avoid ChromaDB dependency
    with patch("nanobot.memory.db.add_vector_memory"):
        add_fact(
            category="Arch",
            key="DB",
            value="SQLite",
            domain="Project: NanoBot",
            sub_category="Storage",
        )

    # get_fact returns category, key, value - check via get_facts_filtered for full row
    facts = get_facts_filtered(domain="Project: NanoBot", category="Arch", limit=10)
    assert len(facts) == 1
    assert facts[0]["category"] == "Arch"
    assert facts[0]["key"] == "DB"
    assert facts[0]["value"] == "SQLite"
    assert facts[0].get("domain") == "Project: NanoBot"
    assert facts[0].get("sub_category") == "Storage"


# ---------- get_facts_filtered ----------


def test_get_facts_filtered(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_facts_filtered returns only facts matching domain and/or category."""
    db_file = tmp_path / "test_hmem.db"
    monkeypatch.setattr("nanobot.memory.db.DB_PATH", db_file)
    init_db()

    with patch("nanobot.memory.db.add_vector_memory"):
        add_fact("Arch", "DB", "SQLite", domain="Project: X", sub_category="Storage")
        add_fact("Arch", "Cache", "Redis", domain="Project: X", sub_category="Storage")
        add_fact("Hobbies", "Music", "Jazz", domain="Personal")
        add_fact("Comm", "Lang", "RU", domain="Project: X")
        add_fact("Other", "Key", "Val", domain="Project: Y")

    domain_x = get_facts_filtered(domain="Project: X", limit=10)
    assert len(domain_x) == 3
    assert all(f.get("domain") == "Project: X" for f in domain_x)

    domain_cat = get_facts_filtered(domain="Project: X", category="Arch", limit=10)
    assert len(domain_cat) == 2
    assert all(f.get("category") == "Arch" for f in domain_cat)


# ---------- MemorySearchTool ----------


@pytest.mark.asyncio
async def test_memory_search_tool_semantic() -> None:
    """MemorySearchTool with semantic search returns formatted results."""
    mock_facts = [
        {
            "domain": "User Preferences",
            "category": "Technology",
            "sub_category": "Programming",
            "key": "Preferred Language",
            "value": "Python",
        },
        {
            "domain": "User Preferences",
            "category": "Technology",
            "sub_category": None,
            "key": "Preferred IDE",
            "value": "Cursor",
        },
    ]

    with patch("nanobot.memory.db.semantic_search", return_value=mock_facts):
        tool = MemorySearchTool()
        result = await tool.execute(query="programming preferences", limit=5)

    assert "Found 2 facts" in result
    assert "[Domain: User Preferences]" in result
    assert "Technology > Programming > Preferred Language: Python" in result
    assert "Technology > Preferred IDE: Cursor" in result


@pytest.mark.asyncio
async def test_memory_search_tool_requires_query() -> None:
    """MemorySearchTool.execute requires query parameter."""
    tool = MemorySearchTool()

    with pytest.raises(TypeError):
        await tool.execute()  # type: ignore[call-arg]


# ---------- Crystallize with hierarchy ----------


@pytest.mark.asyncio
async def test_crystallize_with_hierarchy(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """crystallize_memories saves facts with domain and sub_category from LLM response."""
    db_file = tmp_path / "test_hmem.db"
    monkeypatch.setattr("nanobot.memory.db.DB_PATH", db_file)

    init_db()

    # Provide session messages directly (conversations table removed)
    session_messages = [
        {"role": "user", "content": "I prefer Python and use Cursor IDE", "timestamp": "2025-01-01T00:00:00"},
        {"role": "assistant", "content": "Got it", "timestamp": "2025-01-01T00:00:01"},
    ]

    mock_response = LLMResponse(
        content='[{"domain":"User Preferences","category":"Technology","sub_category":"Programming","key":"Language","value":"Python"},{"domain":"User Preferences","category":"Technology","sub_category":null,"key":"IDE","value":"Cursor"}]'
    )
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(return_value=mock_response)

    with patch("nanobot.memory.db.add_vector_memory"):
        result = await crystallize_memories(
            mock_provider, messages_limit=10, session_messages=session_messages,
        )

    assert result["saved_facts"] >= 1
    assert result["extracted_facts"] >= 1

    facts = get_facts_filtered(domain="User Preferences", limit=10)
    assert any(f.get("key") == "Language" and f.get("value") == "Python" for f in facts)
    assert any(f.get("sub_category") == "Programming" for f in facts)
