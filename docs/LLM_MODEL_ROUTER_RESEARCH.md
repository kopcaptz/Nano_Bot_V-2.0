# Исследование: Model Router для Nanobot (LiteLLM)

**Дата:** 18 февраля 2026  
**Ветка:** cursor/llm-3172

---

## 1️⃣ АРХИТЕКТУРНЫЙ АНАЛИЗ

### Где выбирается модель сейчас

| Компонент | Файл | Логика выбора модели |
|-----------|------|----------------------|
| **AgentLoop** | `nanobot/agent/loop.py` | `self.model = model or provider.get_default_model()` при инициализации. Модель **фиксирована** на всё время жизни агента. Используется во всех 4 вызовах `provider.chat(..., model=self.model)` (строки 246, 398, 534, 694) |
| **ContextBuilder** | `nanobot/agent/context.py` | **Нет** выбора модели. Только сборка промптов и сообщений |
| **SkillManager** | `nanobot/agent/skill_manager.py` | **Нет** выбора модели. Управление навыками, векторный поиск |
| **SubagentManager** | `nanobot/agent/subagent.py` | Получает `model` из конструктора AgentLoop (`model=self.model`). Использует одну и ту же модель для всех subagents |
| **Reflection** | `nanobot/agent/reflection.py` | `model=self.model` — та же модель |
| **SkillGenerator** | `nanobot/agent/skill_generator.py` | `model=self.model` — та же модель |

### Как передаётся model

1. **Конфиг:** `config.agents.defaults.model` (schema: `AgentDefaults.model = "anthropic/claude-opus-4-5"`)
2. **CLI:** `nanobot/cli/commands.py` → `AgentLoop(..., model=config.agents.defaults.model)`
3. **Provider:** `LiteLLMProvider(default_model=model)` — один default_model
4. **Нет env-переменной** для модели в schema (есть только для Discord и пр.)

### Можно ли внедрить прослойку-роутер без поломки логики?

**Да.** Точки входа для роутера:

- **Вариант A (минимальный):** Заменить `LiteLLMProvider` на обёртку `SmartRouterProvider`, которая наследует `LLMProvider`, внутри выбирает модель и вызывает `LiteLLMProvider.chat()`.
- **Вариант B (LiteLLM Router):** Создать `litellm.Router` с `model_list`, передавать в `acompletion` через роутер вместо прямого `acompletion`. AgentLoop продолжает вызывать `provider.chat()` — provider скрывает роутинг.
- **Вариант C (гибрид):** AgentLoop получает `get_model_for_message(msg) -> str` callback; перед каждым вызовом LLM вызывается callback с `current_message` — максимальная гибкость.

---

## 2️⃣ LiteLLM Router (готовое решение)

### Версия

- **pyproject.toml:** `litellm>=1.0.0`
- **Установленная:** 1.81.13 (через pip)
- **Router:** `from litellm import Router` — есть и работает

### Поддержка routing_strategy

```python
routing_strategy: Literal[
    "simple-shuffle",       # случайный выбор из model_list
    "least-busy",           # наименее загруженный
    "usage-based-routing",  # по использованию
    "latency-based-routing", # по латентности
    "cost-based-routing",   # по стоимости
    "usage-based-routing-v2",
] = "simple-shuffle"
```

### Конфигурация model_list

```python
model_list = [
    {
        "model_name": "gpt-4",  # алиас для выбора
        "litellm_params": {
            "model": "gpt-4",
            "api_key": "...",
            # или "anthropic/claude-3" для OpenRouter
        },
        "model_info": {"max_tokens": 100000},  # опционально
    },
]
```

### Fallbacks и context_window_fallbacks

- **fallbacks:** `[{"model-a": "model-b"}]` — при ошибке model-a пробовать model-b
- **context_window_fallbacks:** при превышении context window — автоматически переключиться на модель с большим окном

### config.json — как описать model_router

Текущая структура Config не содержит `model_router`. Нужно добавить:

```json
{
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5"
    }
  },
  "modelRouter": {
    "enabled": true,
    "modelList": [
      {
        "modelName": "claude-complex",
        "litellmParams": { "model": "anthropic/claude-sonnet-4" },
        "modelInfo": { "maxTokens": 200000 }
      },
      {
        "modelName": "qwen-simple",
        "litellmParams": { "model": "qwen/qwen3-237b" },
        "modelInfo": { "maxTokens": 32768 }
      }
    ],
    "routingStrategy": "cost-based-routing",
    "fallbacks": [{"claude-complex": "qwen-simple"}],
    "contextWindowFallbacks": []
  }
}
```

### Плюсы встроенного LiteLLM Router

- Готовый fallback, retry, context_window_fallbacks
- cost-based-routing, least-busy — полезно для бюджета
- Совместим с текущим `acompletion`

### Минусы

- **Нет routing по содержанию запроса** — Router выбирает по load/cost/latency, но не по "сложность" или "код vs привет"
- Для "умного" роутинга (сложность vs простой запрос) нужно либо:
  - свой слой поверх Router (подход C с metadata),
  - либо классификатор (подход B)

