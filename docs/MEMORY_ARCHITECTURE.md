# Nanobot — Архитектура персистентной памяти

## Файлы

```
nanobot/memory/
  __init__.py      — публичный API
  db.py            — SQLite: facts, journal, conversations, reflections, token_usage
  vector.py        — ChromaDB: семантический поиск
  crystallize.py   — извлечение фактов из диалогов через LLM

nanobot/agent/memory.py        — файловая память (MEMORY.md + YYYY-MM-DD.md)
nanobot/agent/context.py       — сборка промпта + авто-обогащение из векторов
nanobot/agent/tools/memory.py  — инструмент memory_search для агента
nanobot/session/manager.py     — JSONL-сессии
src/core/memory.py             — in-memory буфер (legacy)
```

## Слои хранения

| Слой | Движок | Путь |
|------|--------|------|
| Структурированные факты | SQLite | `~/.nanobot/memory.db` |
| Векторный индекс | ChromaDB PersistentClient | `~/.nanobot/chroma/` |
| Файловая память | Markdown | `~/.nanobot/workspace/memory/` |
| История сессий | JSONL | `~/.nanobot/sessions/` |
| Оперативный буфер | Python dict | RAM |

## Векторы

- Модель: `all-MiniLM-L6-v2` (384 dim, float32)
- Метрика: cosine (`hnsw:space: cosine`)
- Коллекция: `nanobot_memory`
- ID записи: `fact::{category}::{key}`
- Metadata: type, category, key, value, domain, sub_category, updated_at
- Fallback: если SentenceTransformers нет — встроенный embedder ChromaDB

## Зависимости

В pyproject.toml: `pydantic`, `pydantic-settings`, `loguru`, `litellm`
Динамический импорт: `chromadb`, `sentence-transformers` (опционально)

## Потоки данных

**Сохранение факта:**
message -> `crystallize_memories()` -> LLM -> JSON -> `add_fact()` -> SQLite UPSERT + ChromaDB upsert

**Загрузка факта:**
message -> `ContextBuilder.build_messages()` -> `semantic_search()` -> ChromaDB query -> фильтр distance < 0.7 -> system-сообщение с релевантными фактами

**Ручной поиск (агент):**
`memory_search` tool -> с domain/category -> `get_facts_filtered()` (SQLite) | без фильтра -> `semantic_search()` (ChromaDB)

**Сессия:**
`SessionManager.get_or_create()` -> load JSONL -> `add_message()` -> `save()` -> write JSONL
