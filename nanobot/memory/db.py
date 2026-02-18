"""SQLite-хранилище памяти для nanobot."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from nanobot.memory.vector import (
    add_memory as add_vector_memory,
    delete_memory as delete_vector_memory,
    search_similar,
)


logger = logging.getLogger(__name__)


# Путь к базе данных памяти: ~/.nanobot/memory.db
DB_PATH = Path.home() / ".nanobot" / "memory.db"


def _now_iso() -> str:
    """Возвращает текущее время в ISO-формате."""
    return datetime.now().isoformat(timespec="seconds")


def _ensure_db_dir() -> None:
    """Гарантирует, что директория для БД существует."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    """Создает подключение к SQLite с удобным доступом к колонкам."""
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Создает базу и таблицы, если они еще не существуют."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                domain TEXT,
                sub_category TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(category, key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                requests INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(date, model)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_usage_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE,
                conversation_key TEXT,
                timestamp TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0,
                iteration INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reflections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT NOT NULL,
                tool_args TEXT,
                error_text TEXT NOT NULL,
                insight TEXT NOT NULL,
                session_key TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        # Индексы для ускорения частых выборок и поиска.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_journal_date ON journal(date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_chat_id ON conversations(chat_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_date ON token_usage(date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_calls_timestamp ON token_usage_calls(timestamp DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_calls_session ON token_usage_calls(session_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_calls_conversation_timestamp ON token_usage_calls(conversation_key, timestamp DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reflections_tool ON reflections(tool_name)"
        )

        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Преобразует sqlite3.Row в обычный dict."""
    return dict(row)


def _fact_vector_id(category: str, key: str) -> str:
    """Строит стабильный id факта для векторной памяти."""
    return f"fact::{category}::{key}"


