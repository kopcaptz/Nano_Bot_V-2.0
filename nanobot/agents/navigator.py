"""Hybrid navigator agent (rules + SLM) for pre-routing hints."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from enum import Enum
from pathlib import Path
from typing import Any

try:
    from loguru import logger
except ImportError:  # pragma: no cover - fallback for minimal environments
    import logging

    logger = logging.getLogger(__name__)

from nanobot.providers.base import LLMProvider


class RouteDecision(str, Enum):
    """Deterministic routing decisions from the rule engine."""

    NO_ACTION = "NO_ACTION"
    TEMPLATE = "TEMPLATE"
    SLM = "SLM"
    FALLBACK = "FALLBACK"


@dataclass
class RuleEngineDecision:
    """Intermediate result produced by the rule engine."""

    route: RouteDecision
    tags: list[str]
    flags: dict[str, Any]
    metrics: dict[str, float]
    complexity: float
    llm_payload: dict[str, Any] | None


@dataclass
class SLMHint:
    """Validated SLM output and usage telemetry."""

    hint: str
    focus: str
    tokens_in: int
    tokens_out: int
    latency_ms: float


@dataclass
class NavigatorResult:
    """Public result returned to the main agent loop."""

    route: str
    hint: str | None
    metrics: dict[str, Any]
    complexity: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result for logging/debug output."""
        return {
            "route": self.route,
            "hint": self.hint,
            "metrics": self.metrics,
            "complexity": self.complexity,
        }


def has_pii(text: str) -> bool:
    """PII detector stub. Extend with a real detector in production."""
    _ = text
    return False


def is_toxic(text: str) -> bool:
    """Toxicity detector stub. Extend with a real detector in production."""
    _ = text
    return False


class RuleEngine:
    """Deterministic preprocessing, tagging, scoring, and routing."""

    _TAG_PATTERNS: dict[str, re.Pattern[str]] = {
        "urgency": re.compile(r"\b(срочно|горит|urgency|urgent|asap)\b", re.IGNORECASE),
        "issue": re.compile(r"\b(ошибка|сломалось|не работает|error|bug|broken)\b", re.IGNORECASE),
        "guidance_needed": re.compile(
            r"\b(не понимаю|что дальше|как\b|подскажи|help|how to|what next)\b",
            re.IGNORECASE,
        ),
    }
    _STUCK_PATTERNS = re.compile(
        r"\b(застрял|не получается|не могу|stuck|blocked|confused)\b",
        re.IGNORECASE,
    )

    def preprocess(
        self,
        user_message: str,
        session_history: list[dict[str, Any]] | None,
        config: dict[str, Any] | None = None,
    ) -> RuleEngineDecision:
        """Calculate metrics and route the current turn."""
        cfg = config or {}
        thresholds = cfg.get("thresholds", {})
        low = _as_float(thresholds.get("complexity_low"), 0.30)
        high = _as_float(thresholds.get("complexity_high"), 0.75)
        if high <= low:
            high = min(low + 0.10, 1.0)
        cooldown_seconds = _as_float(cfg.get("cooldown_seconds"), 2.0)

        normalized = self._normalize(user_message)
        history = session_history or []

        prev_user = self._last_user_message(history)
        idle_sec = self._idle_seconds(history)
        repeat_score = self._similarity(normalized, prev_user)
        question_count = normalized.count("?")

        metrics = {
            "char_len": float(len(normalized)),
            "token_est": float(self._estimate_tokens(normalized)),
            "idle_sec": float(idle_sec),
            "question_count": float(question_count),
            "repeat_score": float(round(repeat_score, 4)),
        }

        tags = [
            tag for tag, pattern in self._TAG_PATTERNS.items() if pattern.search(normalized)
        ]
        flags = {
            "risk_pii": has_pii(normalized),
            "risk_toxic": is_toxic(normalized),
            "stage": self._detect_stage(history, normalized, repeat_score, idle_sec),
            "cooldown_ok": idle_sec >= cooldown_seconds,
        }

        complexity = 0.0
        complexity += min(metrics["token_est"] / 120.0, 1.0) * 0.35
        complexity += float(metrics["question_count"] > 0) * 0.20
        complexity += float(metrics["repeat_score"] > 0.90) * 0.20
        complexity += float("guidance_needed" in tags) * 0.25
        complexity = max(0.0, min(complexity, 1.0))

        route = RouteDecision.FALLBACK
        llm_payload: dict[str, Any] | None = None

        if not flags["cooldown_ok"]:
            route = RouteDecision.NO_ACTION
        elif flags["risk_pii"] or flags["risk_toxic"] or complexity < low:
            route = RouteDecision.TEMPLATE
        elif complexity < high:
            route = RouteDecision.SLM
            llm_payload = self._build_llm_payload(
                user_message=normalized,
                session_history=history,
                tags=tags,
                flags=flags,
                metrics=metrics,
            )
        else:
            route = RouteDecision.FALLBACK

        return RuleEngineDecision(
            route=route,
            tags=tags,
            flags=flags,
            metrics=metrics,
            complexity=round(complexity, 4),
            llm_payload=llm_payload,
        )

    def _build_llm_payload(
        self,
        user_message: str,
        session_history: list[dict[str, Any]],
        tags: list[str],
        flags: dict[str, Any],
        metrics: dict[str, float],
    ) -> dict[str, Any]:
        """Prepare compact structured facts for SLM prompt."""
        return {
            "facts": {
                "user_message": user_message,
                "tags": tags,
                "stage": flags.get("stage", "active"),
                "metrics": {
                    "token_est": int(metrics["token_est"]),
                    "idle_sec": round(metrics["idle_sec"], 2),
                    "question_count": int(metrics["question_count"]),
                    "repeat_score": round(metrics["repeat_score"], 4),
                },
                "recent_summary": self._recent_summary(session_history),
            },
            "constraints": {
                "language": "ru",
                "tone": "calm, actionable",
                "max_words": 40,
                "format": "json",
            },
        }

    def _detect_stage(
        self,
        session_history: list[dict[str, Any]],
        message: str,
        repeat_score: float,
        idle_sec: float,
    ) -> str:
        """Detect lightweight FSM stage: start / active / stuck."""
        user_turns = sum(1 for item in session_history if item.get("role") == "user")
        if user_turns < 2:
            return "start"
        if repeat_score > 0.90 or idle_sec > 600 or self._STUCK_PATTERNS.search(message):
            return "stuck"
        return "active"

    def _recent_summary(self, session_history: list[dict[str, Any]], limit: int = 4) -> str:
        """Build compact factual context for SLM consumption."""
        snippets: list[str] = []
        for item in session_history[-limit:]:
            role = item.get("role", "unknown")
            content = self._normalize(str(item.get("content", "")))
            if not content:
                continue
            snippets.append(f"{role}: {content[:120]}")
        return " | ".join(snippets)

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize whitespace for deterministic metrics."""
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Fast token estimate used by the deterministic rules."""
        if not text:
            return 0
        words = len(text.split())
        by_chars = max(1, round(len(text) / 4))
        return max(words, by_chars)

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        """Similarity score used for repeat/fatigue detection."""
        if not left or not right:
            return 0.0
        return SequenceMatcher(None, left, right).ratio()

    @staticmethod
    def _last_user_message(history: list[dict[str, Any]]) -> str:
        """Return latest user message from history if present."""
        for item in reversed(history):
            if item.get("role") == "user":
                return str(item.get("content", ""))
        return ""

    @staticmethod
    def _idle_seconds(history: list[dict[str, Any]]) -> float:
        """Seconds elapsed since the latest message timestamp."""
        for item in reversed(history):
            raw = item.get("timestamp")
            if not raw:
                continue
            parsed = _parse_iso_timestamp(str(raw))
            if parsed:
                delta = datetime.now(timezone.utc) - parsed
                return max(delta.total_seconds(), 0.0)
        return 9_999.0


