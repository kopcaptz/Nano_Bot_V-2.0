"""Event triggers for automatic push notifications."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from nanobot.notifications.manager import NotificationManager


# Tools that warrant a completion notification (skip routine: read_file, list_dir, etc.)
_NOTIFY_ON_COMPLETE_TOOLS = frozenset(
    {"exec", "spawn", "create_skill", "web_search", "web_fetch", "cron"}
)


class EventTrigger:
    """
    Triggers automatic push notifications on important events.

    Uses NotificationManager for delivery. Call from AgentLoop and other
    components to notify users without explicit user action.
    """

    def __init__(
        self,
        notification_manager: "NotificationManager | None",
        default_chat_id: str | int | None = None,
        notify_on_error: bool = True,
        notify_on_task_complete: bool = True,
        notify_on_system_alert: bool = True,
        notify_all_tools: bool = False,
    ):
        self._nm = notification_manager
        self._default_chat_id = default_chat_id
        self.notify_on_error = notify_on_error
        self.notify_on_task_complete = notify_on_task_complete
        self.notify_on_system_alert = notify_on_system_alert
        self.notify_all_tools = notify_all_tools

    def _resolve_chat_id(self, chat_id: str | int | None) -> str | int | None:
        """Resolve chat_id; use default if None."""
        if chat_id is not None and str(chat_id).strip():
            return chat_id
        return self._default_chat_id

    def _can_notify(self, flag: bool) -> bool:
        """Check if we can send (manager + flag)."""
        return bool(self._nm and flag)

    async def on_error(
        self,
        error: BaseException | str,
        context: str | dict[str, Any] | None = None,
        chat_id: str | int | None = None,
    ) -> bool:
        """
        Send push notification when an error occurs.

        Args:
            error: The error (exception or string).
            context: Optional context (e.g. tool name, request info).
            chat_id: Target chat. Uses default if None.

        Returns:
            True if notification was sent.
        """
        if not self._can_notify(self.notify_on_error):
            return False

        target = self._resolve_chat_id(chat_id)
        if not target:
            return False

        err_text = str(error) if isinstance(error, BaseException) else error
        if isinstance(context, dict):
            ctx_str = ", ".join(f"{k}={v}" for k, v in context.items())
        else:
            ctx_str = context or ""

        message = f"Ошибка выполнения: {err_text}"
        if ctx_str:
            message = f"{message} [{ctx_str}]"

        try:
            return await self._nm.send_system_alert(
                chat_id=target,
                message=message,
                level="error",
            )
        except Exception as e:
            logger.warning("EventTrigger.on_error failed to send: {}", e)
            return False

    async def on_task_complete(
        self,
        task_name: str,
        chat_id: str | int | None = None,
    ) -> bool:
        """
        Send push when a task completes successfully.

        Args:
            task_name: Name of the completed task (e.g. tool name).
            chat_id: Target chat. Uses default if None.

        Returns:
            True if notification was sent.
        """
        if not self._can_notify(self.notify_on_task_complete):
            return False
        if not self.notify_all_tools and task_name not in _NOTIFY_ON_COMPLETE_TOOLS:
            return False

        target = self._resolve_chat_id(chat_id)
        if not target:
            return False

        message = f"{task_name} завершён"
        try:
            return await self._nm.send_system_alert(
                chat_id=target,
                message=message,
                level="success",
            )
        except Exception as e:
            logger.warning("EventTrigger.on_task_complete failed to send: {}", e)
            return False

    async def on_system_alert(
        self,
        message: str,
        level: str = "info",
        chat_id: str | int | None = None,
    ) -> bool:
        """
        Send a system alert (memory, health, etc.).

        Args:
            message: Alert message.
            level: info, warning, or error.
            chat_id: Target chat. Uses default if None.

        Returns:
            True if notification was sent.
        """
        if not self._can_notify(self.notify_on_system_alert):
            return False

        target = self._resolve_chat_id(chat_id)
        if not target:
            return False

        try:
            return await self._nm.send_system_alert(
                chat_id=target,
                message=message,
                level=level,
            )
        except Exception as e:
            logger.warning("EventTrigger.on_system_alert failed to send: {}", e)
            return False