---

## 3️⃣ СТРАТЕГИИ РОУТИНГА — ОЦЕНКА

### A. Правила на основе ключевых слов (Regex)

- **Идея:** "код", "bug", "напиши" → Claude; "привет", "как дела" → Qwen/gpt-4o-mini
- **Плюсы:** Просто, быстро, без доп. вызовов
- **Минусы:** Глупо, ложные срабатывания, не масштабируется
- **Оценка:** ⭐⭐ — только как MVP для proof-of-concept

### B. Классификатор на мини-модели

- **Идея:** Сначала дешёвая модель (gpt-4o-mini / qwen-flash) оценивает сложность 1–5, затем выбирается основная
- **Плюсы:** Умно, гибко
- **Минусы:** +1 вызов LLM (задержка ~200–500 ms, стоимость ~$0.0001 за запрос)
- **Оценка:** ⭐⭐⭐ — имеет смысл при высоком объёме и желании экономить на простых запросах

### C. LiteLLM Router + metadata (рекомендуемый)

- **Идея:** Передавать в `metadata`/доп. параметры информацию о запросе. Использовать `cost-based-routing` или `usage-based-routing` для бюджета. Для "умного" выбора — тонкий слой: перед вызовом решать модель по эвристикам (длина, наличие tool_calls в history, кол-во итераций) **без** дополнительного вызова LLM.
- **Плюсы:** Компромисс: не нужен классификатор, но можно добавить простые эвристики (длина > 500 символов + "код" → Claude)
- **Минусы:** Эвристики менее точны, чем B
- **Оценка:** ⭐⭐⭐⭐ — оптимально для старта

---

## 4️⃣ РИСКИ И "ПОДВОДНЫЕ КАМЕНЬ"

### Потеря контекста при смене модели

- **Проблема:** Сессия началась на Qwen, середина — на Claude. Разная токенизация, разный стиль ответов.
- **Митигация:** Роутить **на уровне сообщения**, а не на уровне сессии. Либо использовать **одну модель на сессию** (выбор при первом сообщении), либо явно передавать в system prompt: "Ты продолжаешь диалог, начатый другой моделью".
- **Рекомендация:** Для начала — **одна модель на сессию** (session_key → model cache). Смена модели только при новой сессии или при явном fallback (ошибка, context overflow).

### Race conditions (subagents)

- **Проблема:** Несколько subagents одновременно — каждый вызывает provider.chat(). Если роутер stateful (least-busy, usage-based), возможны коллизии.
- **Анализ:** LiteLLM Router **thread-safe** — состояние в Redis или in-memory, обновляется атомарно. `usage-based-routing` и `least-busy` рассчитаны на конкурентные вызовы.
- **Риск:** Низкий при использовании встроенного Router.

### Отладка — chosen_model_reason

- **Проблема:** Нужно логировать, почему выбрана модель.
- **Решение:** Добавить в `LLMResponse` поле `chosen_model`, в provider — логировать перед return:  
  `logger.info("chosen_model", model=model, reason=reason, messages_preview=...)`

### Бюджет

- **Проблема:** Роутер может направить сложные задачи на дорогую модель.
- **Решение:**  
  - `cost-based-routing` — предпочитает дешёвые модели  
  - `provider_budget_config` в Router — лимиты по провайдеру  
  - Кастомная логика: при `iteration > 5` или `len(messages) > 50` — принудительно дешёвая модель (или отказ)

---

## 5️⃣ ПЛАН РЕАЛИЗАЦИИ (ROADMAP)

### Phase 0: Prep (15–20 мин)

- [ ] Обновить litellm до `>=1.50.0` (уже 1.81.13 — ок)
- [ ] Добавить тест: `Router(model_list=[...]).acompletion(model="gpt-4", messages=[...])`
- [ ] Проверить совместимость с текущим LiteLLMProvider

### Phase 1: Config (20–30 мин)

- [ ] Добавить в `nanobot/config/schema.py`: `ModelRouterConfig` с `model_list`, `routing_strategy`, `fallbacks`, `enabled`
- [ ] Обновить `Config` — поле `model_router: ModelRouterConfig | None`
- [ ] В `loader.py` — читать `modelRouter` из config.json (camelCase → snake_case)

### Phase 2: Core (45–60 мин)

- [ ] Создать `SmartRouter` или `LiteLLMRouterProvider(LLMProvider)`:
  - При `model_router.enabled=False` — поведение как сейчас (прямой LiteLLMProvider)
  - При `enabled=True` — создавать `litellm.Router`, в `chat()` вызывать `router.acompletion(**kwargs)` вместо `litellm.acompletion`
- [ ] Передавать `model` из AgentLoop — как "model group" для Router (если указан в model_list) или default

### Phase 3: Integration (30–40 мин)

- [ ] В `_make_provider()` — если config.model_router.enabled, возвращать `LiteLLMRouterProvider`, иначе `LiteLLMProvider`
- [ ] AgentLoop — без изменений (продолжает передавать model в provider.chat)
- [ ] Опционально: callback `get_model(messages, session_key)` для кастомного роутинга

