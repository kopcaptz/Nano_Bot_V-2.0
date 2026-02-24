# Отчёт: Экспериментальная интеграция Smithery MCP — Google Calendar

**Дата:** 2026-02-16  
**Цель:** Этап 1 гибридной интеграции — подключить Google Calendar через Smithery MCP

---

## Шаг 1: Установка Smithery CLI

```bash
npm install -g @smithery/cli
```

**Результат:** ✅ Успешно (302 packages за ~10 сек)

---

## Шаг 2: Проверка версии

```bash
smithery --version
```

**Версия Smithery CLI:** `4.0.1`

---

## Шаг 3: Авторизация

```bash
smithery auth login
```

**Результат:** ⏳ Требуется ручное завершение

Команда запускает OAuth-флоу и открывает браузер. В headless/remote окружении браузер не открывается автоматически — нужно вручную перейти по ссылке:

```
https://smithery.ai/auth/cli?s=<session-id>
```

После успешного входа в аккаунт Smithery команда завершится, и credentials сохранятся локально.

**Блокер:** Без завершённой авторизации команды `mcp add`, `tool list`, `tool call` возвращают:
```
Failed to add connection: No API key found. Run 'smithery login' to authenticate.
```

---

## Шаг 4: Доступные MCP-серверы для Calendar

Поиск **без авторизации** работает. Найдены варианты:

| qualifiedName | useCount | Описание |
|---------------|----------|----------|
| `googlecalendar` | 5354 | Официальный Google Calendar |
| `googlesuper` | 8031 | Все сервисы Google (Drive, Calendar, Gmail и др.) |
| `Kashyab19/google-calendar-mcp-server` | 192 | Community-сервер Calendar |
| `INSIDE-HAIR/mcp-google-meet-and-calendar` | 416 | Calendar + Google Meet |

Для эксперимента рекомендован: **`googlecalendar`** (наибольшее использование для отдельного Calendar).

---

## Команды для выполнения после авторизации

### 4.1 Добавить Google Calendar MCP

```bash
smithery mcp add googlecalendar
```

или с полным URL:
```bash
smithery mcp add https://server.smithery.ai/googlecalendar
```

Smithery проведёт OAuth для Google Calendar (откроется браузер для выбора аккаунта Google).

### 4.2 Список инструментов

```bash
smithery tool list
```

или для конкретного соединения:
```bash
smithery tool list googlecalendar
```

### 4.3 Тестовый вызов (события на сегодня)

```bash
smithery tool call googlecalendar list-events '{"timeMin": "2026-02-16T00:00:00Z", "timeMax": "2026-02-16T23:59:59Z"}'
```

Альтернативный формат (если имена инструментов отличаются):
```bash
smithery tool find events
smithery tool get googlecalendar <tool-name>
```

---

## Скрипт для локального запуска

См. `scripts/smithery_calendar_test.sh` — выполняет шаги 4–6 после того, как `smithery auth login` успешно завершён.

---

## Наблюдения

### Установка
- Установка через npm простая, без ошибок
- Версия 4.0.1, CLI стабильный
- Команды: `mcp`, `tool`, `auth`, `skill`, `namespace`, `setup`

### Авторизация
- **Требуется интерактивный браузер** — в CI/headless нужен альтернативный путь
- `smithery auth token` — возможность выпуска service token для автоматизации (проверить отдельно)
- Без auth поиск (`mcp search`) работает, остальные операции — нет

### Структура команд
- `smithery mcp add <server>` — добавить соединение
- `smithery tool list [connection]` — список инструментов
- `smithery tool call <connection> <tool> [args]` — вызов инструмента
- Аргументы передаются как JSON-строка

### Следующие шаги (после успешного теста)
1. Замерить время отклика `tool call`
2. Зафиксировать точные имена инструментов Google Calendar
3. Подключить `MCPAdapter` в `CommandHandler` для вызовов через `smithery` вместо `manus-mcp-cli`
