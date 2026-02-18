# RESEARCH: Pure LLM Navigator Agent (AI-only)

**Дата:** 2026-02-18  
**Контекст:** Nanobot Navigator (Штурман), гипотеза без rule-based логики

---

## TL;DR

Для подхода "чистый AI-навига́тор" лучший practical-топ сейчас:

1. **Llama-3.2-3B-Instruct** - лучший баланс instruction following + latency + доступность по API.
2. **Phi-3-mini-128k-instruct** - сильный long-context и суммаризация длинных диалогов.
3. **Qwen2.5-1.5B-Instruct** - сильная "малая" модель для edge/local, хороша в structured output и дешевой оркестрации.

Ключевой вывод: **SLM реально может тянуть intent extraction + goal drift + summarization**, но только при строгом prompt-контракте (JSON schema, few-shot, self-check, ограничение формата ответа).

---

## 1) Что SLM умеют "самостоятельно" в задачах Навигатора

### Задача A: Intent extraction из потока сообщений
- **Хорошо:** Llama-3.2-3B, Qwen2.5-1.5B, Phi-3-mini.
- **Условно:** Qwen2.5-0.5B, Gemma-2-2B (работают, но чаще теряют нюансы/ограничения).
- Главный фактор - не размер сам по себе, а **жесткий формат выхода** (слоты intent/goal/constraints).

### Задача B: Goal drift detection
- Реально решается, если модель не "угадывает свободным текстом", а выдает:
  - `current_goal`
  - `evidence_from_dialog`
  - `drift_score (0..1)`
  - `why_drift`
- На практике лучше всего по устойчивости: **Llama-3.2-3B** и **Phi-3-mini**.

### Задача C: Summarization длинного контекста
- Для длинного контекста критичен context window:
  - Qwen2.5: до 128K (линейка)
  - Llama-3.2 text models: до 128K (по model card)
  - Phi-3-mini-128k: 128K, отдельные long-context бенчмарки
- Лучший "чистый summarizer" из компактных: **Phi-3-mini-128k** (сильные long-context результаты).

---

## 2) Сравнение по бенчмаркам (Context Understanding + Instruction Following)

> Важно: это **не полностью apples-to-apples** (разные наборы и методики), но дает практическую картину.

| Модель | Instruction-following | Context/Understanding | Примечание |
|---|---:|---:|---|
| **Qwen2.5-0.5B-Instruct** | IFEval **27.9** | MMLU-Pro **15.0**, GSM8K **49.6** | Очень бюджетно, но слабый "контроллер" без сильного prompt scaffolding |
| **Qwen2.5-1.5B-Instruct** | IFEval **42.5** | MMLU-Pro **32.4**, GSM8K **73.2**, HumanEval **61.6** | Хороший edge-вариант для навигатора |
| **Llama-3.2-1B-Instruct (bf16)** | IFEval **59.5** | MMLU **49.3**, TLDR9+ ROUGE-L **16.8** | Лучше 0.5-1.5B класса по следованию инструкции |
| **Llama-3.2-3B-Instruct (bf16)** | IFEval **77.4** | MMLU **63.4**, TLDR9+ ROUGE-L **19.0**, NIH multi-needle **84.7** | Сильный baseline для AI-only навигатора |
| **Phi-3-mini-128k-instruct** | (internal instruction set, обновление: Instruction Challenge **42.3**) | MMLU **69.7**, GPQA **29.7**, RULER avg **84.6**, Long-context avg **25.9** | Сильная long-context модель в малом размере |
| **Gemma-2-2B-IT** | Human IF (single-sided) **26.5%** | MMLU IT **56.1** | Слабее по IF-метрикам относительно Llama-3.2-3B |

---

## 3) Промпт-инжиниринг для "Pure Navigator" (максимум из SLM)

### Что работает лучше всего
1. **System Prompt с жесткой ролью**  
   "Ты только навигатор, не исполнитель, не придумывай факты."

2. **Жесткий JSON-контракт**  
   Без свободного prose-ответа, только поля.

3. **Few-shot на drift cases**  
   2-4 примера "цель сохранена" vs "цель смещена".

4. **Chain-of-Thought как internal reasoning, не как verbose output**  
   Для продакшна: требовать краткую `rationale` на 1-2 предложения, а не длинные рассуждения.

5. **Self-check шаг в том же ответе**  
   Поле `uncertainty` + `missing_info`.

6. **Token budget enforcement**  
   Ограничивать summary по длине и структуре.

---

## 4) Латентность и стоимость (API + local)

## 4.1 API: что реально видно сейчас

### OpenRouter (публичный каталог моделей)
- `meta-llama/llama-3.2-3b-instruct`: **$0.02 / 1M input**, **$0.02 / 1M output**
- `meta-llama/llama-3.2-1b-instruct`: **$0.027 / 1M input**, **$0.20 / 1M output**
- В каталоге не найдены на момент проверки:
  - Qwen2.5-0.5B/1.5B Instruct
  - Phi-3-mini (4k/128k)
  - Gemma-2-2B-IT

### Together / другие провайдеры (по провайдерным метрикам Artificial Analysis для Llama-3.2)

| Модель/провайдер | Цена (in/out, $ за 1M токенов) | Median TTFT | Median output speed |
|---|---:|---:|---:|
| Llama-3.2-3B @ Together Turbo | 0.06 / 0.06 | **0.443s** | **117.64 tok/s** |
| Llama-3.2-3B @ DeepInfra | 0.02 / 0.02 | 0.376s | 22.19 tok/s |
| Llama-3.2-1B @ Amazon | 0.10 / 0.10 | 0.378s | 73.60 tok/s |
| Llama-3.2-1B @ DeepInfra | 0.005 / 0.01 | 0.404s | 21.24 tok/s |