### Phase 4: Telemetry (20–30 мин)

- [ ] В `LLMResponse` добавить `chosen_model: str | None`, `routing_reason: str | None`
- [ ] В Router provider — извлекать `model` из response (litellm возвращает в metadata) и логировать
- [ ] `logger.info("llm_call", model=..., chosen_model=..., reason=..., cost_estimate=...)`

### Phase 5: Testing (30 мин)

- [ ] Сценарий "привет" — дешёвая модель (если cost-based)
- [ ] Сценарий "напиши код на Python" — дорогая модель
- [ ] Fallback: отключить основную модель — убедиться, что срабатывает fallback
- [ ] Subagent — проверить, что роутинг работает в фоне

---

## 6️⃣ ВЕРДИКТ И РЕКОМЕНДАЦИИ

### Вердикт по времени

- **Минимальный MVP (только LiteLLM Router с fallbacks):** **1–2 часа**
- **С конфигом, telemetry, тестами:** **4–6 часов**
- **С умным роутингом (эвристики по содержанию):** **1–2 дня**
- **С классификатором (подход B):** **2–3 дня**

### Рекомендация: Подход C (LiteLLM Router + простые эвристики)

1. Внедрить LiteLLM Router с `model_list`, `fallbacks`, `context_window_fallbacks`.
2. Использовать `cost-based-routing` по умолчанию.
3. Добавить опциональный слой: `get_model_for_message(msg) -> str` с эвристиками (длина, ключевые слова) — для тех, кто хочет "код → Claude".
4. Логировать `chosen_model` и `reason`.

---

## 7️⃣ КОД-СНИППЕТЫ

### Пример конфига (config.json)

```json
{
  "agents": {
    "defaults": {
      "model": "claude-sonnet",
      "maxTokens": 8192
    }
  },
  "modelRouter": {
    "enabled": true,
    "modelList": [
      {
        "modelName": "claude-sonnet",
        "litellmParams": {
          "model": "anthropic/claude-sonnet-4",
          "api_key": "${ANTHROPIC_API_KEY}"
        },
        "modelInfo": { "maxTokens": 200000 }
      },
      {
        "modelName": "qwen-simple",
        "litellmParams": {
          "model": "qwen/qwen3-237b",
          "api_key": "${OPENROUTER_API_KEY}"
        },
        "modelInfo": { "maxTokens": 32768 }
      }
    ],
    "routingStrategy": "cost-based-routing",
    "fallbacks": [{ "claude-sonnet": "qwen-simple" }],
    "contextWindowFallbacks": []
  }
}
```

### Пример вызова роутера (псевдокод)

```python
# nanobot/providers/router_provider.py (новый файл)

from litellm import Router
from nanobot.providers.base import LLMProvider, LLMResponse
from nanobot.providers.litellm_provider import LiteLLMProvider

class LiteLLMRouterProvider(LLMProvider):
    def __init__(self, model_list: list, routing_strategy: str = "cost-based-routing", **kwargs):
        self._router = Router(
            model_list=model_list,
            routing_strategy=routing_strategy,
            fallbacks=kwargs.get("fallbacks", []),
            context_window_fallbacks=kwargs.get("context_window_fallbacks", []),
        )
        self._fallback_provider = LiteLLMProvider(**kwargs)  # если Router отключен

    async def chat(self, messages, tools=None, model=None, **kwargs) -> LLMResponse:
        model = model or self.get_default_model()
        # Router использует model как "model_name" из model_list
        response = await self._router.acompletion(
            model=model,
            messages=messages,
            tools=tools,
            **kwargs,
        )
        return self._parse_response(response)
```

---

## 8️⃣ ЧЕК-ЛИСТ РИСКОВ

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Потеря контекста при смене модели | Средняя | Одна модель на сессию |
| Race conditions (subagents) | Низкая | LiteLLM Router thread-safe |
| Роутер "прожигает" бюджет | Средняя | cost-based-routing + provider_budget_config |
| Нет логов выбора модели | Высокая (если не сделать) | Добавить chosen_model, reason в логи |
| Регрессия при отключении роутера | Низкая | Feature flag `model_router.enabled` |
| Несовместимость config.json | Средняя | Миграция _migrate_config в loader |
| Конфликт с существующим src/core/llm_router.py | Низкая | Другой модуль (OpenRouter commands), другое назначение |

---

## 9️⃣ ПОШАГОВЫЙ ПЛАН ДЛЯ CURSOR-АГЕНТА

1. **Создать ветку** (уже cursor/llm-3172)
2. **Phase 0:** Запустить `pytest tests/` — убедиться, что всё зелёное
3. **Phase 1:** Добавить `ModelRouterConfig` в schema, обновить loader
4. **Phase 2:** Создать `LiteLLMRouterProvider` в `nanobot/providers/`
5. **Phase 3:** В `_make_provider()` — условно возвращать Router provider
6. **Phase 4:** Добавить логирование chosen_model
7. **Phase 5:** Написать тест `test_router_fallback` и `test_router_cost_based`
8. **Commit & Push** после каждой фазы
