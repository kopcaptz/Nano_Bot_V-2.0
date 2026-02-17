# Чеклист: SkillManager интеграция (семантический поиск)

**Статус:** ⚠️ ГОТОВ К ИНТЕГРАЦИИ (код есть, интеграции нет)

---

## КОМАНДЫ ДЛЯ ТЕСТИРОВАНИЯ

```powershell
# 1. Проверить импорт SkillManager
python -c "from nanobot.agent.skill_manager import SkillManager; print('SkillManager OK')"

# 2. Запустить тесты SkillManager
python -m pytest tests/test_skill_management.py -v

# 3. Проверить использование SkillManager в AgentLoop
Get-ChildItem -Path "nanobot\agent" -Recurse -Filter "*.py" | Select-String -Pattern "SkillManager"

# 4. Проверить ContextBuilder интеграцию
Get-ChildItem -Path "nanobot\agent" -Recurse -Filter "*.py" | Select-String -Pattern "SkillsLoader|skill_manager"

# 5. Проверить семантический поиск (search_skills)
# Примечание: требуется pip install hnswlib sentence-transformers
# При auto_sync=False векторный индекс не заполняется — поиск вернёт []
python -c "
from nanobot.agent.skill_manager import SkillManager
from pathlib import Path
import tempfile
with tempfile.TemporaryDirectory() as d:
    m = SkillManager(Path(d), auto_sync=True)  # auto_sync=True для индексации
    m.add_skill('test_skill', 'How to write Python code', description='Python')
    r = m.search_skills('write code', limit=3)
    print('search_skills OK:', len(r) > 0)
"
```

## ЧЕКЛИСТ

### 1. SkillManager в AgentLoop
- [ ] ❌ SkillManager **отсутствует** в AgentLoop
- [ ] ❌ AgentLoop **не инициализирует** SkillManager
- [ ] ❌ AgentLoop **не использует** search_skills / compose_for_task

### 2. Семантический поиск навыков
- [x] ✅ SkillManager.search_skills() — работает через SkillVectorSearch (HNSW)
- [x] ✅ SkillVectorSearch интегрирован (all-MiniLM-L6-v2)
- [x] ✅ hierarchical_search() — поиск по уровням meta/composite/basic
- [x] ✅ SkillComposer.compose_for_task() использует search_skills

### 3. Интеграция с ContextBuilder
- [ ] ❌ ContextBuilder **не использует** SkillManager
- [x] ✅ ContextBuilder использует SkillsLoader (файловая система workspace/skills/)
- [ ] ❌ build_system_prompt() **не получает** навыки из SkillManager (семантически подобранные)

### 4. Производительность поиска
- [x] ✅ HNSW индекс (hnswlib) — быстрый approximate NN
- [ ] ⚠️ hnswlib — **не установлен** (pip install hnswlib)
- [x] ✅ Lazy loading embedder и index
- [ ] ⚠️ Первый вызов search_skills загружает SentenceTransformer (~1-2 сек)

### 5. Тесты
- [x] ✅ tests/test_skill_management.py — 18/19 passed
- [ ] ⚠️ test_export_import_skill — 1 fail (import использует filename.stem вместо имени из контента)

---

## РЕЗУЛЬТАТЫ ПРОВЕРКИ (18.02.2026)

| Компонент | Статус | Комментарий |
|-----------|--------|-------------|
| SkillManager импорт | ✅ | OK |
| SkillVectorSearch | ✅ | HNSW + SentenceTransformer |
| search_skills | ✅ | Семантический поиск работает |
| SkillComposer | ✅ | compose_for_task, analyze_coverage |
| AgentLoop | ❌ | SkillManager **не интегрирован** |
| ContextBuilder | ❌ | Использует SkillsLoader, **не SkillManager** |
| Тесты | ⚠️ | 18/19 passed |

---

## ВЫВОД

**SkillManager** реализован и работает (репозиторий, векторный поиск, композиция), но **не интегрирован** в основной цикл агента:

1. **AgentLoop** — не создаёт и не использует SkillManager
2. **ContextBuilder** — собирает навыки через SkillsLoader (файлы), а не через SkillManager.search_skills()
3. Семантический подбор навыков под запрос пользователя **не выполняется** при build_messages()

**Рекомендации для интеграции:**
- Добавить SkillManager в AgentLoop.__init__
- Передать skill_manager в ContextBuilder
- В ContextBuilder.build_messages: перед сборкой контекста вызывать `skill_manager.search_skills(current_message)` и добавлять найденные навыки в system prompt

---

## КОНСУЛЬТАЦИЯ С MANUS

Нужен экспертный совет по интеграции SkillManager в агентный цикл.

**Вопрос:** Как лучше заменить SkillsLoader на SkillManager?

**Варианты:**
1. **Полная замена** — ContextBuilder работает только с SkillManager; SkillsLoader удаляется.
2. **Гибридный подход** — SkillsLoader для builtin/workspace навыков (SKILL.md) + SkillManager для семантического поиска и динамически созданных навыков.

**Критерии выбора:** совместимость с существующими skills/, миграция данных, сложность внедрения.

---

## Итоговый статус

⚠️ **ФАЗА 5 ЖДЁТ АРХИТЕКТУРНОГО РЕШЕНИЯ**
