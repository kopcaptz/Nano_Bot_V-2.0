"""Единый менеджер ChromaDB для векторного поиска в проекте."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger


class VectorDBManager:
    """
    Единая точка доступа к ChromaDB.

    Использует Singleton-паттерн для клиента и embedding-функции на уровне класса,
    чтобы избежать повторной загрузки тяжёлых ресурсов.
    """

    _client: Any | None = None
    _embedding_fn: Any | None = None
    _embedding_ready: bool = False

    def __init__(
        self,
        db_path: Path,
        model_name: str = "all-MiniLM-L6-v2",
    ) -> None:
        """
        Инициализация менеджера.

        Args:
            db_path: Путь к директории хранилища ChromaDB.
            model_name: Имя модели для embedding (по умолчанию multilingual).
        """
        self.db_path = Path(db_path)
        self.model_name = model_name

    def get_client(self) -> Any:
        """
        Возвращает persistent-клиент ChromaDB.

        Создаёт клиент при первом вызове, далее возвращает тот же экземпляр.

        Returns:
            ChromaDB PersistentClient.
        """
        if VectorDBManager._client is not None:
            return VectorDBManager._client

        try:
            import chromadb
        except Exception as exc:
            logger.error("ChromaDB недоступен: {}", exc)
            raise RuntimeError("ChromaDB недоступен в текущем окружении") from exc

        self.db_path.mkdir(parents=True, exist_ok=True)
        VectorDBManager._client = chromadb.PersistentClient(path=str(self.db_path))
        logger.info("ChromaDB client инициализирован: {}", self.db_path)
        return VectorDBManager._client

    def _get_embedding_function(self) -> Any | None:
        """
        Возвращает embedding-функцию для коллекции.

        Пытается загрузить SentenceTransformer. При ошибке возвращает None —
        ChromaDB использует встроенный default.
        """
        if VectorDBManager._embedding_ready:
            return VectorDBManager._embedding_fn

        VectorDBManager._embedding_ready = True
        try:
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction,
            )

            VectorDBManager._embedding_fn = SentenceTransformerEmbeddingFunction(
                model_name=self.model_name
            )
            logger.info("Embedding модель загружена: {}", self.model_name)
        except Exception as e:
            VectorDBManager._embedding_fn = None
            logger.warning(
                "Не удалось загрузить SentenceTransformer ({}): {}. Используем ChromaDB default.",
                self.model_name,
                e,
            )

        return VectorDBManager._embedding_fn

    def get_collection(self, name: str) -> Any:
        """
        Возвращает или создаёт коллекцию ChromaDB.

        Args:
            name: Имя коллекции.

        Returns:
            Collection ChromaDB с метаданными hnsw:space=cosine.
        """
        client = self.get_client()
        embedding_fn = self._get_embedding_function()

        kwargs: dict[str, Any] = {
            "name": name,
            "metadata": {"hnsw:space": "cosine"},
        }
        if embedding_fn is not None:
            kwargs["embedding_function"] = embedding_fn

        collection = client.get_or_create_collection(**kwargs)
        logger.debug("Коллекция получена/создана: {}", name)
        return collection