class SLMNavigator:
    """Generate short semantic hints using a small instruction model."""

    SYSTEM_PROMPT = (
        "Ты Штурман. На основе фактов сгенерируй 1 предложение (макс 40 слов) для Пилота. "
        "Тон: calm, actionable. Формат: JSON {\"hint\": \"...\", \"focus\": \"...\"}. "
        "Возвращай только валидный JSON без markdown."
    )

    def __init__(
        self,
        provider: LLMProvider,
        model: str = "qwen-2.5-1.5b-instruct",
        timeout_seconds: float = 2.0,
    ) -> None:
        self.provider = provider
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def generate_hint(self, payload: dict[str, Any]) -> SLMHint | None:
        """Call SLM with structured facts and return validated JSON output."""
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

        started = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                self.provider.chat(
                    messages=messages,
                    model=self.model,
                    max_tokens=120,
                    temperature=0.1,
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("Navigator SLM call timed out after {}s", self.timeout_seconds)
            return None
        except Exception as exc:  # pragma: no cover - defensive catch
            logger.warning("Navigator SLM call failed: {}", exc)
            return None

        latency_ms = (time.perf_counter() - started) * 1000
        parsed = self._parse_json(response.content or "")
        if not parsed:
            return None

        hint = self._limit_words(parsed.get("hint", ""), max_words=40)
        focus = self._limit_words(parsed.get("focus", ""), max_words=20)
        if not hint:
            return None

        usage = response.usage or {}
        return SLMHint(
            hint=hint,
            focus=focus,
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
            latency_ms=round(latency_ms, 2),
        )

    def _parse_json(self, content: str) -> dict[str, Any] | None:
        """Robust JSON extraction from compact model output."""
        text = content.strip()
        if not text:
            return None
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()

        for candidate in (text, self._extract_json_object(text)):
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    @staticmethod
    def _extract_json_object(text: str) -> str | None:
        """Extract first JSON object from a noisy response string."""
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        return match.group(0) if match else None

    @staticmethod
    def _limit_words(value: str, max_words: int) -> str:
        """Collapse whitespace and clip to max words."""
        clean = re.sub(r"\s+", " ", str(value or "")).strip()
        if not clean:
            return ""
        words = clean.split(" ")
        if len(words) <= max_words:
            return clean
        return " ".join(words[:max_words]).strip()


class NavigatorAgent:
    """Top-level orchestrator for the hybrid navigator pipeline."""

    def __init__(
        self,
        provider: LLMProvider,
        model: str = "qwen-2.5-1.5b-instruct",
        timeout_seconds: float = 2.0,
        log_path: str = "logs/navigator_pilot.jsonl",
    ) -> None:
        self.rule_engine = RuleEngine()
        self.slm = SLMNavigator(provider=provider, model=model, timeout_seconds=timeout_seconds)
        self.log_path = Path(log_path)
        self._log_lock = asyncio.Lock()

    def should_run(self, conversation_id: str, config: dict[str, Any] | None) -> bool:
        """Evaluate feature flag + mode + canary for this conversation."""
        cfg = config or {}
        if not bool(cfg.get("enabled", False)):
            return False
        if str(cfg.get("mode", "off")).lower() != "hybrid":
            return False

        canary_percent = int(cfg.get("canary_percent", 0))
        if canary_percent <= 0:
            return True
        if canary_percent >= 100:
            return True
        bucket = self._bucket(conversation_id)
        return bucket < canary_percent

    async def analyze(
        self,
        session_history: list[dict[str, Any]],
        user_message: str,
        config: dict[str, Any] | None = None,
        conversation_id: str = "unknown",
    ) -> NavigatorResult:
        """
        Run rules-first analysis; call SLM only for medium complexity route.

        Returns:
            NavigatorResult with route, optional hint, metrics, and complexity.
        """
        cfg = config or {}
        decision = self.rule_engine.preprocess(
            user_message=user_message,
            session_history=session_history,
            config=cfg,
        )

        route = decision.route
        hint_text: str | None = None
        focus_text: str = ""
        tokens_in = 0
        tokens_out = 0
        latency_ms = 0.0

        if route == RouteDecision.SLM:
            slm_hint = await self.slm.generate_hint(decision.llm_payload or {})
            if slm_hint is None:
                route = RouteDecision.FALLBACK
            else:
                hint_text = slm_hint.hint
                focus_text = slm_hint.focus
                tokens_in = slm_hint.tokens_in
                tokens_out = slm_hint.tokens_out
                latency_ms = slm_hint.latency_ms

        cost_usd = self._estimate_cost(tokens_in, tokens_out, cfg)
        baseline_tokens = max(80, int(decision.metrics.get("token_est", 0) + 40))
        tokens_saved_est = max(0, baseline_tokens - tokens_in - tokens_out)

        metrics: dict[str, Any] = {
            **decision.metrics,
            "tags": decision.tags,
            "flags": decision.flags,
            "focus": focus_text,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
            "tokens_saved_est": tokens_saved_est,
        }
        result = NavigatorResult(
            route=route.value,
            hint=hint_text,
            metrics=metrics,
            complexity=decision.complexity,
        )
        await self._log_turn(conversation_id=conversation_id, result=result, model=self.slm.model)
        return result

    async def _log_turn(
        self,
        conversation_id: str,
        result: NavigatorResult,
        model: str,
    ) -> None:
        """Persist navigator decision into pilot JSONL logs."""
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "conversation_id": self._hash_conversation_id(conversation_id),
            "route": result.route,
            "complexity_score": result.complexity,
            "tags": result.metrics.get("tags", []),
            "model": model,
            "tokens_in": int(result.metrics.get("tokens_in", 0)),
            "tokens_out": int(result.metrics.get("tokens_out", 0)),
            "latency_ms": float(result.metrics.get("latency_ms", 0.0)),
            "cost_usd": float(result.metrics.get("cost_usd", 0.0)),
            "tokens_saved_est": int(result.metrics.get("tokens_saved_est", 0)),
        }
        try:
            async with self._log_lock:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as exc:  # pragma: no cover - log path issues should not break flow
            logger.warning("Failed to write navigator pilot log: {}", exc)

        logger.info(json.dumps({"event": "navigator_turn", **event}, ensure_ascii=False))

    @staticmethod
    def _bucket(conversation_id: str) -> int:
        """Deterministic conversation bucket in [0, 99]."""
        digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % 100

    @staticmethod
    def _hash_conversation_id(conversation_id: str) -> str:
        """Hash conversation id before writing to telemetry logs."""
        return hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _estimate_cost(tokens_in: int, tokens_out: int, config: dict[str, Any]) -> float:
        """Estimate SLM cost from configurable per-1k token rates."""
        pricing = config.get("pricing", {})
        in_per_1k = _as_float(pricing.get("input_per_1k"), 0.0)
        out_per_1k = _as_float(pricing.get("output_per_1k"), 0.0)
        total = (tokens_in / 1000.0) * in_per_1k + (tokens_out / 1000.0) * out_per_1k
        return round(total, 7)


def _parse_iso_timestamp(value: str) -> datetime | None:
    """Parse ISO timestamp to timezone-aware datetime."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_float(value: Any, default: float) -> float:
    """Safe float conversion with fallback."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
