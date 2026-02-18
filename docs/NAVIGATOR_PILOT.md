# Hybrid Navigator Pilot Runbook

## 1) Enable pilot in config

Edit `~/.nanobot/config.json` and ensure:

```json
{
  "navigator": {
    "enabled": true,
    "mode": "hybrid",
    "model": "qwen-2.5-1.5b-instruct",
    "thresholds": {
      "complexityLow": 0.3,
      "complexityHigh": 0.75
    },
    "canaryPercent": 0,
    "slmTimeoutSeconds": 2.0,
    "logPath": "logs/navigator_pilot.jsonl"
  }
}
```

Notes:
- `mode: "off"` disables navigator fully.
- `mode: "pure_ai"` bypasses navigator (control path).
- `canaryPercent: 0` means full hybrid traffic (no canary gating).

## 2) Start nanobot

```bash
nanobot gateway
```

Or for direct CLI checks:

```bash
nanobot agent -m "Привет"
nanobot agent -m "У меня ошибка в коде, не понимаю как исправить, вот лог..."
```

## 3) Verify expected routing behavior

- Simple short message should usually map to `TEMPLATE` (or `NO_ACTION` if cooldown triggered).
- Medium complexity / guidance messages should map to `SLM` and add `<navigator_hint>` to system prompt.
- High complexity should map to `FALLBACK`.

## 4) Where to inspect logs

Navigator pilot events are written to:

`logs/navigator_pilot.jsonl`

Each line is JSON with fields:
- `ts`
- `conversation_id` (hashed)
- `route`
- `complexity_score`
- `tags`
- `model`
- `tokens_in`
- `tokens_out`
- `latency_ms`
- `cost_usd`
- `tokens_saved_est`

## 5) Dashboard

Run Streamlit dashboard and open the main page:

```bash
streamlit run dashboard/main.py
```

The dashboard reads `logs/navigator_pilot.jsonl` and shows:
- route mix (%)
- estimated token savings
- average navigator latency
