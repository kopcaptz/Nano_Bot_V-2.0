"""Tests for Hybrid Navigator Agent (rules + SLM)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from nanobot.agents.navigator import NavigatorAgent, RouteDecision, RuleEngine
from nanobot.providers.base import LLMProvider, LLMResponse


class DummyProvider(LLMProvider):
    """Minimal async provider for navigator tests."""

    def __init__(self, response: LLMResponse) -> None:
        super().__init__(api_key=None, api_base=None)
        self.response = response

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        _ = (messages, tools, model, max_tokens, temperature)
        return self.response

    def get_default_model(self) -> str:
        return "dummy/model"


def _history_with_timestamp(seconds_ago: int, content: str = "prev") -> list[dict[str, Any]]:
    ts = (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()
    return [{"role": "user", "content": content, "timestamp": ts}]


def test_rule_engine_low_complexity_routes_template() -> None:
    engine = RuleEngine()
    decision = engine.preprocess("Привет", session_history=[], config={})
    assert decision.route == RouteDecision.TEMPLATE
    assert decision.complexity < 0.30


def test_rule_engine_cooldown_routes_no_action() -> None:
    engine = RuleEngine()
    history = _history_with_timestamp(seconds_ago=1, content="hello")
    decision = engine.preprocess(
        user_message="ещё",
        session_history=history,
        config={"cooldown_seconds": 5.0},
    )
    assert decision.route == RouteDecision.NO_ACTION
    assert decision.flags["cooldown_ok"] is False


def test_rule_engine_high_complexity_routes_fallback() -> None:
    engine = RuleEngine()
    repeated = ("не понимаю как исправить это ? " * 40).strip()
    history = _history_with_timestamp(seconds_ago=120, content=repeated)
    decision = engine.preprocess(repeated, session_history=history, config={})
    assert decision.route == RouteDecision.FALLBACK
    assert decision.complexity >= 0.75


@pytest.mark.asyncio
async def test_navigator_analyze_slm_success(tmp_path: Path) -> None:
    response = LLMResponse(
        content=(
            '{"hint":"Сфокусируйся на первом stacktrace и воспроизведи ошибку локально.",'
            '"focus":"Первый stacktrace"}'
        ),
        usage={"prompt_tokens": 18, "completion_tokens": 9, "total_tokens": 27},
    )
    navigator = NavigatorAgent(
        provider=DummyProvider(response),
        model="qwen-2.5-1.5b-instruct",
        timeout_seconds=2.0,
        log_path=str(tmp_path / "navigator_pilot.jsonl"),
    )
    history = _history_with_timestamp(seconds_ago=30, content="предыдущее сообщение")
    result = await navigator.analyze(
        session_history=history,
        user_message="У меня ошибка, не понимаю как починить?",
        config={"thresholds": {"complexity_low": 0.30, "complexity_high": 0.75}},
        conversation_id="test:session",
    )

    assert result.route == RouteDecision.SLM.value
    assert result.hint is not None
    assert result.metrics["tokens_in"] == 18
    assert result.metrics["tokens_out"] == 9

    log_path = tmp_path / "navigator_pilot.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["route"] == RouteDecision.SLM.value
    assert payload["tokens_in"] == 18


@pytest.mark.asyncio
async def test_navigator_analyze_invalid_json_falls_back(tmp_path: Path) -> None:
    response = LLMResponse(content="not-a-json-response", usage={})
    navigator = NavigatorAgent(
        provider=DummyProvider(response),
        model="qwen-2.5-1.5b-instruct",
        timeout_seconds=2.0,
        log_path=str(tmp_path / "navigator_pilot.jsonl"),
    )
    history = _history_with_timestamp(seconds_ago=45, content="старое")
    result = await navigator.analyze(
        session_history=history,
        user_message="Не понимаю, как исправить это?",
        config={"thresholds": {"complexity_low": 0.30, "complexity_high": 0.75}},
        conversation_id="fallback:test",
    )
    assert result.route == RouteDecision.FALLBACK.value
    assert result.hint is None


def test_navigator_should_run_respects_mode_and_flag() -> None:
    navigator = NavigatorAgent(
        provider=DummyProvider(LLMResponse(content='{"hint":"ok","focus":"x"}')),
        log_path="logs/test-navigator.jsonl",
    )
    assert navigator.should_run("s:1", {"enabled": True, "mode": "hybrid", "canary_percent": 0})
    assert not navigator.should_run("s:1", {"enabled": False, "mode": "hybrid", "canary_percent": 0})
    assert not navigator.should_run("s:1", {"enabled": True, "mode": "pure_ai", "canary_percent": 0})
    assert navigator.should_run("s:1", {"enabled": True, "mode": "hybrid", "canary_percent": 100})
