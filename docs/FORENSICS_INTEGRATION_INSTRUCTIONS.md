# Интеграция Forensics в основной провайдер

## Что сделано

1. **`nanobot/providers/litellm_provider.py`** — добавлена запись token usage в БД:
   - Импорт `logging`
   - Метод `_track_tokens(model, usage)` — вызывает `add_token_usage` из `nanobot.memory`
   - В `chat()` после успешного вызова LLM: если `result.usage` не пусто, вызывается `_track_tokens`
   - Ошибки логирования перехватываются в `try/except`, не ломают основной поток

2. **`nanobot/cli/commands.py`** — добавлена команда `nanobot usage`:
   - `nanobot usage sessions -d 1` — статистика за сегодня
   - `nanobot usage sessions -d 7` — за последние 7 дней

## Проверка после git pull

1. Убедись, что в `litellm_provider.py` есть метод `_track_tokens` и вызов после `_parse_response`:
   ```python
   if result.usage:
       self._track_tokens(model, result.usage)
   ```

2. Запусти один запрос к агенту:
   ```bash
   nanobot agent -m "Привет, ответь коротко"
   ```

3. Проверь данные:
   ```bash
   nanobot usage sessions -d 1
   ```
   Должна появиться таблица с моделью, prompt/completion/total tokens и requests.

## Схема БД

Используется существующая таблица `token_usage` в `~/.nanobot/memory.db`:

- `date`, `model`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `requests`
- Таблица создаётся автоматически через `init_db()` при первом обращении к памяти

**Миграция не требуется** — структура уже есть в `nanobot/memory/db.py`.

## Совместимость с ModelRouter (llm-3172)

- `_track_tokens` вызывается с `model` из `chat()` — это уже итоговая модель после роутинга (если роутер меняет модель, запись идёт по выбранной модели)
- Роутер не конфликтует: он лишь выбирает модель до вызова `provider.chat()`, провайдер по-прежнему получает финальную модель
