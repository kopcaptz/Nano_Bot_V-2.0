"""Fake data for dashboard placeholders."""

import random
from datetime import datetime, timedelta
from typing import Any


def fake_sessions(count: int = 5) -> list[dict[str, Any]]:
    """Generate fake session entries."""
    channels = ["telegram", "discord", "gateway"]
    return [
        {
            "key": f"{channels[i % 3]}:{1000 + i}",
            "created_at": (datetime.now() - timedelta(hours=i * 2)).isoformat(),
            "updated_at": (datetime.now() - timedelta(minutes=i * 15)).isoformat(),
            "path": f"~/.nanobot/sessions/{channels[i % 3]}_{1000 + i}.jsonl",
        }
        for i in range(count)
    ]


def fake_token_usage(days: int = 7) -> dict[str, Any]:
    """Generate fake token usage for today."""
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "prompt_tokens": random.randint(500, 5000),
        "completion_tokens": random.randint(200, 3000),
        "total_tokens": random.randint(1000, 8000),
        "requests": random.randint(5, 50),
        "by_model": [
            {"model": "anthropic/claude-opus-4-5", "prompt_tokens": 1200, "completion_tokens": 800, "total_tokens": 2000, "requests": 3},
            {"model": "openai/gpt-4o", "prompt_tokens": 800, "completion_tokens": 400, "total_tokens": 1200, "requests": 2},
        ],
    }


def fake_token_usage_period(days: int = 7) -> list[dict[str, Any]]:
    """Generate fake token usage per day."""
    return [
        {
            "date": (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"),
            "prompt_tokens": random.randint(500, 3000),
            "completion_tokens": random.randint(200, 2000),
            "total_tokens": random.randint(1000, 5000),
            "requests": random.randint(2, 20),
        }
        for i in range(days - 1, -1, -1)
    ]


def fake_facts(count: int = 5) -> list[dict[str, Any]]:
    """Generate fake fact entries."""
    categories = ["user", "preference", "system"]
    return [
        {
            "id": i + 1,
            "category": categories[i % 3],
            "key": f"fact_key_{i}",
            "value": f"Sample value for fact {i + 1}",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        for i in range(count)
    ]


def fake_reflections(count: int = 3) -> list[dict[str, Any]]:
    """Generate fake reflection entries."""
    tools = ["exec", "web_search", "read_file"]
    return [
        {
            "id": i + 1,
            "tool_name": tools[i % 3],
            "tool_args": "{}",
            "error_text": f"Sample error {i + 1}",
            "insight": f"Retry with different parameters for tool {tools[i % 3]}",
            "session_key": "gateway:local",
            "created_at": datetime.now().isoformat(),
        }
        for i in range(count)
    ]


def fake_journal_entries(count: int = 2) -> list[dict[str, Any]]:
    """Generate fake journal entries."""
    return [
        {
            "id": i + 1,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "content": f"Sample journal entry {i + 1}",
            "created_at": datetime.now().isoformat(),
        }
        for i in range(count)
    ]
