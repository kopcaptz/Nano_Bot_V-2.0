"""Bridge to nanobot gateway for agent mode tasks.

In Hybrid Mode, when the main bot detects a complex task (code, files, multi-step),
it delegates to the nanobot agent via this bridge. The agent runs in-process
using AgentLoop.process_direct() — no subprocess.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_agent_loop: Any = None
_agent_lock = asyncio.Lock()


def _create_provider_from_env() -> Any:
    """Create LiteLLMProvider from OPENROUTER_* env vars (fallback when nanobot config missing)."""
    from nanobot.providers.litellm_provider import LiteLLMProvider

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet").strip()
    if not model:
        model = "anthropic/claude-3.5-sonnet"

    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set. Configure it in .env or ~/.nanobot/config.json"
        )

    return LiteLLMProvider(
        api_key=api_key,
        api_base="https://openrouter.ai/api/v1",
        default_model=model,
        extra_headers=None,
        provider_name="openrouter",
    )


def _create_provider_from_nanobot_config(config: Any) -> Any:
    """Create LiteLLMProvider from nanobot config."""
    from nanobot.providers.litellm_provider import LiteLLMProvider

    p = config.get_provider()
    model = config.agents.defaults.model
    if not (p and p.api_key) and not model.startswith("bedrock/"):
        return None

    return LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=config.get_provider_name(),
    )


async def _get_agent_loop(workspace_override: Path | None = None) -> Any:
    """Lazily create AgentLoop. Uses nanobot config when available, else env fallback."""
    global _agent_loop
    async with _agent_lock:
        if _agent_loop is not None:
            return _agent_loop

        try:
            from nanobot.bus.queue import MessageBus
            from nanobot.agent.loop import AgentLoop
            from nanobot.session.manager import SessionManager

            bus = MessageBus()
            workspace: Path
            provider: Any

            # Try nanobot config first
            try:
                from nanobot.config.loader import load_config

                nb_config = load_config()
                provider = _create_provider_from_nanobot_config(nb_config)
                if provider is not None:
                    workspace = workspace_override or nb_config.workspace_path
                    workspace = Path(workspace).expanduser().resolve()
                    workspace.mkdir(parents=True, exist_ok=True)
                else:
                    provider = _create_provider_from_env()
                    workspace = workspace_override or Path(
                        os.getenv("AGENT_WORKSPACE", str(Path.cwd() / "workspace"))
                    ).expanduser().resolve()
                    workspace.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.debug("Nanobot config unavailable, using env: %s", e)
                provider = _create_provider_from_env()
                workspace = workspace_override or Path(
                    os.getenv("AGENT_WORKSPACE", str(Path.cwd() / "workspace"))
                ).expanduser().resolve()
                workspace.mkdir(parents=True, exist_ok=True)

            session_manager = SessionManager(workspace)
            _agent_loop = AgentLoop(
                bus=bus,
                provider=provider,
                workspace=workspace,
                model=provider.default_model if hasattr(provider, "default_model") else None,
                max_iterations=20,
                brave_api_key=None,
                restrict_to_workspace=False,
                session_manager=session_manager,
            )
            logger.info(
                "Gateway bridge initialized (workspace=%s, model=%s)",
                workspace,
                getattr(provider, "default_model", "default"),
            )
            return _agent_loop
        except Exception as e:
            logger.exception("Failed to initialize gateway bridge: %s", e)
            raise


async def execute_task(
    task: str,
    chat_id: int,
    workspace: Path | None = None,
    timeout_seconds: float = 120.0,
) -> str:
    """Execute a task via the nanobot agent and return the result.

    Args:
        task: User's task description (e.g. "create file test.txt with Hello").
        chat_id: Telegram chat ID (used for session isolation).
        workspace: Optional workspace path; uses config default if not provided.
        timeout_seconds: Max time for agent execution.

    Returns:
        Agent's response text, or error message on failure.
    """
    try:
        agent = await _get_agent_loop(workspace_override=workspace)
        session_key = f"telegram:{chat_id}"

        result = await asyncio.wait_for(
            agent.process_direct(
                task,
                session_key=session_key,
                channel="telegram",
                chat_id=str(chat_id),
            ),
            timeout=timeout_seconds,
        )
        return result or ""
    except asyncio.TimeoutError:
        logger.warning("Gateway task timed out after %.0fs", timeout_seconds)
        return (
            f"Агентный режим не завершил задачу за {timeout_seconds:.0f} секунд. "
            "Попробуйте упростить запрос или разбить его на части."
        )
    except RuntimeError as e:
        logger.exception("Gateway task failed")
        return f"Ошибка агентного режима: {e}"
    except Exception as e:
        logger.exception("Gateway bridge error")
        return f"Не удалось выполнить задачу через агент: {e}"
