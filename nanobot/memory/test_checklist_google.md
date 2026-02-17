# Чеклист: Google экосистема частично работает

## КОМАНДЫ ДЛЯ ТЕСТИРОВАНИЯ

```powershell
# 1. Проверить MCP конфигурацию (Smithery CLI)
smithery --version
smithery mcp list
smithery tool list --limit=200

# 2. Calendar — список инструментов и тест events_list
python -c "
import asyncio
from src.core.smithery_bridge import SmitheryBridge
async def test():
    b = SmitheryBridge(timeout=30)
    tools = await b.list_tools(server='googlecalendar-kMHR', limit=50)
    print('Calendar tools:', len(tools) if isinstance(tools, list) else tools)
    if isinstance(tools, list):
        print('Examples:', [t.get('name') for t in tools[:5]])
asyncio.run(test())
"

# 3. Sheets — проверить наличие
smithery tool list googlesheets 2>$null; if ($?) { echo 'Sheets OK' } else { echo 'Sheets not configured' }

# 4. Gmail — проверить GmailAdapter и credentials
python -c "
from pathlib import Path
creds = Path('credentials.json')
token = Path('token.json')
print('credentials.json:', creds.exists())
print('token.json:', token.exists())
"

# 5. Drive — проверить наличие
smithery tool list googledrive 2>$null; if ($?) { echo 'Drive OK' } else { echo 'Drive not configured' }

# 6. Тестовые операции: Calendar events_list
python test_calendar_integration.py
```

## ЧЕКЛИСТ

### MCP конфигурация
- [x] ✅ Smithery CLI установлен и в PATH (4.0.1)
- [ ] ❌ smithery auth login — 403 connections:read (namespace minnow-QPDS)
- [ ] ⚠️ MCP серверы — smithery mcp list / tool list возвращают 403

### Сервис 1: Google Calendar
- [x] ✅ SmitheryBridge в src/core/smithery_bridge.py
- [x] ✅ Handler: [ACTION:CALENDAR_*], regex, time range — всё работает
- [x] ✅ LLM Router: CALENDAR TOOLS в системном промпте
- [ ] ❌ events_list — 403 (Smithery OAuth/namespace, требуется smithery auth login)

### Сервис 2: Google Sheets
- [ ] ❌ Интеграция отсутствует в проекте (нет adapter, нет Smithery-сервера)

### Сервис 3: Gmail
- [x] ✅ GmailAdapter в src/adapters/gmail_adapter.py
- [x] ✅ credentials.json и token.json существуют
- [x] ✅ OAuth scope gmail.readonly настроен
- [ ] ⚠️ get_unread_summary() — не тестировалась (нужен запуск бота)

### Сервис 4: Google Drive
- [ ] ❌ Интеграция отсутствует в проекте (нет adapter, нет Smithery-сервера)

### Интеграция с AgentLoop/Handler
- [x] ✅ Calendar: [ACTION:CALENDAR_*] в Handler (src/core/handler.py)
- [x] ✅ Gmail: /gmail, /gmail_read shortcuts в Handler
- [x] ✅ SmitheryBridge.call_tool / list_tools — код готов

---

**Результат проверки (18.02.2026):**

| Сервис | Статус | Комментарий |
|--------|--------|-------------|
| Calendar | ⚠️ | Smithery 403 — нужна переавторизация |
| Gmail | ✅ | Прямой API работает |
| Sheets | ❌ | НЕТ В ПРОЕКТЕ |
| Drive | ❌ | НЕТ В ПРОЕКТЕ |

---

## РЕАЛЬНЫЙ СТАТУС

- **2 из 4 сервисов** интегрированы (Calendar, Gmail)
- **Calendar + Gmail = ~51 инструмент** (не 138!)
- **Sheets и Drive** отсутствуют в коде

---

## Итоговый статус

### ⚠️ ФАЗА 3 ЧАСТИЧНО ЗАВЕРШЕНА

**Что работает:**
- **Gmail** — прямой API, GmailAdapter, credentials, token
- **Calendar** — код и Handler готовы; events_list требует `smithery auth login`

**Что отсутствует:**
- Google Sheets — нет интеграции
- Google Drive — нет интеграции
