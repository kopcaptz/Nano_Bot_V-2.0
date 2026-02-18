"""Bridge to nanobot agent for hybrid mode — code, files, complex commands."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _ensure_nanobot_import_path() -> None:
    """Add project root to path so nanobot can be imported when run from workspace."""
    if "nanobot" in sys.modules:
        return
    root = Path(__file__).resolve().parent.parent.parent
    if root.is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))

# Lazy import to avoid hard dependency; nanobot is optional
_agent: Optional[object] = None
_workspace_override: Optional[Path] = None


def _get_agent(workspace: Optional[Path] = None) -> object:
    """Lazy-initialize nanobot AgentLoop. Uses workspace override if provided."""
    global _agent, _workspace_override
    if _agent is not None:
        return _agent

    _ensure_nanobot_import_path()
    try:
        from nanobot.config.loader import load_config
        from nanobot.bus.queue import MessageBus
        from nanobot.agent.loop import AgentLoop
        from nanobot.session.manager import SessionManager

        # Build provider like nanobot CLI does
        config = load_config()
        provider = _make_provider(config)

        workspace_path = (workspace or _workspace_override or config.workspace_path).resolve()
        workspace_path.mkdir(parents=True, exist_ok=True)

        session_manager = SessionManager(workspace_path)
        bus = MessageBus()

        agent = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=workspace_path,
            model=config.agents.defaults.model,
            max_iterations=config.agents.defaults.max_tool_iterations,
            max_llm_calls=config.agents.defaults.max_llm_calls,
            llm_max_tokens=config.agents.defaults.max_tokens,
            llm_temperature=config.agents.defaults.temperature,
            brave_api_key=config.tools.web.search.api_key or None,
            exec_config=config.tools.exec,
            cron_service=None,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            session_manager=session_manager,
            navigator_config=config.navigator,
        )

        _agent = agent
        logger.info("Gateway bridge: nanobot AgentLoop initialized (workspace=%s)", workspace_path)
        return _agent
    except ImportError as e:
        logger.error("nanobot not installed or unavailable: %s", e)
        raise RuntimeError(
            "Gateway bridge requires nanobot. Install: pip install nanobot-ai (or pip install -e .)"
        ) from e
    except Exception as e:
        logger.exception("Failed to initialize gateway bridge")
        raise RuntimeError(f"Gateway bridge initialization failed: {e}") from e


def _make_provider(config: object) -> object:
    """Create LiteLLMProvider from nanobot config."""
    from nanobot.providers.litellm_provider import LiteLLMProvider

    p = config.get_provider()
    model = config.agents.defaults.model
    if not (p and p.api_key) and not (model and model.startswith("bedrock/")):
        raise RuntimeError(
            "nanobot requires an API key. Configure ~/.nanobot/config.json or set provider api_key."
        )
    return LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=config.get_provider_name(),
    )


def set_workspace(workspace: Path) -> None:
    """Set workspace path for the agent. Call before first execute_task if needed."""
    global _workspace_override
    _workspace_override = Path(workspace).resolve()


async def execute_task(
    task: str,
    session_key: str = "gateway_bridge:default",
    workspace: Optional[Path] = None,
) -> str:
    """
    Execute a task via nanobot agent (files, code, complex commands).

    Args:
        task: User request (e.g. "create file test.txt with text Hello").
        session_key: Session identifier for conversation context.
        workspace: Optional workspace path override for this call.

    Returns:
        Agent response text.
    """
    agent = _get_agent(workspace=workspace or _workspace_override)
    try:
        response = await agent.process_direct(
            content=task,
            session_key=session_key,
            channel="gateway_bridge",
            chat_id="default",
        )
        return response or ""
    except Exception as e:
        logger.exception("Gateway execute_task failed")
        return f"[Gateway error] {e}"
