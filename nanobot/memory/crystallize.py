"""Кристаллизация памяти: извлечение фактов из диалогов через LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.memory.db import add_fact
from nanobot.providers.base import LLMProvider


def _get_sessions_dir() -> Path:
    """Путь к директории сессий (monkeypatch в тестах)."""
    return Path.home() / ".nanobot" / "sessions"


def _load_messages_from_sessions(limit: int = 100) -> list[dict[str, Any]]:
    """
    Читает сообщения из JSONL-файлов SessionManager (~/.nanobot/sessions/).

    Возвращает список в формате crystallize: chat_id, role, timestamp, message.
    Сообщения отсортированы по timestamp, возвращаются последние limit.
    """
    sessions_dir = _get_sessions_dir()
    if not sessions_dir.exists():
        return []

    rows: list[dict[str, Any]] = []
    for path in sessions_dir.glob("*.jsonl"):
        try:
            key = path.stem.replace("_", ":")
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    if data.get("_type") == "metadata":
                        continue
                    role = str(data.get("role", ""))
                    content = str(data.get("content", ""))
                    timestamp = str(data.get("timestamp", ""))
                    rows.append({
                        "chat_id": key,
                        "role": role,
                        "timestamp": timestamp,
                        "message": content,
                    })
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug(f"Crystallize: skip {path.name}: {exc}")
            continue

    rows.sort(key=lambda r: r.get("timestamp", ""))
    return rows[-limit:] if len(rows) > limit else rows


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
    rows = _load_messages_from_sessions(limit=messages_limit)
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
