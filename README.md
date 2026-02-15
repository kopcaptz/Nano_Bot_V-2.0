# Nano Bot V-2.0 (Local System Agent)

Локальный асинхронный агент на Python 3.11+ с 4 адаптерами:
- Telegram
- System
- Browser
- Vision

Также включает:
- EventBus для событийной архитектуры
- CrystalMemory для контекста диалога
- OpenRouter LLM Router (модель по умолчанию: `kimi/kimi-k2.5`)
- graceful shutdown по `SIGINT` / `SIGTERM`

## 1) Клонирование репозитория

```bash
git clone <your-repo-url>
cd <repo-folder>
```

## 2) Создание виртуального окружения

```bash
python -m venv .venv
source .venv/bin/activate
```

Для Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

## 3) Установка зависимостей

```bash
pip install -r requirements.txt
```

## 4) Установка браузеров для Playwright

```bash
playwright install
```

## 5) Создание `.env` из `.env.example`

Скопируйте пример:

```bash
cp .env.example .env
```

Заполните токены и настройки:
- `TELEGRAM_BOT_TOKEN`
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`
- `AGENT_WORKSPACE`
- `LOG_LEVEL`

## 6) Запуск

```bash
python src/main.py
```

---

## Быстрые команды в Telegram (MVP)

- Обычный текст: уходит в LLM
- `/system <cmd>` — выполнить безопасную системную команду (whitelist)
- `/browser_open <url>` — открыть страницу в браузере
- `/browser_text [url]` — получить текст страницы
- `/screenshot <filename.png>` — сделать скриншот в `AGENT_WORKSPACE/screenshots/`

