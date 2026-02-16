# Nanobot Memory

SQLite (`~/.nanobot/memory.db`) — факты/журнал/диалоги/рефлексии/токены.
ChromaDB (`~/.nanobot/chroma/`) — векторный поиск, `all-MiniLM-L6-v2` 384d cosine, коллекция `nanobot_memory`, id=`fact::{cat}::{key}`.
Markdown (`~/.nanobot/workspace/memory/`) — MEMORY.md + YYYY-MM-DD.md.
JSONL (`~/.nanobot/sessions/`) — история чатов.

Deps: `pydantic`, `loguru`, `litellm`; динамически: `chromadb`, `sentence-transformers`.

Save: message -> LLM crystallize -> JSON facts -> SQLite UPSERT + ChromaDB upsert.
Load: message -> `semantic_search()` -> ChromaDB query -> distance<0.7 -> inject system msg.
Search: `memory_search` tool -> domain/category -> SQLite | free query -> ChromaDB.
