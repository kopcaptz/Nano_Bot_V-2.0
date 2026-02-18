"""Tests for token usage forensic tracking and CLI reporting."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from nanobot.cli.commands import app
from nanobot.memory.db import (
    add_token_usage_call,
    get_token_usage_session_details,
    get_token_usage_sessions,
    get_token_usage_today,
    init_db,
)
from nanobot.providers.litellm_provider import LiteLLMProvider


def test_token_usage_calls_table_created(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """init_db creates token_usage_calls with forensic columns."""
    db_file = tmp_path / "test_forensics.db"
    monkeypatch.setattr("nanobot.memory.db.DB_PATH", db_file)
    init_db()

    conn = sqlite3.connect(db_file)
    rows = conn.execute("PRAGMA table_info(token_usage_calls)").fetchall()
    conn.close()
    columns = {row[1] for row in rows}

    assert {"session_id", "request_id", "timestamp", "model", "total_tokens", "cost_usd"}.issubset(
        columns
    )


def test_get_token_usage_sessions_and_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session aggregation and per-call details are computed correctly."""
    db_file = tmp_path / "test_forensics.db"
    monkeypatch.setattr("nanobot.memory.db.DB_PATH", db_file)
    init_db()

    # Session A (higher cost)
    add_token_usage_call(
        session_id="sess-A",
        request_id="req-A1",
        conversation_key="telegram:1",
        model="openai/gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        cost_usd=0.25,
        iteration=1,
    )
    add_token_usage_call(
        session_id="sess-A",
        request_id="req-A2",
        conversation_key="telegram:1",
        model="openai/gpt-4o-mini",
        prompt_tokens=80,
        completion_tokens=20,
        total_tokens=100,
        cost_usd=0.15,
        iteration=2,
    )

    # Session B (lower cost)
    add_token_usage_call(
        session_id="sess-B",
        request_id="req-B1",
        conversation_key="telegram:2",
        model="anthropic/claude-opus-4-5",
        prompt_tokens=50,
        completion_tokens=50,
        total_tokens=100,
        cost_usd=0.05,
        iteration=1,
    )

    sessions = get_token_usage_sessions(days=7, top=10)
    assert len(sessions) == 2
    assert sessions[0]["session_id"] == "sess-A"
    assert sessions[0]["llm_calls"] == 2
    assert sessions[0]["total_tokens"] == 250
    assert float(sessions[0]["cost_usd"]) == pytest.approx(0.40)

    details = get_token_usage_session_details("sess-A")
    assert details is not None
    assert details["session_id"] == "sess-A"
    assert details["conversation_key"] == "telegram:1"
    assert details["llm_calls"] == 2
    assert details["total_tokens"] == 250
    assert float(details["cost_usd"]) == pytest.approx(0.40)
    assert len(details["calls"]) == 2
    assert details["calls"][0]["request_id"] == "req-A1"
    assert details["calls"][1]["request_id"] == "req-A2"

    assert get_token_usage_session_details("missing") is None


@pytest.mark.asyncio
async def test_provider_persists_forensic_and_aggregate_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LiteLLM provider writes both legacy aggregate and forensic rows."""
    db_file = tmp_path / "test_forensics.db"
    monkeypatch.setattr("nanobot.memory.db.DB_PATH", db_file)
    init_db()

    # Prevent provider auto-prefixing and use deterministic model key.
    monkeypatch.setattr(
        "nanobot.providers.litellm_provider.find_by_model",
        lambda model: None,
    )

    async def fake_acompletion(**kwargs):
        message = SimpleNamespace(content="ok", tool_calls=None, reasoning_content=None)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18)
        return SimpleNamespace(choices=[choice], usage=usage)

    monkeypatch.setattr("nanobot.providers.litellm_provider.acompletion", fake_acompletion)
    monkeypatch.setattr(
        "nanobot.providers.litellm_provider.litellm.completion_cost",
        lambda completion_response: 0.0123,
    )

    provider = LiteLLMProvider(api_key="test-key", default_model="test-model")
    result = await provider.chat(
        messages=[{"role": "user", "content": "hello"}],
        model="test-model",
        usage_session_id="usage-session-1",
        usage_request_id="usage-request-1",
        usage_iteration=3,
        usage_conversation_key="telegram:777",
    )

    assert result.content == "ok"
    assert result.usage["total_tokens"] == 18

    daily = get_token_usage_today()
    assert daily["total_tokens"] == 18
    assert daily["requests"] == 1

    details = get_token_usage_session_details("usage-session-1")
    assert details is not None
    assert details["llm_calls"] == 1
    assert details["calls"][0]["request_id"] == "usage-request-1"
    assert details["calls"][0]["iteration"] == 3
    assert details["calls"][0]["conversation_key"] == "telegram:777"
    assert float(details["cost_usd"]) == pytest.approx(0.0123)


def test_usage_sessions_cli_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI usage sessions prints aggregated rows."""
    monkeypatch.setattr(
        "nanobot.memory.get_token_usage_sessions",
        lambda days, top: [
            {
                "session_id": "sess-cli-1",
                "conversation_key": "telegram:100",
                "llm_calls": 4,
                "total_tokens": 1234,
                "cost_usd": 0.456,
                "first_timestamp": "2026-02-18T12:00:00",
                "last_timestamp": "2026-02-18T12:01:00",
            }
        ],
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["usage", "sessions", "-d", "7", "--top", "20"],
        env={"COLUMNS": "220"},
    )

    assert result.exit_code == 0
    assert "Token Usage Sessions" in result.output
    assert "sess-cli" in result.output
    assert "telegram" in result.output
    assert "1,234" in result.output


def test_usage_session_cli_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI usage session prints summary and per-call table."""
    monkeypatch.setattr(
        "nanobot.memory.get_token_usage_session_details",
        lambda session_id: {
            "session_id": session_id,
            "conversation_key": "discord:200",
            "llm_calls": 2,
            "total_tokens": 321,
            "cost_usd": 0.111,
            "first_timestamp": "2026-02-18T13:00:00",
            "last_timestamp": "2026-02-18T13:00:05",
            "by_model": [
                {
                    "model": "test-model",
                    "llm_calls": 2,
                    "total_tokens": 321,
                    "cost_usd": 0.111,
                }
            ],
            "calls": [
                {
                    "timestamp": "2026-02-18T13:00:01",
                    "request_id": "req-1",
                    "iteration": 1,
                    "model": "test-model",
                    "total_tokens": 111,
                    "cost_usd": 0.05,
                },
                {
                    "timestamp": "2026-02-18T13:00:03",
                    "request_id": "req-2",
                    "iteration": 2,
                    "model": "test-model",
                    "total_tokens": 210,
                    "cost_usd": 0.061,
                },
            ],
        },
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["usage", "session", "sess-cli-2"],
        env={"COLUMNS": "220"},
    )

    assert result.exit_code == 0
    assert "sess-cli-2" in result.output
    assert "req-1" in result.output
    assert "req-2" in result.output

