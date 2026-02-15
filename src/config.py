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

    if not os.getenv("OPENROUTER_API_KEY", "").strip():
        logging.warning("OPENROUTER_API_KEY is empty. LLM requests will fail.")

    return Config(
        telegram_bot_token=telegram_token,
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "kimi/kimi-k2.5").strip(),
        agent_workspace=workspace_path,
        log_level=log_level,
    )

