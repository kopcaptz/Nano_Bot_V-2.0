"""Smart model router with heuristic-based selection."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from nanobot.config.schema import ModelRouterConfig


def get_model_for_request(
    query: str,
    is_background: bool,
    config: "ModelRouterConfig | None",
) -> str | None:
    """
    Select model based on heuristics. Returns model_name from config or None if routing disabled.

    Rules:
    - is_background=True -> free-model (Aurora)
    - keywords_smart in query -> smart-model (Claude)
    - short query (< max_words_cheap words) -> cheap-model (Qwen)
    - else -> cheap-model (default for simple)

    Returns:
        Model name (e.g. "smart-model", "cheap-model", "free-model") or None.
    """
    if not config or not config.enabled or not config.models:
        return None

    rules = config.routing_rules
    model_names = {m.model_name for m in config.models}

    # Map role to model name (must exist in config)
    smart_name = "smart-model" if "smart-model" in model_names else (config.models[0].model_name if config.models else "smart-model")
    cheap_name = "cheap-model" if "cheap-model" in model_names else (config.models[1].model_name if len(config.models) > 1 else smart_name)
    free_name = "free-model" if "free-model" in model_names else (config.models[2].model_name if len(config.models) > 2 else cheap_name)

    # Ensure we use names that exist
    available = [m.model_name for m in config.models]
    if smart_name not in available:
        smart_name = available[0] if available else smart_name
    if cheap_name not in available:
        cheap_name = available[1] if len(available) > 1 else available[0] if available else cheap_name
    if free_name not in available:
        free_name = available[2] if len(available) > 2 else cheap_name

    query_lower = (query or "").lower().strip()
    word_count = len(re.findall(r"\S+", query_lower))

    # 1. Background tasks -> free model
    if is_background:
        logger.info(f"Routing: [Background] -> {free_name} (Reason: is_background=True)")
        return free_name

    # 2. Keywords for complex tasks -> smart model (Claude)
    keywords = [k.lower() for k in rules.keywords_smart]
    if any(kw in query_lower for kw in keywords):
        logger.info(f"Routing: [Complex] -> {smart_name} (Reason: keywords matched)")
        return smart_name

    # 3. Short simple query -> cheap model (Qwen)
    if word_count <= rules.max_words_cheap:
        logger.info(f"Routing: [Simple] -> {cheap_name} (Reason: {word_count} words <= {rules.max_words_cheap})")
        return cheap_name

    # 4. Default for longer queries without keywords -> cheap model
    logger.info(f"Routing: [Default] -> {cheap_name} (Reason: no keywords, {word_count} words)")
    return cheap_name
