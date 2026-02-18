# 📊 АУДИТ STREAMLIT DASHBOARD (Nano_Bot V-2.0)

**Дата:** 18.02.2025  
**Версия:** Nano Bot V-2.0  
**Папка:** `dashboard/`

---

## 1️⃣ СТАТУС-ОТЧЁТ: ФУНКЦИИ И СТАТУС

| Функция | Статус | Комментарий |
|---------|--------|-------------|
| **Dashboard (главная)** | ⚠️ | Метрики (Sessions, Tokens, Requests, Model) — данные из БД; при пустой БД показываются fake_sessions/fake_token_usage |
| **Auto-refresh каждые 5 сек** | ⚠️ | `@st.fragment(run_every=...)` — зависит от Streamlit 1.33+; возможна ошибка ImportError |
| **Settings (редактирование config)** | ✅ | Полная работа: model, workspace, max_tokens, temperature, gateway, channels |
| **Memory (Facts/Reflections/Journal)** | ⚠️ | Данные из memory.db; при пустой БД — placeholder |
| **Tools (список инструментов)** | ⚠️ | Статический список из кода, не из runtime; нет динамики |
| **Monitor (токены по дням/моделям)** | ⚠️ | Данные из token_usage; при пустой БД — fake_token_usage |
| **Admin (пути, config summary)** | ❌ | **Баг:** ожидает `config.workspace_path`, `config.agents.defaults.model`; при JSON fallback — dict → AttributeError |
| **Token Forensics** | ❌ | Нет в БД и дашборде |
| **Model Router logs** | ❌ | Нет таблицы/полей session_id, chosen_model, routing_reason |
| **График стоимости по моделям** | ❌ | Только total_tokens; нет $/cost |
| **Топ дорогих сессий** | ❌ | Нет таблицы usage_sessions; sessions — только key, created_at, updated_at |
| **Переключатель роутера** | ❌ | Нет настройки роутера в config/Settings |
| **Effort (итерации/шаги)** | ❌ | Не сохраняется в БД |

---

## 2️⃣ СТРУКТУРА МЕНЮ И ВИДЖЕТЫ

### Sidebar
- **🤖 Nanobot** (заголовок)
- Ссылки на страницы (Streamlit multi-page app):
  - **Dashboard** — главная
  - **Settings** — настройки
  - **Memory** — Facts, Reflections, Journal
  - **Tools** — список инструментов
  - **Monitor** — токены
  - **Admin** — пути и сводка

### Главная (Welcome)
- Приветствие
- Подсказка: "Navigate to Dashboard..."
- Info: "Use the sidebar to explore..."

### Dashboard
- 4 метрики: Sessions, Tokens Today, Requests Today, Default Model
- Кнопка 🔄 Refresh
- Recent Sessions (expanders с key, channel, updated_at)
- Caption: "↻ Last updated: HH:MM:SS" (при наличии st.fragment)

### Settings
- Agent Defaults: model, workspace, max_tokens, temperature
- Gateway: host, port
- Channels: чекбоксы (Telegram, Discord, WhatsApp, Email, Slack, Mochat)
- Кнопка 💾 Save Configuration

### Memory
- Tabs: Facts | Reflections | Journal
- Facts: поиск, фильтр по категории, expanders
- Reflections: tool_name, error_text, insight
- Journal: date picker, список записей

### Monitor
- 4 метрики: Total/Prompt/Completion Tokens, Requests
- By Model (сегодня)
- Line chart: Token Usage за 7 дней (pandas + st.line_chart)

### Admin
- Paths: config.json, sessions/, memory.db
- Config Summary (⚠️ падает при dict config)
- Health Check

---

## 3️⃣ MISSING FEATURES / СЕРЫЕ ЗОНЫ

### Критические
1. **Token usage не записывается в main build**  
   `add_token_usage` вызывается только в `litellm_provider-Jeki.py`. Основной `litellm_provider.py` не пишет в БД → Monitor/Dashboard всегда placeholder или пусто.

