# MCP Unification Spec — Nano Bot V-2.0

**Версия**: 1.0  
**Дата**: 18.02.2026  
**Цель**: Унификация MCP через manus-mcp-cli, замена SmitheryBridge, один CLI.

---

## Контекст

- **nanobot/** — чистая кодовая база без MCP.
- **src/** — legacy: SmitheryBridge, MCPAdapter (manus-mcp-cli).
- **Цель**: MCP в nanobot через MCPTool, один CLI (manus-mcp-cli).

---

## Промпт 1: MCPTool — создание `nanobot/agent/tools/mcp.py`

**Задача**: Создать MCPTool — обёртку над manus-mcp-cli для вызова MCP-инструментов.

Требования:
1. Файл: `nanobot/agent/tools/mcp.py`
2. Класс `MCPCallTool(Tool)` — вызывает `manus-mcp-cli tool call <tool_name> --server <server> --input <json>`
3. Параметры: `server` (string), `tool_name` (string), `arguments` (object, optional) — JSON для --input
4. `ExecTool`/`WebFetchTool` как образец структуры (name, description, parameters, execute)
5. Подпроцесс: `asyncio.create_subprocess_shell`, timeout 20s
6. `ToolPolicy.CONFIRM` или `ALLOW` — на усмотрение
7. При `FileNotFoundError` возвращать: "Error: manus-mcp-cli not found. Install: npm i -g manus-mcp-cli"

---

## Промпт 2: Регистрация MCPTool в AgentLoop

**Задача**: Зарегистрировать MCPCallTool в `_register_default_tools()`.

Требования:
1. Импорт: `from nanobot.agent.tools.mcp import MCPCallTool`
2. В `_register_default_tools()`, после CronTool, добавить: `self.tools.register(MCPCallTool())`

---

## Промпт 3: Динамическая загрузка MCP tools (опциональная фаза)

**Задача**: При старте AgentLoop попытаться загрузить список MCP-инструментов и зарегистрировать их.

Требования:
1. Если `manus-mcp-cli tool list --server <server>` поддерживается — парсить JSON и создавать по одному MCPTool на каждый инструмент (или использовать общий MCPCallTool с параметром tool_name).
2. Конфиг: `nanobot/config` или `.env` — `MCP_SERVERS=manus-mcp` (список серверов через запятую).
3. Если tool list не поддерживается — оставить только один MCPCallTool (из Промпта 1-2). Не ломать запуск при отсутствии manus-mcp-cli.

---

## Промпт 4: Тесты MCPTool

**Задача**: Добавить unit-тест для MCPCallTool.

Требования:
1. Файл: `tests/test_mcp_tool.py`
2. Тест: `test_mcp_call_tool_import` — импорт и создание экземпляра.
3. Тест: `test_mcp_call_tool_execute_mock` — мок subprocess, проверка вызова с правильными аргументами.
4. Тест: `test_mcp_call_tool_not_found` — при FileNotFoundError возвращается ожидаемое сообщение об ошибке.

---

## Промпт 5: Документация и коммит этапа

**Задача**: Обновить документацию и закоммитить изменения.

Требования:
1. В `nanobot/memory/test_checklist_mcp.md` — отметить выполненные пункты (MCPTool добавлен, зарегистрирован в AgentLoop).
2. В `README.md` или `docs/` — краткая секция "MCP Integration" с инструкцией: установка manus-mcp-cli, переменная MCP_SERVERS.
3. Коммит: `git add -A && git commit -m "feat(mcp): MCPTool + registration in AgentLoop (prompts 1-2)"`

---

## Порядок выполнения

| Этап | Промпт | Действие | Тест | Коммит |
|------|--------|----------|------|--------|
| 1 | 1 | MCPTool в mcp.py | `pytest tests/test_mcp_tool.py -v` | — |
| 2 | 2 | Регистрация в AgentLoop | `python -c "from nanobot.agent.loop import AgentLoop; ..."` | commit 1 |
| 3 | 3 | Динамическая загрузка (опционально) | Запуск бота | commit 2 |
| 4 | 4 | Тесты | `pytest tests/test_mcp_tool.py -v` | commit 3 |
| 5 | 5 | Документация + итог | — | commit 4 |

---

## Ссылки

- `nanobot/memory/test_checklist_mcp.md`
- `src/adapters/mcp_adapter.py` — эталон вызова manus-mcp-cli
