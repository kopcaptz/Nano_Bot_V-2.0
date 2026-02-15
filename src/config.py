"""Configuration loading and validation for Nano Bot V-2.0."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Config:
    """Runtime configuration values."""

    telegram_bot_token: str
    openrouter_api_key: str
    openrouter_model: str
    llm_context_max_messages: int
    memory_max_messages: int
    handler_max_command_length: int
    llm_request_timeout_seconds: float
    system_command_timeout_seconds: float
    adapter_start_timeout_seconds: float
    adapter_stop_timeout_seconds: float
    agent_workspace: Path
    log_level: str


def _normalize_log_level(raw_level: str) -> int:
    """Convert string log level into logging constant."""
    name = (raw_level or "INFO").upper()
    return getattr(logging, name, logging.INFO)


def _resolve_workspace_path(raw_path: str) -> Path:
    """
    Resolve workspace path with cross-platform guard.

    On POSIX, a Windows-style path (e.g. C:\\Users\\...) is treated as invalid
    runtime value and replaced by a safe default workspace path.
    """
    if os.name != "nt" and re.match(r"^[A-Za-z]:\\", raw_path):
        fallback = Path.cwd() / "workspace"
        logging.warning(
            "AGENT_WORKSPACE looks like Windows path on POSIX (%s). "
            "Using fallback workspace: %s",
            raw_path,
            fallback,
        )
        return fallback

    return Path(raw_path).expanduser()


def _parse_positive_int(raw_value: str | None, default: int, name: str) -> int:
    """Parse positive integer config value with safe fallback."""
    if raw_value is None or not raw_value.strip():
        return default
    try:
        parsed = int(raw_value.strip())
    except ValueError:
        logging.warning("%s must be integer. Using default: %d", name, default)
        return default
    if parsed <= 0:
        logging.warning("%s must be > 0. Using default: %d", name, default)
        return default
    return parsed


def _parse_positive_float(raw_value: str | None, default: float, name: str) -> float:
    """Parse positive float config value with safe fallback."""
    if raw_value is None or not raw_value.strip():
        return default
    try:
        parsed = float(raw_value.strip())
    except ValueError:
        logging.warning("%s must be float. Using default: %.1f", name, default)
        return default
    if parsed <= 0:
        logging.warning("%s must be > 0. Using default: %.1f", name, default)
        return default
    return parsed


def load_config() -> Config:
    """Load config values from .env and validate critical paths/settings."""
    load_dotenv()

    log_level = os.getenv("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=_normalize_log_level(log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    workspace_raw = os.getenv("AGENT_WORKSPACE", str(Path.cwd() / "workspace"))
    workspace_path = _resolve_workspace_path(workspace_raw)
    workspace_path.mkdir(parents=True, exist_ok=True)

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not telegram_token:
        logging.warning("TELEGRAM_BOT_TOKEN is empty. Telegram adapter will not start.")

    openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not openrouter_api_key:
        logging.warning("OPENROUTER_API_KEY is empty. LLM requests will fail.")

    openrouter_model = os.getenv("OPENROUTER_MODEL", "kimi/kimi-k2.5").strip()
    if not openrouter_model:
        openrouter_model = "kimi/kimi-k2.5"
        logging.warning("OPENROUTER_MODEL is empty. Falling back to kimi/kimi-k2.5.")

    llm_context_max_messages = _parse_positive_int(
        os.getenv("LLM_CONTEXT_MAX_MESSAGES"),
        default=40,
        name="LLM_CONTEXT_MAX_MESSAGES",
    )
    memory_max_messages = _parse_positive_int(
        os.getenv("MEMORY_MAX_MESSAGES"),
        default=200,
        name="MEMORY_MAX_MESSAGES",
    )
    handler_max_command_length = _parse_positive_int(
        os.getenv("HANDLER_MAX_COMMAND_LENGTH"),
        default=8000,
        name="HANDLER_MAX_COMMAND_LENGTH",
    )
    llm_request_timeout_seconds = _parse_positive_float(
        os.getenv("LLM_REQUEST_TIMEOUT_SECONDS"),
        default=45.0,
        name="LLM_REQUEST_TIMEOUT_SECONDS",
    )
    system_command_timeout_seconds = _parse_positive_float(
        os.getenv("SYSTEM_COMMAND_TIMEOUT_SECONDS"),
        default=20.0,
        name="SYSTEM_COMMAND_TIMEOUT_SECONDS",
    )
    adapter_start_timeout_seconds = _parse_positive_float(
        os.getenv("ADAPTER_START_TIMEOUT_SECONDS"),
        default=20.0,
        name="ADAPTER_START_TIMEOUT_SECONDS",
    )
    adapter_stop_timeout_seconds = _parse_positive_float(
        os.getenv("ADAPTER_STOP_TIMEOUT_SECONDS"),
        default=10.0,
        name="ADAPTER_STOP_TIMEOUT_SECONDS",
    )

    return Config(
        telegram_bot_token=telegram_token,
        openrouter_api_key=openrouter_api_key,
        openrouter_model=openrouter_model,
        llm_context_max_messages=llm_context_max_messages,
        memory_max_messages=memory_max_messages,
        handler_max_command_length=handler_max_command_length,
        llm_request_timeout_seconds=llm_request_timeout_seconds,
        system_command_timeout_seconds=system_command_timeout_seconds,
        adapter_start_timeout_seconds=adapter_start_timeout_seconds,
        adapter_stop_timeout_seconds=adapter_stop_timeout_seconds,
        agent_workspace=workspace_path,
        log_level=log_level,
    )