2. **Admin crash**  
   `load_dashboard_config()` может вернуть `dict` (JSON fallback). Admin использует `config.workspace_path`, `config.agents.defaults.model` → `AttributeError`.

### Данные из БД
3. **token_usage** — поля: `date`, `model`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `requests`. Нет: `session_id`, `chosen_model`, `routing_reason`.

4. **sessions** — из файлов JSONL в `~/.nanobot/sessions/`. Поля: `key`, `created_at`, `updated_at`, `path`. Нет привязки к токенам/стоимости.

5. **Нет таблиц** `usage_sessions`, `token_forensics`, `model_router_logs`.

### UI/UX
6. **Tools** — статический список, policy захардкожена.
7. **Monitor** — `st.line_chart` (базовый), нет Plotly; разбивка по моделям — только текст.
8. **Нет алертов** — "Расход превышен!", "Модель упала!".
9. **Auto-refresh** — try/except с `pass`, тихий отказ при старом Streamlit.

---

## 4️⃣ ТОП-5 ИДЕЙ ДЛЯ АПГРЕЙДА

| # | Фича | Сложность | Описание |
|---|------|-----------|----------|
| 1 | **Запись token usage в main provider** | Low | Добавить вызов `add_token_usage()` в `litellm_provider.py` после `acompletion()` (по аналогии с Jeki) |
| 2 | **График "Стоимость запроса во времени"** | Med | Добавить pricing per model (OpenRouter API или локальная таблица), Plotly line chart |
| 3 | **Таблица "Топ дорогих сессий"** | Med | Расширить `add_token_usage` → писать session_id; новая таблица/агрегация; страница в Monitor |
| 4 | **Переключатель роутера в Settings** | Low | Добавить `router.enabled` в config; чекбокс в Settings; использовать в agent loop |
| 5 | **Алерты: "Расход превышен!"** | Low | Threshold в config; проверка в Monitor; `st.warning` / `st.error` при превышении |

### Дополнительно
- **Effort (итерации)** — Med: сохранять iteration count в token_usage или отдельную таблицу.
- **Fix Admin для dict config** — Low: использовать `config.get("agents", {}).get("defaults", {}).get("model")` как в Settings.

---

## 5️⃣ ТЕХНИЧЕСКИЙ СТАТУС

### Зависимости
- **pyproject.toml** `[dashboard]`: `streamlit>=1.33.0`, `pandas>=2.0.0`
- **Plotly** — не в зависимостях; используется только `st.line_chart` (встроенный).
- **requirements.txt** — dashboard-зависимости не включены. Нужно: `pip install -e ".[dashboard]"` или отдельно `streamlit pandas`.

### Конфиг
- Конфиг дашборда = `~/.nanobot/config.json` (Nanobot config).
- Отдельного конфига дашборда нет.

### Запуск
```bash
# Из корня проекта (с установленным nanobot)
streamlit run dashboard/main.py

# Или с указанием порта
streamlit run dashboard/main.py --server.port 8501
```
Команда не задокументирована в README.

---

## 6️⃣ РЕКОМЕНДАЦИЯ

**Стоит развивать этот дашборд.**

**Причины:**
1. Базовая структура (страницы, utils, fake data) уже есть.
2. Интеграция с memory.db и config есть; нужно только дописать provider и починить Admin.
3. Streamlit быстро даёт результат; миграция на React — отдельный большой проект.
4. Топ-5 идей в основном Low/Med; быстрый win — запись токенов и исправление Admin.

**Когда имеет смысл переписывать на React:**
- Нужен real-time WebSocket без перезагрузки страницы.
- Требуется сложная кастомизация UI (много интерактивных виджетов).
- Масштабирование на множество пользователей и сложная авторизация.

**Следующие шаги:**
1. Добавить `add_token_usage` в `litellm_provider.py`.
2. Исправить Admin для dict config.
3. Добавить `[dashboard]` в README как опциональную установку и команду запуска.
4. Внедрить топ-5 фич по приоритету.
