# Техническое описание Nanobot

**Nanobot** — лёгкий персональный AI-ассистент на Python 3.11+ с модульной архитектурой. Проект распространяется под лицензией MIT.

---

## Назначение

Локальный асинхронный агент для работы с LLM через различные каналы коммуникации. Выполняет задачи: ответы на вопросы, работа с файлами, веб-поиск, планировщик задач, управление навыками (skills), интеграция с MCP.

---

## Архитектура

### Ядро: AgentLoop

Цикл обработки сообщений:

1. **Приём** — сообщения через MessageBus
2. **Контекст** — ContextBuilder собирает историю, память, навыки
3. **Навигатор** — NavigatorAgent (опционально) предварительная маршрутизация запроса
4. **LLM** — вызов провайдера (LiteLLM)
5. **Инструменты** — выполнение tool calls
6. **Рефлексия** — анализ ошибок через Reflection

### Компоненты

| Компонент | Описание | Путь |
|-----------|----------|------|
| **MessageBus** | Очередь событий InboundMessage / OutboundMessage | `nanobot/bus/` |
| **LiteLLMProvider** | Поддержка OpenAI, Anthropic, OpenRouter, локальных моделей | `nanobot/providers/` |
| **SessionManager** | Сессии в JSONL (`~/.nanobot/sessions/`) | `nanobot/session/` |
| **VectorDBManager** | ChromaDB для векторного поиска навыков и памяти | `nanobot/memory/` |
| **SkillManager** | Хранение, векторный поиск, композиция навыков | `nanobot/agent/skill_*.py` |

### Каналы (Channels)

- Telegram, WhatsApp, Discord, Slack
- Feishu (Lark), DingTalk, QQ
- Email (IMAP/SMTP)
- System (CLI, интерактивный режим)

### Инструменты (Tools)

- **Файловая система:** read_file, write_file, edit_file, list_dir
- **Shell:** exec (с ограничениями и политикой)
- **Веб:** web_search, web_fetch
- **Память:** memory_search (SQLite + ChromaDB)
- **Остальное:** skill (создание навыков), message, spawn (подзадачи), cron, mcp_call

---

## Конфигурация

Файл: `~/.nanobot/config.json`

- Провайдеры LLM (OpenAI, Anthropic, Groq и др.)
- Настройки каналов (токены, allow_from)
- Рабочая директория (workspace)
- Политика инструментов (ExecToolConfig, restrict_to_workspace)

---

## Память

- **SQLite** (`~/.nanobot/memory.db`) — факты, рефлексии, учёт токенов
- **ChromaDB** (`~/.nanobot/chroma/`) — векторный поиск
- **JSONL** (`~/.nanobot/sessions/`) — история диалогов

---

## Запуск

```bash
# CLI-агент (интерактивный режим)
nanobot agent

# Шлюз для каналов (Telegram, WhatsApp и др.)
nanobot gateway

# С сообщением
nanobot agent -m "Привет"
```

---

## Зависимости (основные)

- litellm, anthropic, google-generativeai — LLM
- pydantic, pydantic-settings — конфигурация
- sentence-transformers, chromadb — векторный поиск
- Typer, Rich — CLI
- python-telegram-bot, slack-sdk, discord.py и др. — каналы