def add_fact(
    category: str,
    key: str,
    value: str,
    domain: str | None = None,
    sub_category: str | None = None,
) -> None:
    """Добавляет факт или обновляет значение, если факт уже есть."""
    init_db()
    now = _now_iso()
    domain_val = domain if domain and str(domain).strip() else None
    sub_val = sub_category if sub_category and str(sub_category).strip() else None

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO facts (category, key, value, domain, sub_category, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(category, key)
            DO UPDATE SET
                value = excluded.value,
                domain = COALESCE(excluded.domain, domain),
                sub_category = COALESCE(excluded.sub_category, sub_category),
                updated_at = excluded.updated_at
            """,
            (category, key, value, domain_val, sub_val, now, now),
        )
        conn.commit()

    # Синхронизируем факт в ChromaDB для семантического поиска.
    try:
        text = f"Domain: {domain_val or 'general'}\nКатегория: {category}\nКлюч: {key}\nЗначение: {value}"
        metadata: dict[str, Any] = {
            "type": "fact",
            "category": category,
            "key": key,
            "value": value,
            "updated_at": now,
        }
        if domain_val:
            metadata["domain"] = domain_val
        if sub_val:
            metadata["sub_category"] = sub_val
        add_vector_memory(
            memory_id=_fact_vector_id(category, key),
            text=text,
            metadata=metadata,
        )
    except Exception as exc:
        # Векторный индекс не должен ломать SQLite-операции.
        logger.debug("Failed to sync fact into vector DB: %s", exc)


def get_fact(category: str, key: str) -> dict[str, Any] | None:
    """Возвращает один факт по категории и ключу."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, category, key, value, created_at, updated_at
            FROM facts
            WHERE category = ? AND key = ?
            LIMIT 1
            """,
            (category, key),
        ).fetchone()
    return _row_to_dict(row) if row else None


def delete_fact(category: str, key: str) -> bool:
    """Удаляет факт по категории и ключу. Возвращает True, если запись была удалена."""
    init_db()
    with _connect() as conn:
        cursor = conn.execute(
            """
            DELETE FROM facts
            WHERE category = ? AND key = ?
            """,
            (category, key),
        )
        conn.commit()
    removed = cursor.rowcount > 0
    if removed:
        # best-effort: удаляем и векторную копию факта.
        try:
            delete_vector_memory(_fact_vector_id(category, key))
        except Exception as exc:
            logger.debug("Failed to delete fact from vector DB: %s", exc)
    return removed


def get_facts_by_category(category: str) -> list[dict[str, Any]]:
    """Возвращает все факты выбранной категории."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, category, key, value, created_at, updated_at
            FROM facts
            WHERE category = ?
            ORDER BY key ASC
            """,
            (category,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_facts_filtered(
    domain: str | None = None,
    category: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Возвращает факты с фильтрацией по domain и/или category."""
    init_db()
    conditions: list[str] = []
    params: list[Any] = []
    if domain:
        conditions.append("domain = ?")
        params.append(domain)
    if category:
        conditions.append("category = ?")
        params.append(category)

    where = " AND ".join(conditions) if conditions else "1=1"
    params.append(limit)

    with _connect() as conn:
        try:
            rows = conn.execute(
                f"SELECT * FROM facts WHERE {where} ORDER BY updated_at DESC LIMIT ?",
                params,
            ).fetchall()
        except sqlite3.OperationalError:
            # Fallback when domain/sub_category columns don't exist yet
            if category:
                rows = conn.execute(
                    "SELECT * FROM facts WHERE category = ? ORDER BY updated_at DESC LIMIT ?",
                    (category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM facts ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()

    return [_row_to_dict(row) for row in rows]


def search_facts(query: str) -> list[dict[str, Any]]:
    """Ищет факты по LIKE в полях category, key и value."""
    init_db()
    pattern = f"%{query}%"
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, category, key, value, created_at, updated_at
            FROM facts
            WHERE category LIKE ? OR key LIKE ? OR value LIKE ?
            ORDER BY updated_at DESC
            """,
            (pattern, pattern, pattern),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def semantic_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    Выполняет семантический поиск фактов через векторную память ChromaDB.

    Возвращает список фактов в формате, совместимом с search_facts().
    Если ChromaDB недоступен, выбрасывает исключение (для fallback на уровне context.py).
    """
    hits = search_similar(query=query, limit=limit)

    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for hit in hits:
        metadata = hit.get("metadata") or {}
        if metadata.get("type") not in (None, "fact"):
            continue

        category = str(metadata.get("category", "")).strip()
        key = str(metadata.get("key", "")).strip()
        value = str(metadata.get("value", "")).strip()

        if not category or not key:
            continue
        identity = (category, key)
        if identity in seen:
            continue
        seen.add(identity)

        domain_val = str(metadata.get("domain", "")).strip() or None
        sub_cat = str(metadata.get("sub_category", "")).strip() or None
        results.append(
            {
                "id": None,
                "domain": domain_val,
                "category": category,
                "sub_category": sub_cat,
                "key": key,
                "value": value,
                "created_at": metadata.get("created_at", ""),
                "updated_at": metadata.get("updated_at", ""),
                "distance": hit.get("distance"),
            }
        )

    return results


def add_journal(date: str, content: str) -> None:
    """Добавляет запись в журнал за указанную дату."""
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO journal (date, content, created_at)
            VALUES (?, ?, ?)
            """,
            (date, content, _now_iso()),
        )
        conn.commit()


def get_journal(date: str) -> list[dict[str, Any]]:
    """Возвращает все записи журнала за дату (по времени добавления)."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, date, content, created_at
            FROM journal
            WHERE date = ?
            ORDER BY created_at ASC, id ASC
            """,
            (date,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def add_message(chat_id: str, role: str, message: str) -> None:
    """Сохраняет сообщение диалога."""
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO conversations (chat_id, role, message, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, role, message, _now_iso()),
        )
        conn.commit()


def get_conversation(chat_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Возвращает последние сообщения чата в хронологическом порядке."""
    init_db()
    safe_limit = max(1, int(limit))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, chat_id, role, message, timestamp
            FROM conversations
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (chat_id, safe_limit),
        ).fetchall()

    # Из БД выбраны последние N сообщений, разворачиваем в хронологию.
    return [_row_to_dict(row) for row in reversed(rows)]


def get_recent_conversations(limit: int = 100) -> list[dict[str, Any]]:
    """
    Возвращает последние N сообщений из conversations в хронологическом порядке.

    Используется для кристаллизации памяти.
    """
    init_db()
    safe_limit = max(1, int(limit))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, chat_id, role, message, timestamp
            FROM conversations
            ORDER BY id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    return [_row_to_dict(row) for row in reversed(rows)]


# ============== REFLECTIONS ==============


def add_reflection(
    tool_name: str,
    tool_args: str,
    error_text: str,
    insight: str,
    session_key: str | None = None,
) -> None:
    """Сохраняет рефлексию об ошибке инструмента."""
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO reflections (tool_name, tool_args, error_text, insight, session_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (tool_name, tool_args, error_text, insight, session_key, _now_iso()),
        )
        conn.commit()


def get_recent_reflections(
    tool_name: str | None = None, limit: int = 10
) -> list[dict[str, Any]]:
    """Возвращает последние рефлексии, опционально фильтруя по инструменту."""
    init_db()
    if tool_name:
        query = "SELECT * FROM reflections WHERE tool_name = ? ORDER BY id DESC LIMIT ?"
        params = (tool_name, limit)
    else:
        query = "SELECT * FROM reflections ORDER BY id DESC LIMIT ?"
        params = (limit,)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(row) for row in rows]


# ============== TOKEN USAGE ==============


def add_token_usage(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> None:
    """Добавляет использование токенов за сегодня."""
    init_db()
    today = datetime.now().strftime("%Y-%m-%d")
    now = _now_iso()
    
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO token_usage (date, model, prompt_tokens, completion_tokens, total_tokens, requests, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(date, model)
            DO UPDATE SET
                prompt_tokens = prompt_tokens + excluded.prompt_tokens,
                completion_tokens = completion_tokens + excluded.completion_tokens,
                total_tokens = total_tokens + excluded.total_tokens,
                requests = requests + 1,
                updated_at = excluded.updated_at
            """,
            (today, model, prompt_tokens, completion_tokens, total_tokens, now, now),
        )
        conn.commit()


def add_token_usage_call(
    session_id: str,
    request_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cost_usd: float = 0.0,
    iteration: int | None = None,
    conversation_key: str | None = None,
    timestamp: str | None = None,
) -> None:
    """Сохраняет usage одного LLM-вызова для forensics."""
    init_db()
    now = _now_iso()
    event_ts = timestamp or now

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO token_usage_calls (
                session_id,
                request_id,
                conversation_key,
                timestamp,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                cost_usd,
                iteration,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(request_id) DO NOTHING
            """,
            (
                str(session_id),
                str(request_id),
                conversation_key,
                event_ts,
                model,
                int(prompt_tokens),
                int(completion_tokens),
                int(total_tokens),
                float(cost_usd),
                iteration,
                now,
            ),
        )
        conn.commit()


def get_token_usage_today() -> dict[str, Any]:
    """Возвращает статистику токенов за сегодня."""
    init_db()
    today = datetime.now().strftime("%Y-%m-%d")
    
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT model, prompt_tokens, completion_tokens, total_tokens, requests
            FROM token_usage
            WHERE date = ?
            ORDER BY total_tokens DESC
            """,
            (today,),
        ).fetchall()
    
    models = [_row_to_dict(row) for row in rows]
    
    totals = {
        "date": today,
        "prompt_tokens": sum(m["prompt_tokens"] for m in models),
        "completion_tokens": sum(m["completion_tokens"] for m in models),
        "total_tokens": sum(m["total_tokens"] for m in models),
        "requests": sum(m["requests"] for m in models),
        "by_model": models,
    }
    
    return totals


def get_token_usage_period(days: int = 7) -> list[dict[str, Any]]:
    """Возвращает статистику токенов за последние N дней."""
    init_db()
    
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT date,
                   SUM(prompt_tokens) as prompt_tokens,
                   SUM(completion_tokens) as completion_tokens,
                   SUM(total_tokens) as total_tokens,
                   SUM(requests) as requests
            FROM token_usage
            GROUP BY date
            ORDER BY date DESC
            LIMIT ?
            """,
            (days,),
        ).fetchall()
    
    return [_row_to_dict(row) for row in rows]


def get_token_usage_sessions(days: int = 7, top: int = 20) -> list[dict[str, Any]]:
    """Возвращает топ сессий по расходу токенов/стоимости за период."""
    init_db()
    safe_days = max(1, int(days))
    safe_top = max(1, int(top))
    since = (datetime.now() - timedelta(days=safe_days)).isoformat(timespec="seconds")

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                session_id,
                MIN(conversation_key) AS conversation_key,
                MIN(timestamp) AS first_timestamp,
                MAX(timestamp) AS last_timestamp,
                COUNT(*) AS llm_calls,
                SUM(prompt_tokens) AS prompt_tokens,
                SUM(completion_tokens) AS completion_tokens,
                SUM(total_tokens) AS total_tokens,
                SUM(cost_usd) AS cost_usd,
                GROUP_CONCAT(DISTINCT model) AS models
            FROM token_usage_calls
            WHERE timestamp >= ?
            GROUP BY session_id
            ORDER BY cost_usd DESC, total_tokens DESC, llm_calls DESC
            LIMIT ?
            """,
            (since, safe_top),
        ).fetchall()

    sessions: list[dict[str, Any]] = []
    for row in rows:
        item = _row_to_dict(row)
        models = item.get("models") or ""
        item["models"] = [m for m in str(models).split(",") if m]
        sessions.append(item)

    return sessions


def get_token_usage_session_details(session_id: str) -> dict[str, Any] | None:
    """Возвращает подробные usage-данные по session_id."""
    init_db()

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                request_id,
                conversation_key,
                timestamp,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                cost_usd,
                iteration
            FROM token_usage_calls
            WHERE session_id = ?
            ORDER BY timestamp ASC, id ASC
            """,
            (session_id,),
        ).fetchall()

    if not rows:
        return None

    calls = [_row_to_dict(row) for row in rows]
    by_model: dict[str, dict[str, Any]] = {}
    conversation_key = ""

    for call in calls:
        model = call.get("model", "")
        if not conversation_key and call.get("conversation_key"):
            conversation_key = str(call.get("conversation_key"))

        slot = by_model.setdefault(
            model,
            {
                "model": model,
                "llm_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
            },
        )
        slot["llm_calls"] += 1
        slot["prompt_tokens"] += int(call.get("prompt_tokens", 0) or 0)
        slot["completion_tokens"] += int(call.get("completion_tokens", 0) or 0)
        slot["total_tokens"] += int(call.get("total_tokens", 0) or 0)
        slot["cost_usd"] += float(call.get("cost_usd", 0.0) or 0.0)

    return {
        "session_id": session_id,
        "conversation_key": conversation_key or None,
        "first_timestamp": calls[0].get("timestamp", ""),
        "last_timestamp": calls[-1].get("timestamp", ""),
        "llm_calls": len(calls),
        "prompt_tokens": sum(int(c.get("prompt_tokens", 0) or 0) for c in calls),
        "completion_tokens": sum(int(c.get("completion_tokens", 0) or 0) for c in calls),
        "total_tokens": sum(int(c.get("total_tokens", 0) or 0) for c in calls),
        "cost_usd": sum(float(c.get("cost_usd", 0.0) or 0.0) for c in calls),
        "by_model": sorted(
            by_model.values(),
            key=lambda item: (float(item["cost_usd"]), int(item["total_tokens"])),
            reverse=True,
        ),
        "calls": calls,
    }
