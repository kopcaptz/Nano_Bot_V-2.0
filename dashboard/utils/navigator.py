"""Navigator pilot metrics helpers for Streamlit dashboard."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def _cfg_get(config: Any, keys: list[str], default: Any = None) -> Any:
    """Read nested values from dict-like or pydantic-like config objects."""
    current = config
    for key in keys:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key)
        else:
            current = getattr(current, key, None)
    return default if current is None else current


def resolve_navigator_log_path(config: Any = None) -> Path:
    """Resolve navigator pilot log path from config with fallbacks."""
    configured = _cfg_get(config, ["navigator", "log_path"], "logs/navigator_pilot.jsonl")
    configured_path = Path(str(configured)).expanduser()

    if configured_path.is_absolute():
        return configured_path

    candidates = [Path.cwd() / configured_path]
    workspace = _cfg_get(config, ["agents", "defaults", "workspace"], None)
    if workspace:
        candidates.append(Path(str(workspace)).expanduser() / configured_path)
    candidates.append(Path.home() / ".nanobot" / configured_path)

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def load_navigator_events(limit: int = 2000, config: Any = None) -> list[dict[str, Any]]:
    """Load navigator events from JSONL, returning recent events only."""
    log_path = resolve_navigator_log_path(config)
    if not log_path.exists():
        return []

    events: list[dict[str, Any]] = []
    try:
        with log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    events.append(data)
    except OSError:
        return []

    if limit > 0:
        return events[-limit:]
    return events


def get_navigator_session_metrics(config: Any = None, limit: int = 2000) -> dict[str, Any]:
    """Compute route mix, estimated token savings, and average latency."""
    events = load_navigator_events(limit=limit, config=config)
    if not events:
        return {
            "events": 0,
            "route_counts": {},
            "route_mix": {},
            "tokens_saved_est": 0,
            "avg_latency": 0.0,
            "log_path": str(resolve_navigator_log_path(config)),
        }

    route_counts = Counter(str(item.get("route", "UNKNOWN")) for item in events)
    total = len(events)
    route_mix = {
        route: round((count / total) * 100, 2)
        for route, count in sorted(route_counts.items(), key=lambda item: item[0])
    }

    tokens_saved_est = sum(int(item.get("tokens_saved_est", 0) or 0) for item in events)
    latencies = [float(item.get("latency_ms", 0.0) or 0.0) for item in events]
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

    return {
        "events": total,
        "route_counts": dict(route_counts),
        "route_mix": route_mix,
        "tokens_saved_est": tokens_saved_est,
        "avg_latency": avg_latency,
        "log_path": str(resolve_navigator_log_path(config)),
    }
