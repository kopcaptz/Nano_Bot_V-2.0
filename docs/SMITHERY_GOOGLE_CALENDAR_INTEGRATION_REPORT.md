# Отчёт: Этап 1 — Интеграция Smithery MCP с Google Calendar

**Дата:** 16 февраля 2026  
**Ветка:** cursor/smithery-google-calendar-972a

---

## 1. Версия Smithery CLI

| Параметр | Значение |
|----------|----------|
| **Версия** | 4.0.1 |
| **Установка** | `npm install -g @smithery/cli` |
| **Время установки** | ~9 секунд (302 пакета) |

---

## 2. Результаты по шагам

### Шаг 1–2: Установка и проверка — ✅ Успешно
- CLI установлен глобально
- Команда `smithery --version` возвращает `4.0.1`

### Шаг 3: Авторизация — ⚠️ Частично
- **Первая попытка:** `smithery auth login` — ошибка «Cannot connect to Smithery»
- **Вторая попытка (verbose):** Сессия создаётся успешно, но:
  - Браузер не открывается (среда без GUI: `Missing X server or $DISPLAY`)
  - CLI предлагает ручную ссылку: `https://smithery.ai/auth/cli?s=<session-id>`
  - Polling работает, но авторизация не завершена (требуется открыть ссылку в браузере)

### Шаг 4–6: MCP и тестовый вызов — ❌ Блокируются
- `smithery mcp add googlecalendar` → **No API key found. Run 'smithery login' to authenticate.**
- `smithery tool list` → та же ошибка
- `smithery tool call` → не выполнен из-за отсутствия auth

---

## 3. Список инструментов Google Calendar (из реестра)

Команда `smithery mcp search googlecalendar` работает **без авторизации** и возвращает:

| Сервер | qualifiedName | Описание | Использований |
|--------|---------------|----------|---------------|
| **Google Calendar** | `googlecalendar` | Инструмент управления временем: планирование, напоминания, интеграция с почтой | 5354 |
| Connection URL | — | `https://server.smithery.ai/googlecalendar` | — |

Точный перечень инструментов (например, `list-events`) будет доступен после `smithery tool list` при успешной авторизации.

---

## 4. Результат тестового вызова

**Статус:** Не выполнен (требуется авторизация)

Планировавшаяся команда:
```bash
smithery tool call googlecalendar list-events '{"timeMin": "2026-02-16T00:00:00Z", "timeMax": "2026-02-16T23:59:59Z"}'
```

---

## 5. Время отклика (приблизительно)

| Операция | Время |
|----------|-------|
| `npm install -g @smithery/cli` | ~9 с |
| `smithery --version` | &lt;1 с |
| `smithery auth login` (ошибка) | ~3.7 с |
| `smithery mcp search googlecalendar` | ~1 с |
| `smithery mcp add googlecalendar` (ошибка) | ~0.6 с |

---

## 6. Наблюдения

### Установка
- Установка через npm простая и быстрая
- Зависимости: @anthropic-ai/mcpb, @modelcontextprotocol/sdk, ngrok и др.
- Размер распакованного пакета: ~2.9 MB

### Авторизация
- Требуется браузер (OAuth device flow)
- В headless/бездисплейной среде: браузер не открывается автоматически
- Рекомендуется выполнять `smithery auth login` на локальной машине с браузером
- После успешного логина токены сохраняются локально

### Сеть
- Доступ к https://smithery.ai есть (HTTP 429 при проверке curl — возможное rate limiting)
- Поиск MCP (`smithery mcp search`) не требует авторизации

### Рекомендации для следующего этапа
1. Выполнить `smithery auth login` на локальной машине с графическим окружением
2. После авторизации выполнить:
   - `smithery mcp add googlecalendar`
   - `smithery tool list`
   - `smithery tool call googlecalendar list-events '{"timeMin": "2026-02-16T00:00:00Z", "timeMax": "2026-02-16T23:59:59Z"}'`
3. Рассмотреть использование Service Token (`smithery auth token`) для CI/headless-сценариев

---

## Приложение B: SmitheryBridge (Этап 2)

Модуль `src/core/smithery_bridge.py` — мост для вызова MCP через Smithery CLI.

- **Строк кода:** 206
- **Публичные методы:** `call_tool(server, tool_name, params)`, `list_tools(server=None)`
- **Timeout:** 30 секунд (по умолчанию)
- **Тесты:** `tests/test_smithery_bridge.py` — 4 теста проходят

---

## Приложение: Структура CLI

```
Commands:
  mcp         Search, connect, and manage MCP servers
  tool        Find and call tools from MCP servers
  skill       Search, view, and install Smithery skills
  auth        Authentication and permissions
  setup       Install the Smithery CLI skill for your agent
  namespace   Manage namespace context

mcp subcommands:
  search      Search the Smithery registry
  add         Add an MCP server connection
  list        List your connections
  get         Get connection details
  remove      Remove connections
  update      Update connection details
```
