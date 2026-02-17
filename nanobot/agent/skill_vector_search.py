"""Векторный поиск навыков на базе ChromaDB через VectorDBManager."""

from __future__ import annotations

from typing import Any

from loguru import logger

from nanobot.memory.vector_manager import VectorDBManager

COLLECTION_NAME = "nanobot_skills"


def _normalize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Приводит metadata к формату ChromaDB (только str/int/float/bool)."""
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


class SkillVectorSearch:
    """
    Семантический поиск навыков на базе ChromaDB.

    Использует VectorDBManager для единообразного доступа к ChromaDB.
    Коллекция: nanobot_skills.
    """

    def __init__(self, db_manager: VectorDBManager) -> None:
        """
        Инициализация поиска навыков.

        Args:
            db_manager: Менеджер ChromaDB (единая точка доступа).
        """
        self.db_manager = db_manager
        self._collection = None

    def _get_collection(self):
        """Возвращает коллекцию навыков (lazy)."""
        if self._collection is None:
            self._collection = self.db_manager.get_collection(COLLECTION_NAME)
        return self._collection

    @property
    def _skill_mapping(self) -> dict[str, str]:
        """
        Совместимость с SkillManager._sync_vector_index.

        Возвращает словарь id->name (в ChromaDB id=skill_name).
        """
        try:
            data = self._get_collection().get(include=[])
            ids = data.get("ids") or []
            return {sid: sid for sid in ids}
        except Exception as e:
            logger.warning("Не удалось получить список навыков из индекса: {}", e)
            return {}

    def add_skill(
        self,
        skill_name: str,
        content: str,
        skill_type: str = "basic",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Добавить или обновить навык в индексе.

        Args:
            skill_name: Уникальное имя навыка (id в ChromaDB).
            content: Контент навыка для embedding.
            skill_type: Тип навыка (basic/composite/meta).
            metadata: Дополнительные метаданные (опционально).
        """
        meta = metadata or {}
        meta["skill_type"] = skill_type
        safe_meta = _normalize_metadata(meta)

        collection = self._get_collection()
        collection.upsert(
            ids=[str(skill_name)],
            documents=[content],
            metadatas=[safe_meta],
        )
        logger.debug("Навык '{}' добавлен в индекс", skill_name)

    def remove_skill(self, skill_name: str) -> bool:
        """
        Удалить навык из индекса.

        Args:
            skill_name: Имя навыка.

        Returns:
            True если удалён успешно.
        """
        try:
            collection = self._get_collection()
            collection.delete(ids=[str(skill_name)])
            logger.info("Навык '{}' удалён из индекса", skill_name)
            return True
        except Exception as e:
            logger.error("Ошибка удаления навыка '{}': {}", skill_name, e)
            return False

    def search(
        self,
        query: str,
        limit: int = 5,
        skill_type: str | None = None,
        where_filter: dict | None = None,
    ) -> list[dict[str, Any]]:
        """
        Семантический поиск навыков.

        Args:
            query: Поисковый запрос (естественный язык).
            limit: Максимальное число результатов.
            skill_type: Фильтр по типу навыка (опционально).
            where_filter: Дополнительный ChromaDB where-фильтр.

        Returns:
            Список dict с полями: skill_name, score, distance, rank.
        """
        if not query or not query.strip():
            return []

        where = where_filter or {}
        if skill_type:
            where["skill_type"] = skill_type

        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": max(1, limit),
            "include": ["metadatas", "documents", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            collection = self._get_collection()
            raw = collection.query(**kwargs)

            ids = (raw.get("ids") or [[]])[0]
            dists = (raw.get("distances") or [[]])[0]

            results = []
            for idx, skill_id in enumerate(ids):
                distance = dists[idx] if idx < len(dists) else 0.0
                score = 1.0 - float(distance)
                results.append({
                    "skill_name": skill_id,
                    "score": score,
                    "distance": float(distance),
                    "rank": idx + 1,
                })
            return results
        except Exception as e:
            logger.error("Ошибка поиска навыков: {}", e)
            return []

    def hierarchical_search(
        self,
        query: str,
        max_per_level: int = 3,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Иерархический поиск по уровням навыков.

        Args:
            query: Поисковый запрос.
            max_per_level: Макс. результатов на уровень.

        Returns:
            Dict с ключами meta, composite, basic.
        """
        meta_results = self.search(query, limit=max_per_level, skill_type="meta")
        composite_results = self.search(query, limit=max_per_level, skill_type="composite")
        basic_results = self.search(query, limit=max_per_level, skill_type="basic")

        return {
            "meta": meta_results,
            "composite": composite_results,
            "basic": basic_results,
        }

    def rebuild_index(
        self,
        skills: list[tuple[str, str] | tuple[str, str, dict[str, Any]]],
    ) -> None:
        """
        Полная пересборка индекса.

        Args:
            skills: Список кортежей (skill_name, content) или (skill_name, content, metadata).
        """
        logger.info("Пересборка индекса навыков: {} записей", len(skills))

        collection = self._get_collection()

        # Удалить все записи
        try:
            existing = collection.get(include=[])
            ids_to_delete = existing.get("ids") or []
            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
                logger.debug("Удалено {} записей", len(ids_to_delete))
        except Exception as e:
            logger.warning("Ошибка при очистке коллекции: {}", e)

        # Добавить заново
        if not skills:
            logger.info("Индекс пересобран (пусто)")
            return

        ids_list = []
        documents_list = []
        metadatas_list = []

        for item in skills:
            if len(item) == 2:
                skill_name, content = item
                metadata = {}
            else:
                skill_name, content, metadata = item
            safe_meta = _normalize_metadata(metadata)
            if "skill_type" not in safe_meta:
                safe_meta["skill_type"] = "basic"
            ids_list.append(str(skill_name))
            documents_list.append(content)
            metadatas_list.append(safe_meta)

        collection.add(
            ids=ids_list,
            documents=documents_list,
            metadatas=metadatas_list,
        )
        logger.info("Индекс пересобран: {} навыков", len(skills))

    def save(self) -> None:
        """
        Сохранение индекса.

        ChromaDB сохраняет данные автоматически, метод оставлен для совместимости.
        """
        pass

    def get_by_filter(self, where: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Получить навыки по фильтру metadata.

        Args:
            where: ChromaDB where-фильтр (например {"always_load": True}).

        Returns:
            Список dict с skill_name, content, metadata.
        """
        try:
            collection = self._get_collection()
            raw = collection.get(where=where, include=["metadatas", "documents"])
            ids = raw.get("ids") or []
            docs = raw.get("documents") or []
            metas = raw.get("metadatas") or []
            results = []
            for idx, skill_id in enumerate(ids):
                results.append({
                    "skill_name": skill_id,
                    "content": docs[idx] if idx < len(docs) else "",
                    "metadata": metas[idx] if idx < len(metas) and metas[idx] else {},
                })
            return results
        except Exception as e:
            logger.error("Ошибка get_by_filter: {}", e)
            return []

    def get_stats(self) -> dict[str, Any]:
        """
        Статистика индекса навыков.

        Returns:
            Dict с total_skills и collection.
        """
        try:
            count = self._get_collection().count()
            return {
                "total_skills": count,
                "collection": COLLECTION_NAME,
                "backend": "chromadb",
            }
        except Exception as e:
            logger.warning("Ошибка получения статистики: {}", e)
            return {
                "total_skills": 0,
                "collection": COLLECTION_NAME,
                "backend": "chromadb",
            }
