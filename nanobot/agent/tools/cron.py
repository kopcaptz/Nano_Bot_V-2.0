"""Cron tool for scheduling reminders and tasks."""

import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from nanobot.agent.tools.base import Tool
from nanobot.cron.service import CronService
from nanobot.cron.types import CronSchedule

if TYPE_CHECKING:
    from nanobot.notifications.manager import NotificationManager


def _parse_when(when: str) -> int | None:
    """Parse relative time strings like '30 minutes', '1 hour' into seconds."""
    if not when or not when.strip():
        return None
    s = when.strip().lower()
    # Patterns: "30 minutes", "30 mins", "1 hour", "2 hours", "90 seconds"
    m = re.match(r"(\d+)\s*(minute|min|minutes|mins|hour|hours|hr|hrs|second|seconds|sec|secs)", s)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit.startswith("min"):
            return n * 60
        if unit.startswith("hour") or unit.startswith("hr"):
            return n * 3600
        if unit.startswith("sec"):
            return n
    return None


class CronTool(Tool):
    """Tool to schedule reminders and recurring tasks."""

    def __init__(
        self,
        cron_service: CronService,
        notification_manager: "NotificationManager | None" = None,
    ):
        self._cron = cron_service
        self._notification_manager = notification_manager
        self._channel = ""
        self._chat_id = ""

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current session context for delivery."""
        self._channel = channel
        self._chat_id = chat_id

    @property
    def name(self) -> str:
        return "cron"

    @property
    def description(self) -> str:
        return (
            "Schedule reminders and recurring tasks. "
            "Actions: add (recurring), remind (one-shot with push), list, remove. "
            "Use 'remind' for 'remind me in X minutes about Y' - sends Telegram push."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "remind", "list", "remove"],
                    "description": "add=recurring job, remind=one-shot push in X time, list=show jobs, remove=delete job",
                },
                "message": {
                    "type": "string",
                    "description": "Reminder/task message (for add and remind)",
                },
                "when": {
                    "type": "string",
                    "description": "For remind: relative time like '30 minutes', '1 hour'",
                },
                "every_seconds": {
                    "type": "integer",
                    "description": "Interval in seconds (for add, recurring)",
                },
                "cron_expr": {
                    "type": "string",
                    "description": "Cron expression like '0 9 * * *' (for add)",
                },
                "job_id": {
                    "type": "string",
                    "description": "Job ID (for remove)",
                },
                "notify_chat_id": {
                    "type": "string",
                    "description": "Optional Telegram chat_id for push when cron runs (for add)",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        message: str = "",
        when: str = "",
        every_seconds: int | None = None,
        cron_expr: str | None = None,
        job_id: str | None = None,
        notify_chat_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        if action == "add":
            return self._add_job(message, every_seconds, cron_expr, notify_chat_id)
        if action == "remind":
            return await self._schedule_reminder(message, when)
        if action == "list":
            return self._list_jobs()
        if action == "remove":
            return self._remove_job(job_id)
        return f"Unknown action: {action}"

    def _add_job(
        self,
        message: str,
        every_seconds: int | None,
        cron_expr: str | None,
        notify_chat_id: str | None,
    ) -> str:
        if not message:
            return "Error: message is required for add"
        if not self._channel or not self._chat_id:
            return "Error: no session context (channel/chat_id)"

        # Build schedule
        if every_seconds:
            schedule = CronSchedule(kind="every", every_ms=every_seconds * 1000)
        elif cron_expr:
            schedule = CronSchedule(kind="cron", expr=cron_expr)
        else:
            return "Error: either every_seconds or cron_expr is required"

        chat_id_for_notify = notify_chat_id or (
            self._chat_id if self._channel == "telegram" else None
        )

        job = self._cron.add_job(
            name=message[:30],
            schedule=schedule,
            message=message,
            deliver=True,
            channel=self._channel,
            to=self._chat_id,
            notify_chat_id=chat_id_for_notify,
        )
        out = f"Created job '{job.name}' (id: {job.id})"
        if chat_id_for_notify:
            out += " [push notifications enabled]"
        return out

    async def _schedule_reminder(self, message: str, when: str) -> str:
        """Schedule a one-shot reminder with Telegram push."""
        if not message:
            return "Error: message is required for remind"
        if not when:
            return "Error: when is required (e.g. '30 minutes', '1 hour')"
        if not self._notification_manager:
            return "Error: push notifications not configured (Telegram bot token needed)"

        seconds = _parse_when(when)
        if seconds is None:
            return f"Error: could not parse when '{when}'. Use formats like '30 minutes', '1 hour'"

        chat_id = self._chat_id
        if self._channel != "telegram":
            return (
                "Error: schedule_reminder sends push to Telegram. "
                "Use this from Telegram channel."
            )

        target_time = datetime.now() + timedelta(seconds=seconds)
        self._notification_manager.schedule_notification(
            chat_id=int(chat_id),
            message=message,
            when=target_time,
            priority="high",
            tags=("reminder",),
        )
        return f"Reminder set: '{message}' in {when}. Push will arrive on your phone."

    def _list_jobs(self) -> str:
        jobs = self._cron.list_jobs()
        if not jobs:
            return "No scheduled jobs."
        lines = [f"- {j.name} (id: {j.id}, {j.schedule.kind})" for j in jobs]
        return "Scheduled jobs:\n" + "\n".join(lines)

    def _remove_job(self, job_id: str | None) -> str:
        if not job_id:
            return "Error: job_id is required for remove"
        if self._cron.remove_job(job_id):
            return f"Removed job {job_id}"
        return f"Job {job_id} not found"
