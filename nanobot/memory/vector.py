"""Векторная память на базе ChromaDB."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nanobot.memory.vector_manager import VectorDBManager

# Путь к постоянному хранилищу ChromaDB: ~/.nanobot/chroma/
VECTOR_DB_PATH = Path.home() / ".nanobot" / "chroma"
COLLECTION_NAME = "nanobot_facts"

_manager = VectorDBManager(db_path=VECTOR_DB_PATH)
_COLLECTION: Any | None = None


def _normalize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Приводит metadata к формату, совместимому с ChromaDB."""
    if not metadata:
        return {}

    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            clean[str(key)] = value
        else:
            clean[str(key)] = str(value)
    return clean


def init_vector_db() -> Any:
    """Создает (или открывает) коллекцию векторной памяти."""
    global _COLLECTION
    if _COLLECTION is not None:
        return _COLLECTION

    _COLLECTION = _manager.get_collection(COLLECTION_NAME)
    return _COLLECTION


def add_memory(
    memory_id: str, text: str, metadata: dict[str, Any] | None = None
) -> None:
    """Добавляет или обновляет запись в векторной памяти."""
    if not text or not text.strip():
        return

    collection = init_vector_db()
    safe_metadata = _normalize_metadata(metadata)

    if safe_metadata:
        collection.upsert(
            ids=[str(memory_id)],
            documents=[text],
            metadatas=[safe_metadata],
        )
    else:
        collection.upsert(
            ids=[str(memory_id)],
            documents=[text],
        )


def delete_memory(memory_id: str) -> None:
    """Удаляет запись из векторной памяти по id."""
    collection = init_vector_db()
    collection.delete(ids=[str(memory_id)])


def search_similar(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Выполняет семантический поиск по смыслу."""
    if not query or not query.strip():
        return []

    collection = init_vector_db()
    n_results = max(1, int(limit))
    raw = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["metadatas", "documents", "distances"],
    )

    ids = (raw.get("ids") or [[]])[0]
    docs = (raw.get("documents") or [[]])[0]
    metas = (raw.get("metadatas") or [[]])[0]
    dists = (raw.get("distances") or [[]])[0]

    results: list[dict[str, Any]] = []
    for idx, item_id in enumerate(ids):
        results.append(
            {
                "id": item_id,
                "text": docs[idx] if idx < len(docs) else "",
                "metadata": metas[idx] if idx < len(metas) and metas[idx] else {},
                "distance": dists[idx] if idx < len(dists) else None,
            }
        )
    return results
