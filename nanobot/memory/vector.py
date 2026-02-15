"""Векторная память на базе ChromaDB."""

from __future__ import annotations

from pathlib import Path
from typing import Any


# Путь к постоянному хранилищу ChromaDB: ~/.nanobot/chroma/
VECTOR_DB_PATH = Path.home() / ".nanobot" / "chroma"
COLLECTION_NAME = "nanobot_memory"

_CLIENT: Any | None = None
_COLLECTION: Any | None = None
_EMBEDDING_FN: Any | None = None
_EMBEDDING_READY = False


def _get_client() -> Any:
    """Возвращает persistent-клиент ChromaDB."""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    try:
        import chromadb
    except Exception as exc:  # pragma: no cover - зависит от окружения
        raise RuntimeError("ChromaDB недоступен в текущем окружении") from exc

    VECTOR_DB_PATH.mkdir(parents=True, exist_ok=True)
    _CLIENT = chromadb.PersistentClient(path=str(VECTOR_DB_PATH))
    return _CLIENT


def _get_embedding_function() -> Any | None:
    """
    Возвращает embedding-функцию для коллекции.

    Предпочитаем all-MiniLM-L6-v2 (качественный и легкий вариант).
    Если модель/зависимости недоступны, Chroma использует встроенный default.
    """
    global _EMBEDDING_FN, _EMBEDDING_READY
    if _EMBEDDING_READY:
        return _EMBEDDING_FN

    _EMBEDDING_READY = True
    try:
        from chromadb.utils.embedding_functions import (
            SentenceTransformerEmbeddingFunction,
        )

        _EMBEDDING_FN = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    except Exception:
        _EMBEDDING_FN = None
    return _EMBEDDING_FN


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

    client = _get_client()
    embedding_fn = _get_embedding_function()

    # Если embedding-функция не поднялась, используем встроенный default Chroma.
    if embedding_fn is not None:
        _COLLECTION = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
            embedding_function=embedding_fn,
        )
    else:
        _COLLECTION = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _COLLECTION


def add_memory(memory_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
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
