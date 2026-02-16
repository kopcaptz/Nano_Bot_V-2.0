# Отчёт: Интеграция Smithery Calendar в Handler и LLM Router

**Дата:** 16 февраля 2026  
**Ветка:** cursor/smithery-google-calendar-972a

---

## 1. Список изменённых файлов

| Файл | Изменения |
|------|-----------|
| `src/core/llm_router.py` | Добавлена секция CALENDAR TOOLS в системный промпт |
| `src/core/handler.py` | Импорт SmitheryBridge, обработка [ACTION:CALENDAR_*], `_resolve_calendar_time_range`, `_handle_calendar_action`, `_wrap_calendar_result` |
| `tests/test_command_handler_shortcuts.py` | Добавлен тест `test_calendar_action_triggers_bridge_and_returns_error_when_not_authed` |

---

## 2. Пример ответа на «Что у меня завтра в календаре?»

### При успешной авторизации Smithery

1. Пользователь: «Что у меня завтра в календаре?»
2. LLM возвращает: `[ACTION:CALENDAR_LIST]`
3. Handler извлекает «завтра» из запроса → вычисляет `timeMin`/`timeMax` для следующего дня
4. Вызов: `bridge.call_tool("googlecalendar", "list-events", {"timeMin": "2026-02-17T00:00:00Z", "timeMax": "2026-02-17T23:59:59Z"})`
5. Результат оборачивается в `[CALENDAR_DATA_READONLY]` и передаётся в LLM
6. LLM формирует ответ, например: «Завтра у вас запланировано: встреча в 10:00, обед с коллегами в 13:00».

### Без авторизации (текущее состояние в CI)

Ответ:

> Календарь недоступен. Убедитесь, что выполнена авторизация Smithery (smithery auth login) и добавлен Google Calendar (smithery mcp add googlecalendar). Ошибка: No API key found. Run 'smithery login' to authenticate.

---

## 3. Реализованные action-теги

| Тег | Инструмент Smithery | Описание |
|-----|---------------------|----------|
| `[ACTION:CALENDAR_LIST]` | `list-events` | Список событий; диапазон дат выводится из запроса или JSON в теге |
| `[ACTION:CALENDAR_CREATE {...}]` | `create-event` | Создание события по JSON |
| `[ACTION:CALENDAR_UPDATE {...}]` | `update-event` | Обновление события по JSON |
| `[ACTION:CALENDAR_DELETE {...}]` | `delete-event` | Удаление события по JSON |

---

## 4. Разрешение относительных дат

Handler распознаёт в тексте запроса:

- «завтра», «tomorrow», «следующий день» → следующий день
- «послезавтра», «day after» → через 2 дня
- «вчера», «yesterday» → предыдущий день
- по умолчанию → сегодня

---

## 5. Проблемы и вопросы

1. **Имена инструментов**  
   Используются: `list-events`, `create-event`, `update-event`, `delete-event`. Фактический список инструментов Google Calendar MCP может отличаться — нужно проверить после `smithery tool list googlecalendar`.

2. **Авторизация**  
   Для работы календаря нужна авторизация Smithery и добавленный MCP-сервер. В headless/CI это обычно недоступно.

3. **Параметры create/update/delete**  
   Ожидаемая схема JSON (summary, start, end, eventId и т.п.) должна быть согласована с реальным API Smithery/Google Calendar.

4. **Таймзона**  
   Сейчас используется UTC (`timezone.utc`). Для корректной работы в разных таймзонах может потребоваться учёт локального времени пользователя.
