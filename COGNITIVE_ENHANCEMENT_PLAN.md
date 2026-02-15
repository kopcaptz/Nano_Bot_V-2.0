# План Когнитивного Улучшения Nano Bot V-2.0

**Автор**: Manus (Стратег и Архитектор)
**Дата**: 15.02.2026
**Версия**: 1.0
**Статус**: Ожидает одобрения Г.Вагуса

---

## Оглавление

1. [Введение](#введение)
2. [Сводная таблица этапов и подэтапов](#сводная-таблица)
3. [Этап 1: Рефлексия](#этап-1-рефлексия)
4. [Этап 2: Иерархическая Память](#этап-2-иерархическая-память-h-mem)
5. [Этап 3: Автономия и Самообучение](#этап-3-автономия-и-самообучение)
6. [Этап 4: Дополнительные Улучшения](#этап-4-дополнительные-улучшения-и-завершение)
7. [Порядок выполнения и зависимости](#порядок-выполнения-и-зависимости)

---

## Введение

Этот документ представляет собой детальную техническую дорожную карту по трансформации **Nano Bot V-2.0** из реактивного исполнителя команд в автономного, самообучающегося и рефлексирующего когнитивного агента. План основан на результатах глубокого исследования архитектур когнитивных агентов и адаптирован под текущую кодовую базу проекта.

Каждый этап разбит на подэтапы, и для каждого подэтапа подготовлен **готовый промт для Cursor** — разработчика, который будет реализовывать код. Промты написаны с учётом актуальной структуры файлов, интерфейсов и паттернов проекта.

**Принципы разработки:**

- Каждый подэтап — это атомарная, тестируемая единица работы.
- Обратная совместимость: новый код не должен ломать существующую функциональность.
- Промты для Cursor содержат точные пути к файлам, имена классов и сигнатуры методов.

---

## Сводная таблица

| Этап | Подэтап | Название | Файлы | Приоритет |
|------|---------|----------|-------|-----------|
| 1 | 1.1 | Модуль Рефлексии | `nanobot/agent/reflection.py` (новый) | Высокий |
| 1 | 1.2 | Интеграция Рефлексии в AgentLoop | `nanobot/agent/loop.py` | Высокий |
| 1 | 1.3 | Логирование рефлексий в память | `nanobot/agent/reflection.py`, `nanobot/memory/db.py` | Средний |
| 1 | 1.4 | Тесты для Рефлексии | `tests/test_reflection.py` (новый) | Высокий |
| 2 | 2.1 | Миграция схемы БД | `nanobot/memory/db.py`, `nanobot/memory/migrate.py` (новый) | Высокий |
| 2 | 2.2 | Обновление кристаллизации | `nanobot/memory/crystallize.py` | Высокий |
| 2 | 2.3 | Инструмент `memory_search` | `nanobot/agent/tools/memory.py` (новый), `nanobot/agent/loop.py` | Высокий |
| 2 | 2.4 | Автоматическое извлечение контекста | `nanobot/agent/context.py` | Средний |
| 2 | 2.5 | Тесты для H-MEM | `tests/test_hmem.py` (новый) | Высокий |
| 3 | 3.1 | Генератор навыков | `nanobot/agent/skill_generator.py` (новый) | Средний |
| 3 | 3.2 | Инструмент `create_skill` | `nanobot/agent/tools/skill.py` (новый), `nanobot/agent/loop.py` | Средний |
| 3 | 3.3 | Автоматическое предложение навыков | `nanobot/agent/loop.py` | Низкий |
| 3 | 3.4 | Тесты для генерации навыков | `tests/test_skill_generator.py` (новый) | Средний |
| 4 | 4.1 | Механизм подтверждения (ToolPolicy FSM) | `nanobot/agent/tools/base.py`, `nanobot/agent/tools/registry.py`, `nanobot/session/manager.py`, `nanobot/agent/loop.py` | Критический |
| 4 | 4.2 | Улучшение Heartbeat | `nanobot/heartbeat/service.py` | Средний |
| 4 | 4.3 | Метрики и наблюдаемость | `nanobot/agent/metrics.py` (новый) | Низкий |

---

## Этап 1: Рефлексия

**Цель**: Научить агента анализировать свои ошибки (неудачные вызовы инструментов), понимать их причину и корректировать своё поведение. Это основа для самосовершенствования — цикл «Решение → Анализ → Коррекция».

**Архитектурная идея**: Когда инструмент возвращает ошибку, вместо того чтобы слепо передать её LLM и надеяться на лучшее, мы запускаем отдельный, изолированный LLM-вызов, который анализирует всю траекторию (историю сообщений + неудавшийся вызов + ошибку) и генерирует краткий, действенный вывод. Этот вывод инъецируется обратно в контекст основного агента, направляя его к правильному решению.

---

### Подэтап 1.1: Создание Модуля Рефлексии

**Что делаем**: Создаём изолированный модуль, отвечающий за анализ ошибок и генерацию корректирующих выводов.

**Промпт для Cursor №1:**

```
Задача: Создать модуль Reflection

Создай новый файл nanobot/agent/reflection.py со следующим содержимым.

Класс Reflection отвечает за анализ неудачных вызовов инструментов. Он использует отдельный LLM-вызов (через существующий LLMProvider) для генерации краткого вывода о причине ошибки и предложения по исправлению.

Требования:

1. Файл: nanobot/agent/reflection.py

2. Импорты: 
   - json, from typing import Any
   - from loguru import logger
   - from nanobot.providers.base import LLMProvider

3. Константа REFLECTION_SYSTEM_PROMPT — системный промт для LLM-рефлексии:

REFLECTION_SYSTEM_PROMPT = """You are a Self-Correction module for an AI agent called nanobot.
Your task: analyze a failed tool call and provide a concise, actionable insight.

Rules:
1. Identify the ROOT CAUSE: wrong parameter? wrong assumption? wrong tool? missing prerequisite step?
2. Propose a SPECIFIC fix: suggest a corrected tool call or an alternative approach.
3. Be CONCISE: one paragraph, starting with "Reflection: ...".
4. Do NOT repeat the error message. Focus on the solution.

Example:
Reflection: The read_file tool failed because the path "config.yaml" is relative. The workspace is at C:/Users/kopca/Nano_Bot_V2/workspace/, so the correct path should be "C:/Users/kopca/Nano_Bot_V2/workspace/config.yaml". I should use list_dir first to verify the file exists."""

4. Класс Reflection:
   - __init__(self, provider: LLMProvider, model: str): сохраняет provider и model.
   - async def analyze_trajectory(self, messages: list[dict[str, Any]], failed_tool_call: dict[str, Any], error_result: str) -> str | None:
     a. Формирует user-промт с информацией о последних 5 сообщениях из messages (чтобы не раздувать контекст), имени инструмента, его аргументах и тексте ошибки.
     b. Вызывает self.provider.chat() с REFLECTION_SYSTEM_PROMPT и сформированным user-промтом.
     c. Использует temperature=0.3 и max_tokens=500 для точности.
     d. Возвращает response.content или None при ошибке.
     e. Оборачивает весь вызов в try/except, логирует ошибки через logger.warning.

5. Метод _format_user_prompt(self, messages, failed_tool_call, error_result) -> str:
   - Берёт последние 5 сообщений из messages и форматирует их в читаемый текст.
   - Добавляет информацию о неудавшемся вызове: tool name, arguments (JSON).
   - Добавляет текст ошибки.
   - Возвращает отформатированную строку.

Не добавляй никаких инструментов (tools) в вызов provider.chat() — рефлексия должна быть чисто текстовой.
```

---

### Подэтап 1.2: Интеграция Рефлексии в AgentLoop

**Что делаем**: Встраиваем механизм рефлексии в главный цикл агента. При ошибке инструмента автоматически запускается анализ, и его результат добавляется в контекст для следующей итерации LLM.

**Промпт для Cursor №2:**

```
Задача: Интегрировать Reflection в AgentLoop

Открой файл nanobot/agent/loop.py и внеси следующие изменения.

1. Добавь импорт в начало файла:
   from nanobot.agent.reflection import Reflection

2. В конструкторе AgentLoop.__init__, после строки self.tools = ToolRegistry(), добавь:
   self.reflection = Reflection(provider=provider, model=self.model)

3. Модифицируй метод _process_message. Найди блок:

   for tool_call in response.tool_calls:
       args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
       logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
       result = await self.tools.execute(tool_call.name, tool_call.arguments)
       messages = self.context.add_tool_result(
           messages, tool_call.id, tool_call.name, result
       )

   Замени его на:

   for tool_call in response.tool_calls:
       args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
       logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
       result = await self.tools.execute(tool_call.name, tool_call.arguments)
       
       # Рефлексия при ошибке инструмента
       if result.startswith("Error:"):
           logger.warning(f"Tool {tool_call.name} failed: {result[:200]}")
           try:
               failed_info = {
                   "name": tool_call.name,
                   "arguments": tool_call.arguments
               }
               insight = await self.reflection.analyze_trajectory(
                   messages=messages,
                   failed_tool_call=failed_info,
                   error_result=result
               )
               if insight:
                   logger.info(f"Reflection: {insight[:200]}")
           except Exception as e:
               logger.warning(f"Reflection failed: {e}")
       
       messages = self.context.add_tool_result(
           messages, tool_call.id, tool_call.name, result
       )

4. Сделай аналогичное изменение в методе _process_system_message — там есть такой же цикл обработки инструментов.

Важно: НЕ добавляй insight как отдельное assistant-сообщение. LLM уже получит ошибку через tool_result. Insight будет залогирован и сохранён в память (следующий подэтап). LLM сам увидит ошибку и скорректирует поведение, а insight поможет при анализе логов.
```

---

### Подэтап 1.3: Логирование Рефлексий в Память

**Что делаем**: Сохраняем все рефлексии в SQLite для последующего анализа и обучения. Это создаёт «журнал ошибок», который агент может использовать для предотвращения повторных ошибок.

**Промпт для Cursor №3:**

```
Задача: Сохранять рефлексии в базу данных

1. Открой nanobot/memory/db.py.

2. Добавь новую таблицу reflections в функцию init_db():

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
   conn.execute(
       "CREATE INDEX IF NOT EXISTS idx_reflections_tool ON reflections(tool_name)"
   )

3. Добавь функцию add_reflection():

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

4. Добавь функцию get_recent_reflections():

   def get_recent_reflections(tool_name: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
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

5. Открой nanobot/agent/loop.py.

6. Добавь импорт: from nanobot.memory.db import add_reflection

7. В _process_message, после строки logger.info(f"Reflection: {insight[:200]}"), добавь:
   
   add_reflection(
       tool_name=tool_call.name,
       tool_args=args_str[:500],
       error_text=result[:500],
       insight=insight[:1000],
       session_key=msg.session_key,
   )
```

---

### Подэтап 1.4: Тесты для Модуля Рефлексии

**Что делаем**: Создаём unit-тесты для проверки работоспособности модуля рефлексии.

**Промпт для Cursor №4:**

```
Задача: Написать тесты для модуля Reflection

Создай файл tests/test_reflection.py.

Тесты должны использовать pytest и unittest.mock для мокирования LLMProvider.

1. test_analyze_trajectory_returns_insight:
   - Мокируй LLMProvider.chat() так, чтобы он возвращал LLMResponse с content="Reflection: The file path was wrong."
   - Вызови reflection.analyze_trajectory() с тестовыми данными.
   - Проверь, что результат содержит "Reflection:".

2. test_analyze_trajectory_handles_llm_error:
   - Мокируй LLMProvider.chat() так, чтобы он выбрасывал Exception.
   - Проверь, что analyze_trajectory() возвращает None и не падает.

3. test_format_user_prompt_limits_history:
   - Передай messages с 20 элементами.
   - Проверь, что _format_user_prompt использует только последние 5.

4. test_add_reflection_to_db:
   - Вызови add_reflection() с тестовыми данными.
   - Вызови get_recent_reflections() и проверь, что запись сохранена.

Используй фикстуру tmp_path для изоляции БД (переопредели DB_PATH через monkeypatch).
```

---

## Этап 2: Иерархическая Память (H-MEM)

**Цель**: Реструктурировать память агента, перейдя от плоского списка фактов к иерархической структуре **Domain → Category → Sub-Category → Key/Value**. Это позволит более эффективно и контекстуально извлекать информацию, улучшая релевантность ответов и снижая «засорение» контекста нерелевантными фактами.

**Архитектурная идея**: Вместо того чтобы хранить все факты в одной плоской коллекции, мы добавляем два уровня иерархии: `domain` (широкая область, например, «Проект: Nano Bot» или «Предпочтения пользователя») и `sub_category` (детализация внутри категории). Это позволяет агенту при поиске фактов сужать область поиска, что критически важно при росте объёма памяти.

---

### Подэтап 2.1: Миграция Схемы Базы Данных

**Что делаем**: Расширяем таблицу `facts` новыми полями и создаём механизм миграции для существующих данных.

**Промпт для Cursor №5:**

```
Задача: Обновить схему БД с миграцией

1. Создай новый файл nanobot/memory/migrate.py.

   Этот файл будет содержать функции миграции БД. Нам нужна миграция для добавления полей domain и sub_category в таблицу facts.

   from pathlib import Path
   import sqlite3
   from loguru import logger
   from nanobot.memory.db import DB_PATH, _connect, init_db

   MIGRATIONS = [
       {
           "version": 1,
           "description": "Add domain and sub_category to facts",
           "sql": [
               "ALTER TABLE facts ADD COLUMN domain TEXT DEFAULT NULL",
               "ALTER TABLE facts ADD COLUMN sub_category TEXT DEFAULT NULL",
           ]
       },
   ]

   def get_db_version() -> int:
       """Получает текущую версию схемы БД."""
       try:
           with _connect() as conn:
               conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
               row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
               return row[0] if row and row[0] else 0
       except Exception:
           return 0

   def run_migrations() -> None:
       """Применяет все непримененные миграции."""
       init_db()  # Убедимся, что базовые таблицы существуют
       current = get_db_version()
       
       for migration in MIGRATIONS:
           if migration["version"] <= current:
               continue
           
           logger.info(f"Running migration v{migration['version']}: {migration['description']}")
           try:
               with _connect() as conn:
                   for sql in migration["sql"]:
                       try:
                           conn.execute(sql)
                       except sqlite3.OperationalError as e:
                           if "duplicate column" in str(e).lower():
                               logger.debug(f"Column already exists, skipping: {sql}")
                           else:
                               raise
                   conn.execute("INSERT INTO schema_version (version) VALUES (?)", (migration["version"],))
                   conn.commit()
               logger.info(f"Migration v{migration['version']} completed")
           except Exception as e:
               logger.error(f"Migration v{migration['version']} failed: {e}")
               raise

2. Открой nanobot/memory/db.py.

3. Обнови функцию add_fact — добавь параметры domain и sub_category:

   def add_fact(category: str, key: str, value: str, domain: str | None = None, sub_category: str | None = None) -> None:
       """Добавляет факт или обновляет значение."""
       init_db()
       now = _now_iso()
       with _connect() as conn:
           conn.execute(
               """
               INSERT INTO facts (domain, category, sub_category, key, value, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(category, key)
               DO UPDATE SET
                   value = excluded.value,
                   domain = COALESCE(excluded.domain, domain),
                   sub_category = COALESCE(excluded.sub_category, sub_category),
                   updated_at = excluded.updated_at
               """,
               (domain, category, sub_category, key, value, now, now),
           )
           conn.commit()
       
       # Синхронизируем в ChromaDB
       try:
           vid = _fact_vector_id(category, key)
           text = f"Domain: {domain or 'general'}\nCategory: {category}\nKey: {key}\nValue: {value}"
           add_vector_memory(
               memory_id=vid,
               text=text,
               metadata={
                   "type": "fact",
                   "domain": domain or "general",
                   "category": category,
                   "sub_category": sub_category or "",
                   "key": key,
                   "value": value,
                   "updated_at": now,
               },
           )
       except Exception as exc:
           logger.debug("Failed to sync fact into vector DB: %s", exc)

4. Добавь новые функции поиска:

   def get_facts_by_domain(domain: str) -> list[dict[str, Any]]:
       """Возвращает все факты указанного домена."""
       init_db()
       with _connect() as conn:
           rows = conn.execute(
               "SELECT * FROM facts WHERE domain = ? ORDER BY category, key",
               (domain,),
           ).fetchall()
       return [_row_to_dict(row) for row in rows]

   def get_facts_filtered(domain: str | None = None, category: str | None = None) -> list[dict[str, Any]]:
       """Возвращает факты с фильтрацией по domain и/или category."""
       init_db()
       conditions = []
       params = []
       if domain:
           conditions.append("domain = ?")
           params.append(domain)
       if category:
           conditions.append("category = ?")
           params.append(category)
       
       where = " AND ".join(conditions) if conditions else "1=1"
       with _connect() as conn:
           rows = conn.execute(
               f"SELECT * FROM facts WHERE {where} ORDER BY domain, category, key",
               params,
           ).fetchall()
       return [_row_to_dict(row) for row in rows]

5. Открой nanobot/__main__.py (или место, где происходит инициализация приложения).
   Добавь вызов run_migrations() при старте:
   
   from nanobot.memory.migrate import run_migrations
   run_migrations()

Важно: НЕ меняй UNIQUE constraint в CREATE TABLE, так как это сломает существующие БД. Миграция через ALTER TABLE ADD COLUMN безопасна для существующих данных.
```

---

### Подэтап 2.2: Обновление Процесса Кристаллизации

**Что делаем**: Учим LLM извлекать факты в новой иерархической структуре с полями `domain` и `sub_category`.

**Промпт для Cursor №6:**

```
Задача: Адаптировать кристаллизацию под иерархическую память

Открой файл nanobot/memory/crystallize.py.

1. Замени CRYSTALLIZE_PROMPT на новый:

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

2. Обнови функцию _normalize_facts:
   - Извлекай domain и sub_category из каждого элемента.
   - Ключ дедупликации: (domain, category, key) вместо (category, key, value).
   
   def _normalize_facts(raw_facts: list[dict[str, Any]]) -> list[dict[str, str]]:
       normalized: list[dict[str, str]] = []
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
           fact = {"domain": domain, "category": category, "key": key, "value": value}
           if sub_category:
               fact["sub_category"] = sub_category
           normalized.append(fact)
       return normalized

3. Обнови вызов add_fact в crystallize_memories:

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
```

---

### Подэтап 2.3: Создание Инструмента `memory_search`

**Что делаем**: Даём агенту возможность целенаправленно искать факты в своей структурированной памяти через новый инструмент.

**Промпт для Cursor №7:**

```
Задача: Создать инструмент MemorySearchTool

1. Создай файл nanobot/agent/tools/memory.py:

from typing import Any
from nanobot.agent.tools.base import Tool


class MemorySearchTool(Tool):
    """Tool for searching agent's hierarchical memory."""

    @property
    def name(self) -> str:
        return "memory_search"

    @property
    def description(self) -> str:
        return (
            "Search for facts in your memory. You can filter by domain, category, "
            "or perform a semantic search using a natural language query. "
            "Use this to recall user preferences, project details, or past decisions."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query for semantic search across all facts."
                },
                "domain": {
                    "type": "string",
                    "description": "Filter by domain (e.g., 'User Preferences', 'Project: Nano Bot')."
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (e.g., 'Architecture', 'Hobbies')."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default 10)."
                }
            }
        }

    async def execute(self, query: str | None = None, domain: str | None = None, category: str | None = None, limit: int = 10, **kwargs) -> str:
        from nanobot.memory.db import semantic_search, get_facts_filtered, search_facts

        results = []

        # Семантический поиск
        if query:
            try:
                hits = semantic_search(query, limit=limit)
                results.extend(hits)
            except Exception:
                # Fallback на текстовый поиск
                hits = search_facts(query)
                results.extend(hits[:limit])

        # Фильтрация по domain/category
        if domain or category:
            filtered = get_facts_filtered(domain=domain, category=category)
            # Добавляем только те, которых ещё нет
            existing_keys = {(r.get("category", ""), r.get("key", "")) for r in results}
            for f in filtered[:limit]:
                if (f.get("category", ""), f.get("key", "")) not in existing_keys:
                    results.append(f)

        if not query and not domain and not category:
            return "Error: At least one parameter (query, domain, or category) must be provided."

        if not results:
            return "No facts found matching your search criteria."

        # Форматирование результатов
        lines = [f"Found {len(results)} fact(s):\n"]
        for i, fact in enumerate(results[:limit], 1):
            d = fact.get("domain", "—")
            c = fact.get("category", "—")
            k = fact.get("key", "—")
            v = fact.get("value", "—")
            dist = fact.get("distance")
            line = f"{i}. [{d}] {c} → {k}: {v}"
            if dist is not None:
                line += f" (relevance: {1 - dist:.2f})"
            lines.append(line)

        return "\n".join(lines)

2. Открой nanobot/agent/loop.py.

3. Добавь импорт:
   from nanobot.agent.tools.memory import MemorySearchTool

4. В _register_default_tools, после регистрации WebFetchTool, добавь:
   self.tools.register(MemorySearchTool())
```

---

### Подэтап 2.4: Автоматическое Извлечение Контекста из Памяти

**Что делаем**: При каждом новом сообщении пользователя автоматически ищем релевантные факты в памяти и добавляем их в системный промт. Это делает агента «осведомлённым» о контексте без явного запроса.

**Промпт для Cursor №8:**

```
Задача: Автоматическое обогащение контекста фактами из памяти

Открой файл nanobot/agent/context.py.

1. Добавь импорт в начало файла:
   from nanobot.memory.db import semantic_search

2. Модифицируй метод build_messages. После строки:
   messages.append({"role": "system", "content": system_prompt})
   
   Добавь блок автоматического извлечения релевантных фактов:

   # Автоматическое обогащение контекста из памяти
   if current_message and len(current_message) > 10:  # Не ищем для коротких сообщений
       try:
           relevant_facts = semantic_search(current_message, limit=5)
           if relevant_facts:
               facts_text = "\n".join(
                   f"- [{f.get('domain', '?')}] {f.get('category', '?')} → {f.get('key', '?')}: {f.get('value', '?')}"
                   for f in relevant_facts
                   if f.get("distance", 1.0) < 0.7  # Только релевантные (cosine distance < 0.7)
               )
               if facts_text:
                   messages.append({
                       "role": "system",
                       "content": f"Relevant facts from your memory:\n{facts_text}"
                   })
       except Exception:
           pass  # Не ломаем основной поток при ошибке памяти

Важно: 
- Фильтруй по distance < 0.7 (cosine), чтобы не засорять контекст нерелевантными фактами.
- Оборачивай в try/except, чтобы ошибки ChromaDB не блокировали работу агента.
- Не ищи для коротких сообщений (менее 10 символов), чтобы не тратить ресурсы на "да", "ок" и т.п.
```

---

### Подэтап 2.5: Тесты для Иерархической Памяти

**Что делаем**: Создаём тесты для проверки миграции, новых функций поиска и инструмента `memory_search`.

**Промпт для Cursor №9:**

```
Задача: Написать тесты для иерархической памяти

Создай файл tests/test_hmem.py.

1. test_migration_adds_columns:
   - Создай тестовую БД с init_db().
   - Запусти run_migrations().
   - Проверь, что столбцы domain и sub_category существуют в таблице facts.

2. test_add_fact_with_domain:
   - Вызови add_fact(category="Arch", key="DB", value="SQLite", domain="Project: NanoBot", sub_category="Storage").
   - Вызови get_fact("Arch", "DB") и проверь, что все поля сохранены.

3. test_get_facts_filtered:
   - Добавь 5 фактов с разными domain и category.
   - Проверь, что get_facts_filtered(domain="X") возвращает только факты домена X.
   - Проверь, что get_facts_filtered(domain="X", category="Y") сужает выборку.

4. test_memory_search_tool_semantic:
   - Мокируй semantic_search, чтобы он возвращал тестовые данные.
   - Вызови MemorySearchTool().execute(query="test").
   - Проверь формат вывода.

5. test_memory_search_tool_no_params:
   - Вызови MemorySearchTool().execute() без параметров.
   - Проверь, что возвращается ошибка.

6. test_crystallize_with_hierarchy:
   - Мокируй LLMProvider.chat() так, чтобы он возвращал JSON с domain и sub_category.
   - Вызови crystallize_memories().
   - Проверь, что факты сохранены с правильными domain и sub_category.

Используй monkeypatch для переопределения DB_PATH на tmp_path / "test.db".
```

---

## Этап 3: Автономия и Самообучение

**Цель**: Дать агенту способность создавать новые навыки (skills) на основе успешных последовательностей действий. Это позволит ему «запоминать» удачные решения и переиспользовать их, ускоряя выполнение похожих задач в будущем.

**Архитектурная идея**: Когда агент успешно выполняет сложную задачу (например, «найти все большие файлы в проекте и создать отчёт»), он может проанализировать свою траекторию (последовательность tool_calls) и сгенерировать из неё обобщённую инструкцию — новый SKILL.md. В следующий раз, когда возникнет похожая задача, агент загрузит этот навык и выполнит задачу быстрее и точнее.

---

### Подэтап 3.1: Создание Генератора Навыков

**Что делаем**: Разрабатываем модуль, который анализирует историю сообщений и генерирует из неё новый файл SKILL.md.

**Промпт для Cursor №10:**

```
Задача: Создать модуль SkillGenerator

Создай файл nanobot/agent/skill_generator.py.

1. Импорты:
   import json
   from pathlib import Path
   from typing import Any
   from loguru import logger
   from nanobot.providers.base import LLMProvider

2. Константа SKILL_GENERATION_PROMPT:

SKILL_GENERATION_PROMPT = """Analyze the following successful tool call sequence from an AI agent session. Your task is to convert this into a generalized, reusable skill instruction.

**Tool Sequence:**
{tool_sequence}

**Instructions:**
1. Describe the overall GOAL of this sequence in one sentence.
2. Write a STEP-BY-STEP guide using the available tools (read_file, write_file, edit_file, list_dir, exec, web_search, web_fetch, memory_search).
3. GENERALIZE specific parameters: replace specific filenames with descriptions like "the target file", specific URLs with "the target URL", etc.
4. Include PREREQUISITES: what needs to be true before this skill can be used.
5. Include COMMON PITFALLS: based on any errors that occurred during the sequence.
6. Output clean, well-structured Markdown.

Example output:
## Goal
Find and analyze large files in a project directory.

## Prerequisites
- A project directory path must be known.

## Steps
1. Use `list_dir` to scan the project directory.
2. Use `exec` with `find . -size +10M` to locate large files.
3. For each large file, use `read_file` to check its content type.
4. Use `write_file` to create a summary report.

## Common Pitfalls
- The `find` command syntax differs between Windows and Linux. Use `dir` on Windows.
"""

3. Константа SKILL_TEMPLATE:

SKILL_TEMPLATE = '''---
description: "{description}"
---

# {name}

{body}
'''

4. Класс SkillGenerator:

class SkillGenerator:
    def __init__(self, skills_dir: Path, provider: LLMProvider, model: str):
        self.skills_dir = skills_dir
        self.provider = provider
        self.model = model

    def _extract_tool_sequence(self, messages: list[dict[str, Any]]) -> str:
        """Извлекает последовательность tool_calls из истории сообщений."""
        sequence_parts = []
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    name = func.get("name", "unknown")
                    args = func.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            pass
                    sequence_parts.append(f"Tool: {name}\nArguments: {json.dumps(args, indent=2, ensure_ascii=False)}")
            elif msg.get("role") == "tool":
                content = msg.get("content", "")
                # Сокращаем длинные результаты
                if len(content) > 200:
                    content = content[:200] + "..."
                is_error = content.startswith("Error:")
                status = "ERROR" if is_error else "OK"
                sequence_parts.append(f"Result ({status}): {content}")
        
        return "\n\n".join(sequence_parts) if sequence_parts else "No tool calls found."

    async def create_skill_from_trajectory(
        self,
        skill_name: str,
        skill_description: str,
        messages: list[dict[str, Any]],
    ) -> str:
        """Генерирует новый навык из истории сообщений."""
        tool_sequence = self._extract_tool_sequence(messages)
        
        if tool_sequence == "No tool calls found.":
            return "Error: No tool calls found in the conversation history."
        
        # Генерируем тело навыка через LLM
        prompt = SKILL_GENERATION_PROMPT.format(tool_sequence=tool_sequence)
        
        try:
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": "You are a technical writer. Generate clear, reusable skill documentation."},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.3,
                max_tokens=2000,
            )
            body = response.content or "No content generated."
        except Exception as e:
            logger.error(f"Skill generation LLM call failed: {e}")
            return f"Error: Failed to generate skill content: {e}"
        
        # Собираем SKILL.md
        skill_content = SKILL_TEMPLATE.format(
            name=skill_name,
            description=skill_description,
            body=body,
        )
        
        # Сохраняем файл
        skill_dir = self.skills_dir / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(skill_content, encoding="utf-8")
        
        logger.info(f"Skill '{skill_name}' created at {skill_file}")
        return f"Skill '{skill_name}' created successfully at {skill_file}"
```

---

### Подэтап 3.2: Создание Инструмента `create_skill`

**Что делаем**: Даём агенту возможность самому решать, когда создать новый навык, через инструмент.

**Промпт для Cursor №11:**

```
Задача: Создать инструмент CreateSkillTool

1. Создай файл nanobot/agent/tools/skill.py:

from typing import Any
from nanobot.agent.tools.base import Tool
from nanobot.agent.skill_generator import SkillGenerator
from nanobot.session.manager import SessionManager


class CreateSkillTool(Tool):
    """Tool for creating new skills from conversation history."""

    def __init__(self, skill_generator: SkillGenerator, session_manager: SessionManager):
        self._skill_generator = skill_generator
        self._session_manager = session_manager
        self._current_session_key: str | None = None

    def set_session_key(self, key: str) -> None:
        """Set the current session key for accessing conversation history."""
        self._current_session_key = key

    @property
    def name(self) -> str:
        return "create_skill"

    @property
    def description(self) -> str:
        return (
            "Create a new reusable skill from the current conversation. "
            "Use this when you have successfully completed a complex task "
            "and want to remember the approach for future use. "
            "The skill will be saved as a SKILL.md file."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "A descriptive snake_case name (e.g., 'analyze_project_structure')."
                },
                "skill_description": {
                    "type": "string",
                    "description": "A one-sentence description of what the skill does."
                }
            },
            "required": ["skill_name", "skill_description"]
        }

    async def execute(self, skill_name: str, skill_description: str, **kwargs) -> str:
        if not self._current_session_key:
            return "Error: No active session. Cannot access conversation history."
        
        session = self._session_manager.get_or_create(self._current_session_key)
        if not session.messages:
            return "Error: No messages in current session."
        
        return await self._skill_generator.create_skill_from_trajectory(
            skill_name=skill_name,
            skill_description=skill_description,
            messages=session.get_history(max_messages=100),
        )

2. Открой nanobot/agent/loop.py.

3. Добавь импорты:
   from nanobot.agent.skill_generator import SkillGenerator
   from nanobot.agent.tools.skill import CreateSkillTool

4. В AgentLoop.__init__, после создания self.skills (или self.context), добавь:
   self.skill_generator = SkillGenerator(
       skills_dir=self.workspace / "skills",
       provider=provider,
       model=self.model,
   )

5. В _register_default_tools, добавь:
   create_skill_tool = CreateSkillTool(
       skill_generator=self.skill_generator,
       session_manager=self.sessions,
   )
   self.tools.register(create_skill_tool)

6. В _process_message, после строки session = self.sessions.get_or_create(msg.session_key), добавь:
   # Обновляем контекст для create_skill
   create_skill_tool = self.tools.get("create_skill")
   if isinstance(create_skill_tool, CreateSkillTool):
       create_skill_tool.set_session_key(msg.session_key)
```

---

### Подэтап 3.3: Автоматическое Предложение Создания Навыков

**Что делаем**: После успешного выполнения сложной задачи (более 5 итераций tool_calls без ошибок) агент автоматически предлагает пользователю сохранить последовательность как навык.

**Промпт для Cursor №12:**

```
Задача: Автоматическое предложение создания навыка

Открой nanobot/agent/loop.py.

1. В методе _process_message, после основного цикла while (после строки final_content = response.content; break), добавь логику анализа:

   # Анализ: стоит ли предложить создание навыка?
   if iteration >= 5 and final_content:
       # Подсчитываем успешные tool_calls (без ошибок)
       successful_calls = 0
       error_calls = 0
       for m in messages:
           if m.get("role") == "tool":
               content = m.get("content", "")
               if content.startswith("Error:"):
                   error_calls += 1
               else:
                   successful_calls += 1
       
       # Если было >= 5 успешных вызовов и мало ошибок, предлагаем навык
       if successful_calls >= 5 and error_calls <= 1:
           skill_suggestion = (
               "\n\n---\n"
               "💡 This was a complex task with multiple steps. "
               "Would you like me to save this as a reusable skill? "
               "Just say 'save as skill' and give it a name."
           )
           final_content += skill_suggestion

Важно: Это мягкое предложение, а не автоматическое создание. Пользователь сам решает, сохранять ли навык.
```

---

### Подэтап 3.4: Тесты для Генерации Навыков

**Что делаем**: Создаём тесты для SkillGenerator и CreateSkillTool.

**Промпт для Cursor №13:**

```
Задача: Написать тесты для генерации навыков

Создай файл tests/test_skill_generator.py.

1. test_extract_tool_sequence:
   - Создай тестовые messages с assistant (tool_calls) и tool (results).
   - Вызови _extract_tool_sequence().
   - Проверь, что результат содержит имена инструментов и аргументы.

2. test_create_skill_from_trajectory:
   - Мокируй LLMProvider.chat() для возврата тестового тела навыка.
   - Вызови create_skill_from_trajectory() с tmp_path.
   - Проверь, что файл SKILL.md создан в правильной директории.
   - Проверь, что содержимое файла включает frontmatter с description.

3. test_create_skill_no_tool_calls:
   - Передай пустые messages.
   - Проверь, что возвращается ошибка "No tool calls found".

4. test_create_skill_tool_execute:
   - Мокируй SessionManager и SkillGenerator.
   - Вызови CreateSkillTool.execute().
   - Проверь, что create_skill_from_trajectory был вызван с правильными аргументами.

5. test_create_skill_tool_no_session:
   - Не устанавливай session_key.
   - Проверь, что execute() возвращает ошибку.
```

---

## Этап 4: Дополнительные Улучшения и Завершение

**Цель**: Реализовать критически важные функции, которые были пропущены или требуют доработки, а также улучшить общую надёжность и предсказуемость агента. Этот этап закрывает технический долг и подготавливает систему к продуктивному использованию.

---

### Подэтап 4.1: Завершение Механизма Подтверждения (ToolPolicy FSM)

**Что делаем**: Реализуем полноценный механизм подтверждения для опасных инструментов. Сейчас `ExecTool` помечен как `REQUIRE_CONFIRMATION`, но агент не ждёт ответа пользователя. Мы реализуем это через машину состояний (FSM) в сессии.

**Промпт для Cursor №14:**

```
Задача: Реализовать ToolPolicy с ожиданием подтверждения

Это самый сложный подэтап. Нужно модифицировать несколько файлов.

--- Шаг 1: Создать/обновить ToolPolicy ---

Создай файл nanobot/agent/tools/policy.py (если не существует):

from enum import Enum

class ToolPolicy(str, Enum):
    ALLOW = "allow"
    REQUIRE_CONFIRMATION = "require_confirmation"
    DENY = "deny"

--- Шаг 2: Добавить policy в базовый Tool ---

Открой nanobot/agent/tools/base.py.

Добавь импорт: from nanobot.agent.tools.policy import ToolPolicy

Добавь свойство в класс Tool (после метода to_schema):

    @property
    def policy(self) -> ToolPolicy:
        """Security policy for this tool. Override in subclasses."""
        return ToolPolicy.ALLOW

--- Шаг 3: Переопределить policy в ExecTool ---

Открой nanobot/agent/tools/shell.py.

Добавь импорт: from nanobot.agent.tools.policy import ToolPolicy

Добавь свойство в класс ExecTool:

    @property
    def policy(self) -> ToolPolicy:
        return ToolPolicy.REQUIRE_CONFIRMATION

--- Шаг 4: Добавить get_policy в ToolRegistry ---

Открой nanobot/agent/tools/registry.py.

Добавь импорт: from nanobot.agent.tools.policy import ToolPolicy

Добавь метод:

    def get_policy(self, name: str) -> ToolPolicy:
        """Get the security policy for a tool."""
        tool = self.get(name)
        return tool.policy if tool else ToolPolicy.DENY

--- Шаг 5: Добавить pending state в Session ---

Открой nanobot/session/manager.py.

В dataclass Session, добавь поле:
    pending_confirmation: dict[str, Any] | None = None

Обнови метод get_history, чтобы он НЕ включал pending_confirmation в историю (это внутреннее состояние).

Обнови _load и save, чтобы они корректно сериализовали/десериализовали pending_confirmation. В save, добавь pending_confirmation в metadata:

    metadata_line = {
        "_type": "metadata",
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "metadata": session.metadata,
        "pending_confirmation": session.pending_confirmation,
    }

В _load, восстанавливай:
    pending_confirmation = data.get("pending_confirmation")

И передавай в Session(..., pending_confirmation=pending_confirmation).

--- Шаг 6: Интегрировать в AgentLoop ---

Открой nanobot/agent/loop.py.

Добавь импорт: from nanobot.agent.tools.policy import ToolPolicy

Модифицируй _process_message:

A) В самом начале метода, ПОСЛЕ получения session, добавь обработку ожидающего подтверждения:

    # Проверяем, есть ли ожидающее подтверждение
    if session.pending_confirmation:
        return await self._handle_confirmation(msg, session)

B) Создай новый метод _handle_confirmation:

    async def _handle_confirmation(self, msg: InboundMessage, session: Session) -> OutboundMessage | None:
        """Handle user response to a pending tool confirmation."""
        pending = session.pending_confirmation
        user_response = msg.content.strip().lower()
        
        # Принимаем: yes, да, y, д, ok, ок
        affirmative = {"yes", "да", "y", "д", "ok", "ок", "1", "true"}
        # Отклоняем: no, нет, n, н, cancel, отмена
        negative = {"no", "нет", "n", "н", "cancel", "отмена", "0", "false"}
        
        # Очищаем pending
        session.pending_confirmation = None
        self.sessions.save(session)
        
        if user_response in affirmative:
            # Выполняем сохранённый вызов
            tool_name = pending["name"]
            tool_args = pending["arguments"]
            logger.info(f"Confirmed: executing {tool_name}")
            result = await self.tools.execute(tool_name, tool_args)
            
            # Сохраняем в историю
            session.add_message("user", msg.content)
            session.add_message("assistant", f"✅ Executed `{tool_name}`: {result[:500]}")
            self.sessions.save(session)
            
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=f"✅ Выполнено `{tool_name}`:\n{result[:2000]}"
            )
        elif user_response in negative:
            session.add_message("user", msg.content)
            session.add_message("assistant", "❌ Operation cancelled.")
            self.sessions.save(session)
            
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="❌ Операция отменена."
            )
        else:
            # Непонятный ответ — переспрашиваем
            session.pending_confirmation = pending  # Возвращаем pending
            self.sessions.save(session)
            
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=f"Пожалуйста, ответьте 'yes' или 'no'. Ожидается подтверждение для `{pending['name']}`."
            )

C) В цикле for tool_call in response.tool_calls, ПЕРЕД вызовом self.tools.execute, добавь проверку:

    for tool_call in response.tool_calls:
        # Проверка политики безопасности
        policy = self.tools.get_policy(tool_call.name)
        if policy == ToolPolicy.DENY:
            result = f"Error: Tool '{tool_call.name}' is denied by security policy."
            messages = self.context.add_tool_result(messages, tool_call.id, tool_call.name, result)
            continue
        
        if policy == ToolPolicy.REQUIRE_CONFIRMATION:
            # Сохраняем вызов и запрашиваем подтверждение
            session.pending_confirmation = {
                "id": tool_call.id,
                "name": tool_call.name,
                "arguments": tool_call.arguments,
                "messages_snapshot_len": len(messages),  # Для восстановления контекста
            }
            self.sessions.save(session)
            
            # Формируем читаемое описание операции
            args_preview = json.dumps(tool_call.arguments, ensure_ascii=False, indent=2)
            if len(args_preview) > 500:
                args_preview = args_preview[:500] + "..."
            
            confirmation_msg = (
                f"⚠️ Требуется подтверждение:\n\n"
                f"Инструмент: `{tool_call.name}`\n"
                f"Аргументы:\n```\n{args_preview}\n```\n\n"
                f"Выполнить? (yes/no)"
            )
            
            # Сохраняем в историю
            session.add_message("user", msg.content)
            session.add_message("assistant", confirmation_msg)
            self.sessions.save(session)
            
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=confirmation_msg,
            )
        
        # Обычное выполнение (policy == ALLOW)
        args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
        logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
        result = await self.tools.execute(tool_call.name, tool_call.arguments)
        
        # ... (рефлексия при ошибке, как в подэтапе 1.2) ...
        
        messages = self.context.add_tool_result(
            messages, tool_call.id, tool_call.name, result
        )
```

---

### Подэтап 4.2: Улучшение Проактивного Поведения (Heartbeat)

**Что делаем**: Делаем Heartbeat более интеллектуальным — вместо простого чтения файла, агент анализирует своё состояние и принимает решения.

**Промпт для Cursor №15:**

```
Задача: Улучшить Heartbeat-промт

Открой nanobot/heartbeat/service.py.

1. Замени HEARTBEAT_PROMPT на:

HEARTBEAT_PROMPT = """This is your periodic heartbeat check. Perform the following analysis:

1. **Check HEARTBEAT.md**: Read it from your workspace. Execute any tasks listed there.
2. **Review recent memory**: Use memory_search to check if there are any pending items or reminders.
3. **System health**: If relevant, check system status (disk space, running processes).

After your analysis:
- If you took any action, summarize what you did.
- If nothing needs attention, reply with just: HEARTBEAT_OK

Be efficient — this runs periodically, so keep it brief."""

2. В методе _tick, добавь логирование времени выполнения:

   import time
   
   async def _tick(self) -> None:
       start = time.monotonic()
       content = self._read_heartbeat_file()
       
       if _is_heartbeat_empty(content):
           logger.debug("Heartbeat: no tasks (HEARTBEAT.md empty)")
           return
       
       logger.info("Heartbeat: checking for tasks...")
       
       if self.on_heartbeat:
           try:
               response = await self.on_heartbeat(HEARTBEAT_PROMPT)
               elapsed = time.monotonic() - start
               
               if HEARTBEAT_OK_TOKEN.replace("_", "") in response.upper().replace("_", ""):
                   logger.info(f"Heartbeat: OK ({elapsed:.1f}s)")
               else:
                   logger.info(f"Heartbeat: completed task ({elapsed:.1f}s)")
           except Exception as e:
               logger.error(f"Heartbeat execution failed: {e}")
```

---

### Подэтап 4.3: Метрики и Наблюдаемость

**Что делаем**: Создаём модуль для сбора метрик работы агента — количество итераций, ошибок, рефлексий, созданных навыков. Это позволит отслеживать «здоровье» и эффективность агента.

**Промпт для Cursor №16:**

```
Задача: Создать модуль метрик

1. Создай файл nanobot/agent/metrics.py:

from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


@dataclass
class SessionMetrics:
    """Метрики одной сессии обработки сообщения."""
    started_at: datetime = field(default_factory=datetime.now)
    iterations: int = 0
    tool_calls_total: int = 0
    tool_calls_failed: int = 0
    reflections_triggered: int = 0
    confirmations_requested: int = 0
    skills_created: int = 0
    tokens_used: int = 0

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "duration_s": (datetime.now() - self.started_at).total_seconds(),
            "iterations": self.iterations,
            "tool_calls_total": self.tool_calls_total,
            "tool_calls_failed": self.tool_calls_failed,
            "reflections_triggered": self.reflections_triggered,
            "confirmations_requested": self.confirmations_requested,
            "skills_created": self.skills_created,
        }

    def log_summary(self) -> None:
        d = self.to_dict()
        logger.info(
            f"Session metrics: {d['iterations']} iterations, "
            f"{d['tool_calls_total']} tool calls ({d['tool_calls_failed']} failed), "
            f"{d['reflections_triggered']} reflections, "
            f"{d['duration_s']:.1f}s"
        )

2. Открой nanobot/agent/loop.py.

3. Добавь импорт: from nanobot.agent.metrics import SessionMetrics

4. В _process_message, в начале метода создай:
   metrics = SessionMetrics()

5. Инкрементируй метрики в соответствующих местах:
   - metrics.iterations += 1 — в начале каждой итерации while
   - metrics.tool_calls_total += 1 — при каждом вызове инструмента
   - metrics.tool_calls_failed += 1 — при ошибке инструмента
   - metrics.reflections_triggered += 1 — при запуске рефлексии
   - metrics.confirmations_requested += 1 — при запросе подтверждения

6. В конце _process_message, перед return, добавь:
   metrics.log_summary()
```

---

## Порядок Выполнения и Зависимости

Ниже представлена рекомендуемая последовательность выполнения подэтапов с учётом зависимостей между ними.

| Очередь | Подэтап | Зависит от | Оценка сложности |
|---------|---------|------------|-------------------|
| 1 | 4.1 (ToolPolicy FSM) | — | Высокая |
| 2 | 1.1 (Модуль Рефлексии) | — | Средняя |
| 3 | 1.2 (Интеграция Рефлексии) | 1.1 | Средняя |
| 4 | 1.3 (Логирование рефлексий) | 1.2 | Низкая |
| 5 | 1.4 (Тесты Рефлексии) | 1.1, 1.2, 1.3 | Средняя |
| 6 | 2.1 (Миграция БД) | — | Средняя |
| 7 | 2.2 (Кристаллизация) | 2.1 | Средняя |
| 8 | 2.3 (memory_search) | 2.1 | Средняя |
| 9 | 2.4 (Авто-контекст) | 2.1, 2.3 | Низкая |
| 10 | 2.5 (Тесты H-MEM) | 2.1–2.4 | Средняя |
| 11 | 3.1 (Генератор навыков) | — | Средняя |
| 12 | 3.2 (create_skill) | 3.1 | Средняя |
| 13 | 3.3 (Авто-предложение) | 3.2 | Низкая |
| 14 | 3.4 (Тесты навыков) | 3.1, 3.2 | Средняя |
| 15 | 4.2 (Heartbeat) | 2.3 | Низкая |
| 16 | 4.3 (Метрики) | 1.2, 4.1 | Низкая |

**Критический путь**: 4.1 → 1.1 → 1.2 → 1.3 → 2.1 → 2.2 → 2.3 → 3.1 → 3.2

**Рекомендация**: Начать с подэтапа **4.1 (ToolPolicy FSM)**, так как это критически важная функция безопасности, которая должна быть реализована до любых других улучшений. Затем перейти к Этапу 1 (Рефлексия), так как он закладывает фундамент для самокоррекции.

---

**Автор**: Manus (Стратег и Архитектор)
**Для**: Г.Вагус (одобрение), Cursor (реализация), nanobot (координация)
