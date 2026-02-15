"""Кристаллизация памяти: извлечение фактов из диалогов через LLM."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from nanobot.memory.db import add_fact, get_recent_conversations
from nanobot.providers.base import LLMProvider


CRYSTALLIZE_PROMPT = """Проанализируй эти диалоги. Найди:
- Предпочтения пользователя
- Повторяющиеся темы
- Важные факты
Верни список фактов в формате JSON:
[{"category": "...", "key": "...", "value": "..."}]

Требования:
- Верни только JSON-массив (без markdown и без пояснений).
- category/key/value должны быть короткими и конкретными.
- Не добавляй дубликаты.
- Если фактов нет, верни [].
"""


def _build_dialogue_payload(rows: list[dict[str, Any]]) -> str:
    """Готовит компактный текст диалогов для отправки в LLM."""
    compact_rows: list[dict[str, str]] = []
    for row in rows:
        compact_rows.append(
            {
                "chat_id": str(row.get("chat_id", "")),
                "role": str(row.get("role", "")),
                "timestamp": str(row.get("timestamp", "")),
                "message": str(row.get("message", "")),
            }
        )
    return json.dumps(compact_rows, ensure_ascii=False, indent=2)


def _extract_json_array(raw: str) -> list[dict[str, Any]]:
    """Пытается извлечь JSON-массив фактов из ответа модели."""
    text = (raw or "").strip()
    if not text:
        return []

    # 1) Прямой JSON.
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
    except Exception:
        pass

    # 2) JSON в markdown-блоке.
    if "```" in text:
        blocks = text.split("```")
        for block in blocks:
            candidate = block.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            try:
                obj = json.loads(candidate)
                if isinstance(obj, list):
                    return [x for x in obj if isinstance(x, dict)]
            except Exception:
                continue

    # 3) JSON-массив внутри произвольного текста.
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            obj = json.loads(candidate)
            if isinstance(obj, list):
                return [x for x in obj if isinstance(x, dict)]
        except Exception:
            pass

    return []


def _normalize_facts(raw_facts: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Нормализует и дедуплицирует факты перед сохранением."""
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for item in raw_facts:
        category = str(item.get("category", "")).strip()
        key = str(item.get("key", "")).strip()
        value = str(item.get("value", "")).strip()
        if not category or not key or not value:
            continue

        identity = (category.lower(), key.lower(), value.lower())
        if identity in seen:
            continue
        seen.add(identity)

        normalized.append(
            {
                "category": category,
                "key": key,
                "value": value,
            }
        )

    return normalized


async def crystallize_memories(
    provider: LLMProvider,
    messages_limit: int = 100,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """
    Кристаллизует память из последних диалогов и сохраняет факты в SQLite.

    Args:
        provider: LLM-провайдер nanobot.
        messages_limit: Сколько последних сообщений анализировать.
        model: Модель для извлечения фактов (по умолчанию дешевая).

    Returns:
        Сводка выполнения (сколько сообщений обработано, сколько фактов сохранено и т.д.).
    """
    rows = get_recent_conversations(limit=messages_limit)
    if not rows:
        return {
            "processed_messages": 0,
            "extracted_facts": 0,
            "saved_facts": 0,
            "model": model,
            "facts": [],
        }

    payload = _build_dialogue_payload(rows)
    messages = [
        {
            "role": "system",
            "content": "Ты извлекаешь структурированные факты из диалогов. Отвечай строго JSON-массивом.",
        },
        {
            "role": "user",
            "content": f"{CRYSTALLIZE_PROMPT}\n\nДиалоги для анализа:\n{payload}",
        },
    ]

    response = await provider.chat(
        messages=messages,
        model=model,
        temperature=0.1,
        max_tokens=1600,
    )
    raw = response.content or "[]"
    parsed = _extract_json_array(raw)
    facts = _normalize_facts(parsed)

    saved = 0
    for fact in facts:
        try:
            add_fact(fact["category"], fact["key"], fact["value"])
            saved += 1
        except Exception as exc:
            logger.warning(f"Crystallize: failed to save fact {fact}: {exc}")

    return {
        "processed_messages": len(rows),
        "extracted_facts": len(facts),
        "saved_facts": saved,
        "model": model,
        "facts": facts,
    }