---

## 4.2 Оценка стоимости "на одно сообщение"

Принято для расчета (типичный navigator вызов):
- Input: **2500 токенов** (контекст + история + state)
- Output: **220 токенов** (structured navigator JSON)

| Вариант | Стоимость / сообщение |
|---|---:|
| OpenRouter Llama-3.2-3B | **$0.000054** |
| OpenRouter Llama-3.2-1B | **$0.000111** |
| Together Llama-3.2-3B Turbo | **$0.000163** |
| DeepInfra Llama-3.2-1B | **$0.000015** |

Оценка total latency (грубо): `TTFT + output_tokens / output_tps`  
Пример Llama-3.2-3B:
- Together: `0.44 + 220/117.64 ~= 2.31s`
- DeepInfra: `0.38 + 220/22.19 ~= 10.29s`

---

## 4.3 Local (A100 80GB, официальный Qwen2.5 speed benchmark)

Из Qwen docs (batch=1, генерация 2048 токенов):
- **Qwen2.5-0.5B BF16**
  - Transformers: **47.40 tok/s**
  - vLLM: **311.55 tok/s**
- **Qwen2.5-1.5B BF16**
  - Transformers: **39.68 tok/s**
  - vLLM: **183.33 tok/s**

Для того же "2500 in + 220 out" (2720 токенов):
- 0.5B (vLLM): ~8.7s
- 1.5B (vLLM): ~14.8s

Если арендный A100 = ~$1.8/час:
- 0.5B (vLLM): ~$0.0044/сообщение
- 1.5B (vLLM): ~$0.0074/сообщение

Если GPU свой (электричество, условно 250W и $0.15/kWh):
- порядок ~$0.00009-0.00015/сообщение.

---

## 5) Топ-3 модели для "чистого AI-Навигатора"

## 1) **Llama-3.2-3B-Instruct**
**Почему #1:**
- Лучший instruction-following среди рассматриваемых малых моделей (IFEval 77.4).
- Реальные API-метрики TTFT/speed доступны.
- Хорошая устойчивость для drift detection и routing-подсказок.

**Риск:** уступает крупным моделям в сложном multi-hop reasoning.

## 2) **Phi-3-mini-128k-instruct**
**Почему #2:**
- Сильный long-context профиль (RULER, long-context benchmark в card).
- Хорошая база для summarization длинных сессий.

**Риск:** меньше прозрачных актуальных провайдерных метрик latency/price в публичных агрегаторах.

## 3) **Qwen2.5-1.5B-Instruct**
**Почему #3:**
- Очень сильный "малый" профиль для edge/local (IFEval 42.5, GSM8K 73.2, HumanEval 61.6).
- Отличный throughput в local vLLM.

**Риск:** меньше открытых провайдерных latency-срезов по API именно для 1.5B варианта.

---

## 6) Пример "идеального" system prompt для Navigator SLM

```text
You are NAVIGATOR, a planning-and-alignment module for a larger assistant.
Your job is to analyze dialogue context and output a compact navigation plan.

Hard rules:
1) Do NOT execute tasks, do NOT invent facts.
2) Ground every conclusion in the provided messages.
3) If evidence is insufficient, state uncertainty explicitly.
4) Output STRICT JSON only (no markdown, no prose).
5) Keep output concise (<= 220 tokens).

Primary objectives:
- Extract user intent and current goal.
- Detect goal drift from prior goal.
- Produce short context summary for the main model.
- Suggest next best action for the main model.

Return JSON schema:
{
  "intent": "...",
  "current_goal": "...",
  "goal_drift": {
    "score_0_to_1": 0.0,
    "is_drift": false,
    "evidence": ["...", "..."]
  },
  "context_summary": ["bullet1", "bullet2", "bullet3"],
  "constraints": ["..."],
  "missing_info": ["..."],
  "next_action_for_main_model": "...",
  "confidence_0_to_1": 0.0
}
```

---

## 7) Риски подхода AI-only

1. **Галлюцинации в drift detection**  
   Модель "додумает" смещение цели без достаточных доказательств.

2. **Непредсказуемость формата**  
   Без JSON schema и валидации модель начинает "болтать".

3. **Потеря критичных деталей при summarization**  
   Особенно на маленьких моделях при длинной истории.

4. **Prompt-injection из пользовательского контекста**  
   Navigator может принять вредный meta-instruction из истории.

5. **Сильная зависимость от провайдера по latency**  
   Одинаковая модель у разных провайдеров может отличаться в 3-5x по total latency.

---

## 8) Практическая рекомендация для Nanobot

1. **Стартовый прод baseline:** Llama-3.2-3B-Instruct как Navigator.  
2. **Long-context режим:** переключение на Phi-3-mini-128k для длинных сессий/саммаризации.  
3. **Edge/cheap режим:** Qwen2.5-1.5B-Instruct локально (vLLM).  
4. Обязательно добавить:
   - JSON schema validator
   - drift threshold (например 0.65)
   - fallback на rule-based guardrails при low confidence
   - offline eval set: intent extraction, drift detection, summary faithfulness.

---

## Источники

1. OpenRouter Models API (`/api/v1/models`) - pricing/availability.  
2. Artificial Analysis provider pages (Llama-3.2 1B/3B) - TTFT, output speed, per-provider pricing.  
3. Qwen2.5 Technical Report (arXiv:2412.15115), таблица 0.5B-1.5B instruct.  
4. Qwen docs v2.5 speed benchmark (A100, transformers/vLLM).  
5. Llama 3.2 public model card (meta-llama GitHub, `llama3_2/MODEL_CARD.md`).  
6. Phi-3-mini-4k / 128k model cards (Microsoft HF).  
7. Gemma 2 technical report (arXiv:2408.00118).

