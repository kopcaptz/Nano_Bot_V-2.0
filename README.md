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
python -m playwright install
```

Если команда `playwright` не найдена в PATH, используйте именно вариант через `python -m`.

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

### Рекомендуемая рабочая директория (песочница)

Создайте директорию заранее:

- Windows:
  - `C:\Users\kopca\Nano_Bot_V2\workspace\`
- Linux/macOS (пример):
  - `/workspace/workspace`

> Если на Linux/macOS в `AGENT_WORKSPACE` оставить Windows-путь (`C:\...`),
> приложение автоматически переключится на локальный fallback-путь `<repo>/workspace`.

## 6) Запуск

```bash
python src/main.py
```

---

## Быстрые команды в Telegram (MVP)

- Обычный текст: уходит в LLM
- Команды можно отправлять как slash-команды (`/status`) или обычным текстом.
- `/help` — список доступных команд
- `/status` — состояние адаптеров и памяти текущего чата
- `/clear_history` — очистить историю текущего чата
- `/system <cmd>` — выполнить безопасную системную команду (whitelist)
- `/browser_open <url>` — открыть страницу в браузере
- `/browser_text [url]` — получить текст страницы
- `/screenshot <filename.png>` — сделать скриншот в `AGENT_WORKSPACE/screenshots/`
- `/ocr <image_path>` — OCR-заглушка (пока возвращает `OCR not implemented yet`)

