"""Memory wrapper for dashboard."""

from datetime import datetime
from typing import Any

try:
    from nanobot.memory.db import (
        get_token_usage_today as _get_token_usage_today,
        get_token_usage_period,
        get_facts_filtered,
        get_facts_by_category,
        search_facts,
        get_recent_reflections,
        get_journal as _get_journal,
        init_db,
    )
    _HAS_NANOBOT = True
except ImportError:
    _HAS_NANOBOT = False


def get_token_usage_today() -> dict[str, Any] | None:
    """Get token usage for today."""
    if not _HAS_NANOBOT:
        return None
    try:
        init_db()
        return _get_token_usage_today()
    except Exception:
        return None


def get_token_usage_period_days(days: int = 7) -> list[dict[str, Any]]:
    """Get token usage for last N days."""
    if not _HAS_NANOBOT:
        return []
    try:
        init_db()
        return get_token_usage_period(days=days)
    except Exception:
        return []


def get_facts(
    domain: str | None = None,
    category: str | None = None,
    limit: int = 50,
    search_query: str | None = None,
) -> list[dict[str, Any]]:
    """Get facts from memory. Optional search by query."""
    if not _HAS_NANOBOT:
        return []
    try:
        init_db()
        if search_query:
            return search_facts(search_query)
        return get_facts_filtered(domain=domain, category=category, limit=limit)
    except Exception:
        return []


def get_facts_categories() -> list[str]:
    """Get distinct fact categories."""
    if not _HAS_NANOBOT:
        return []
    try:
        init_db()
        facts = get_facts_filtered(limit=500)
        cats = sorted({f.get("category") for f in facts if f.get("category")})
        return cats
    except Exception:
        return []


def get_reflections(limit: int = 20, tool_name: str | None = None) -> list[dict[str, Any]]:
    """Get recent reflections."""
    if not _HAS_NANOBOT:
        return []
    try:
        init_db()
        return get_recent_reflections(tool_name=tool_name, limit=limit)
    except Exception:
        return []


def get_journal(date: str | None = None) -> list[dict[str, Any]]:
    """Get journal entries for date. Defaults to today."""
    if not _HAS_NANOBOT:
        return []
    try:
        init_db()
        d = date or datetime.now().strftime("%Y-%m-%d")
        return _get_journal(d)
    except Exception:
        return []
