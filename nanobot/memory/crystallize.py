"""Кристаллизация памяти: извлечение фактов из диалогов через LLM."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.memory.db import add_fact
from nanobot.providers.base import LLMProvider

if TYPE_CHECKING:
    from nanobot.session.manager import SessionManager


CRYSTALLIZE_PROMPT = """Analyze the following dialogues. Extract key facts and user preferences, structuring them hierarchically.

Return a JSON array with this structure:
[{"domain": "...", "category": "...", "sub_category": "...", "key": "...", "value": "..."}]

**Hierarchy Guidelines:**
- domain: Broad area or project (e.g., "User Preferences", "Project: Nano Bot", "Technology: Python", "Work", "Personal").
- category: Specific topic within the domain (e.g., "Architecture", "Hobbies", "Libraries", "Communication").
- sub_category: Optional further detail (e.g., "Database", "Music Genres"). Set to null if not applicable.
- key: The specific attribute name.
- value: The attribute value.

**Requirements:**
- Return ONLY the JSON array (no markdown, no explanations).
- Be specific and concise in key/value pairs.
- Avoid duplicates.
- If no facts found, return [].

**Example:**
[
  {"domain": "User Preferences", "category": "Communication", "sub_category": null, "key": "Preferred Language", "value": "Russian"},
  {"domain": "Project: Nano Bot", "category": "Architecture", "sub_category": "Memory", "key": "Vector DB Engine", "value": "ChromaDB"},
  {"domain": "Personal", "category": "Schedule", "sub_category": null, "key": "Work Hours", "value": "9:00-18:00"}
]"""


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


def _normalize_facts(raw_facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Нормализует и дедуплицирует факты перед сохранением."""
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for item in raw_facts:
        domain = str(item.get("domain", "")).strip() or "general"
        category = str(item.get("category", "")).strip()
        sub_category = str(item.get("sub_category") or "").strip() or None
        key = str(item.get("key", "")).strip()
        value = str(item.get("value", "")).strip()
        if not category or not key or not value:
            continue

        identity = (domain.lower(), category.lower(), key.lower())
        if identity in seen:
            continue
        seen.add(identity)

        fact: dict[str, Any] = {"domain": domain, "category": category, "key": key, "value": value}
        if sub_category:
            fact["sub_category"] = sub_category
        normalized.append(fact)

    return normalized


def _load_messages_from_sessions(
    session_manager: "SessionManager",
    sessions_limit: int = 20,
    messages_limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Загружает сообщения из нескольких последних сессий (JSONL-файлов).

    Args:
        session_manager: Экземпляр SessionManager.
        sessions_limit: Сколько последних сессий загружать (по умолчанию 20).
        messages_limit: Максимум сообщений в итоговом массиве.

    Returns:
        Список сообщений в формате {chat_id, role, timestamp, message}.
    """
    rows: list[dict[str, Any]] = []
    sessions = session_manager.list_sessions()[:sessions_limit]

    for info in sessions:
        key = info.get("key", "")
        if not key:
            continue
        session = session_manager.get_or_create(key)
        for msg in session.messages:
            rows.append(
                {
                    "chat_id": key,
                    "role": str(msg.get("role", "")),
                    "timestamp": str(msg.get("timestamp", "")),
                    "message": str(msg.get("content", "")),
                }
            )

    # Сортируем по timestamp (хронологически) и обрезаем до limit
    rows.sort(key=lambda r: r.get("timestamp", ""))
    return rows[-messages_limit:]


async def crystallize_memories(
    provider: LLMProvider,
    session_manager: "SessionManager",
    *,
    sessions_limit: int = 20,
    messages_limit: int = 100,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """
    Кристаллизует память из последних диалогов (JSONL-сессий) и сохраняет факты в SQLite.

    Args:
        provider: LLM-провайдер nanobot.
        session_manager: Экземпляр SessionManager для доступа к диалогам в JSONL.
        sessions_limit: Сколько последних сессий загружать (по умолчанию 20).
        messages_limit: Сколько последних сообщений анализировать.
        model: Модель для извлечения фактов (по умолчанию дешевая).

    Returns:
        Сводка выполнения (сколько сообщений обработано, сколько фактов сохранено и т.д.).
    """
    rows = _load_messages_from_sessions(
        session_manager,
        sessions_limit=sessions_limit,
        messages_limit=messages_limit,
    )
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
            add_fact(
                category=fact["category"],
                key=fact["key"],
                value=fact["value"],
                domain=fact.get("domain"),
                sub_category=fact.get("sub_category"),
            )
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
