# Отчёт: MVP Smart Model Router

**Дата:** 18 февраля 2026  
**Ветка:** cursor/llm-3172

---

## 1. КОД — ИЗМЕНЕНИЯ

### Новые файлы

#### `nanobot/agent/model_router.py`
- Функция `get_model_for_request(query, is_background, config)` — эвристический выбор модели
- Правила: is_background → free-model; keywords_smart → smart-model; короткий запрос → cheap-model

#### `nanobot/providers/litellm_router_provider.py`
- `LiteLLMRouterProvider` — провайдер с LiteLLM Router + эвристиками
- Использует `litellm.Router` с `model_list`, `fallbacks`
- В `chat()` вызывает `get_model_for_request()`, затем `router.acompletion()`

#### `tests/test_model_router.py`
- Тесты эвристик: Complex → smart, Simple → cheap, Background → free

### Изменённые файлы

#### `nanobot/config/schema.py`
- `ModelRouterConfig`, `ModelRouterModelConfig`, `ModelRouterRoutingRules`
- `Config.model_router: ModelRouterConfig | None`

#### `nanobot/providers/base.py`
- `chat()` — добавлен параметр `metadata: dict | None = None`

#### `nanobot/providers/litellm_provider.py`
- `chat()` — добавлен `metadata` (игнорируется)

#### `nanobot/cli/commands.py`
- `_make_provider()` — при `model_router.enabled` возвращает `LiteLLMRouterProvider`

#### `nanobot/agent/loop.py`
- Вызовы `provider.chat()` — добавлен `metadata={"is_background": True/False}`

#### `nanobot/agent/subagent.py`
- `provider.chat()` — добавлен `metadata={"is_background": True}`

---

## 2. КОНФИГ

### Пример `config.json` (merge в ~/.nanobot/config.json)

```json
{
  "modelRouter": {
    "enabled": true,
    "routingStrategy": "cost-based-routing",
    "models": [
      {
        "modelName": "smart-model",
        "litellmParams": { "model": "anthropic/claude-3-5-sonnet-20241022" },
        "tpm": 100000,
        "rpm": 100
      },
      {
        "modelName": "cheap-model",
        "litellmParams": { "model": "qwen/qwen3.5-plus-02-15" },
        "tpm": 200000,
        "rpm": 300
      },
      {
        "modelName": "free-model",
        "litellmParams": { "model": "openrouter/aurora-alpha" },
        "tpm": 50000,
        "rpm": 50
      }
    ],
    "fallbacks": [
      { "smart-model": "cheap-model" },
      { "cheap-model": "free-model" }
    ],
    "routingRules": {
      "keywordsSmart": ["code", "debug", "architecture", "error", "fix", "bug", "код", "дебаг", "архитектура", "ошибка"],
      "maxWordsCheap": 50
    }
  }
}
```

Полный пример: `docs/example_model_router_config.json`

---

## 3. ЛОГИ — ПРИМЕР ВЫВОДА

```
2026-02-18 18:06:15 | INFO | Routing: [Complex] -> smart-model (Reason: keywords matched)
2026-02-18 18:06:15 | INFO | Routing: [Simple] -> cheap-model (Reason: 3 words <= 50)
2026-02-18 18:06:15 | INFO | Routing: [Background] -> free-model (Reason: is_background=True)
2026-02-18 18:06:15 | INFO | Routing: [Default] -> cheap-model (Reason: no keywords, 72 words)
```

---

## 4. СТАТУС

### Работает
- [x] Конфиг `model_router` в schema
- [x] Эвристики: код/debug/архитектура → Claude
- [x] Короткий запрос (<50 слов) → Qwen
- [x] is_background (subagent, system message) → Aurora
- [x] LiteLLM Router с fallbacks
- [x] Логирование: `Routing: [Type] -> model (Reason: ...)`
- [x] Отключение: `model_router.enabled=false` → обычный LiteLLMProvider
- [x] Unit-тесты эвристик

### Требует проверки с реальным API
- [ ] Тест 1: «Напиши функцию на Python для сортировки» → Claude (smart-model)
- [ ] Тест 2: «Привет, как дела?» → Qwen (cheap-model)
- [ ] Тест 3: Subagent/системное сообщение → Aurora (free-model)
- [ ] Fallback: отключение Claude → переключение на Qwen

### Потенциальные доработки
- Роутинг для Reflection, SkillGenerator, Crystallize (сейчас используют default model)
- `provider_budget_config` для лимитов бюджета
- `chosen_model` в `LLMResponse` для телеметрии
