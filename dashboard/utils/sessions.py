"""Sessions wrapper for dashboard."""

from pathlib import Path
from typing import Any

try:
    from nanobot.session.manager import SessionManager
    from nanobot.utils.helpers import get_workspace_path
    _HAS_NANOBOT = True
except ImportError:
    _HAS_NANOBOT = False


def get_sessions_list(limit: int = 50) -> list[dict[str, Any]]:
    """Get list of sessions from ~/.nanobot/sessions/. Returns empty list if unavailable."""
    if not _HAS_NANOBOT:
        return []
    try:
        workspace = get_workspace_path()
        manager = SessionManager(workspace)
        sessions = manager.list_sessions()
        return sessions[:limit] if limit else sessions
    except Exception:
        return []
