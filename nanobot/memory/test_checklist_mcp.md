# Чеклист: MCP архитектура (упрощение)

## КОМАНДЫ ДЛЯ ТЕСТИРОВАНИЯ

```powershell
# 1. Проверить отсутствие SmitheryBridge в nanobot/
# rg "SmitheryBridge" nanobot/ --glob "*.py"  # пусто = OK

# 2. Проверить наличие MCPTool/MCP в AgentLoop
# rg "MCP|mcp" nanobot/agent/loop.py

# 3. Проверить динамическую загрузку MCP в nanobot
# rg "mcp|MCP|manus-mcp" nanobot/ --glob "*.py"

# 4. Проверить импорт AgentLoop и ToolRegistry
python -c "from nanobot.agent.loop import AgentLoop; from nanobot.agent.tools.registry import ToolRegistry; print('AgentLoop OK')"

# 5. Запустить тесты (без smithery/calendar)
python -m pytest tests/ -v -x -k "not smithery and not calendar"
```

## ЧЕКЛИСТ

### 1. SmitheryBridge удалён
- [x] ✅ SmitheryBridge не используется в nanobot/ (grep nanobot/*.py = пусто)
- [ ] ❌ SmitheryBridge **НЕ удалён** — остаётся в src/ (legacy): `src/core/smithery_bridge.py`, `src/core/handler.py`, `tests/test_smithery_bridge.py`, `test_calendar_integration.py`

### 2. MCPTool в AgentLoop
- [ ] ❌ MCPTool **отсутствует** — нет `nanobot/agent/tools/mcp.py`
- [ ] ❌ AgentLoop **не регистрирует** MCP инструменты (только read_file, exec, web_search и т.д.)

### 3. Динамическая загрузка MCP
- [ ] ❌ В nanobot/ **нет** динамической загрузки MCP (list_tools → register)
- [ ] ⚠️ В src/ есть: `src/core/tool_registry.py` — `register_mcp_tools()`, но это legacy

### 4. Унификация с manus-mcp-cli
- [ ] ❌ **Два разных CLI**: src/ использует и SmitheryBridge (smithery), и MCPAdapter (manus-mcp-cli)
- [ ] ❌ MCPAdapter только в src/adapters/ — в nanobot/ **нет** эквивалента

---

## Результат проверки (18.02.2026)

| Пункт | Статус | Комментарий |
|-------|--------|-------------|
| 1 SmitheryBridge | ❌ legacy | nanobot чист, но src/ всё ещё содержит SmitheryBridge (handler, calendar) |
| 2 MCPTool в AgentLoop | ❌ | MCPTool не существует, AgentLoop не знает MCP |
| 3 Динамическая загрузка | ❌ | Только в src/ (legacy), nanobot без MCP |
| 4 manus-mcp-cli | ❌ | Два CLI: smithery + manus-mcp-cli, не унифицировано |

### Где SmitheryBridge:
- `src/core/smithery_bridge.py` — класс
- `src/core/handler.py` — `_calendar_bridge = SmitheryBridge()`
- `src/core/__init__.py` — экспорт
- `tests/test_smithery_bridge.py` — тесты
- `test_calendar_integration.py` — интеграционный тест

### Где manus-mcp-cli (MCPAdapter):
- `src/adapters/mcp_adapter.py` — вызывает `manus-mcp-cli tool call`
- `src/core/tool_registry.py` — `register_mcp_tools()`, dispatch к MCPAdapter

### Рекомендации для упрощения:
1. **Удалить SmitheryBridge** — заменить на MCPTool в nanobot, вызывающий manus-mcp-cli
2. **Добавить MCPTool** в `nanobot/agent/tools/mcp.py` — обёртка над manus-mcp-cli
3. **Динамическая загрузка** — при старте AgentLoop: `manus-mcp-cli tool list` → register в ToolRegistry
4. **Один CLI** — только manus-mcp-cli, убрать smithery из кодовой базы

