"""Notification manager for sending push notifications via Telegram.

Example usage:

    import asyncio
    from datetime import datetime, timedelta
    from nanobot.notifications import NotificationManager, Priority

    manager = NotificationManager(bot_token="YOUR_BOT_TOKEN")

    # Send immediate notification
    asyncio.run(manager.send_notification(123456789, "Task completed!", "high"))

    # Schedule for later
    manager.schedule_notification(
        chat_id=123456789,
        message="Reminder: meeting in 10 min",
        when=datetime.now() + timedelta(minutes=10),
        priority=Priority.URGENT,
    )
    manager.start_scheduler()
    asyncio.run(asyncio.sleep(600))  # Keep running
    manager.stop_scheduler()
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from loguru import logger
from telegram import Bot

from nanobot.notifications.types import Notification, Priority


def _priority_prefix(priority: Priority) -> str:
    """Return emoji/prefix for message based on priority."""
    prefixes = {
        Priority.LOW: "",
        Priority.NORMAL: "",
        Priority.HIGH: "🔔 ",
        Priority.URGENT: "⚠️ ",
    }
    return prefixes.get(priority, "")


class NotificationManager:
    """
    Manages mobile push notifications through Telegram.

    Uses python-telegram-bot for sending messages to user chat_ids.
    """

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self._bot: Bot | None = None
        self._scheduled: list[Notification] = []
        self._scheduler_task: asyncio.Task[None] | None = None
        self._running = False

    def _get_bot(self) -> Bot:
        if self._bot is None:
            self._bot = Bot(token=self.bot_token)
        return self._bot

    async def send_notification(
        self,
        chat_id: str | int,
        message: str,
        priority: str | Priority = "normal",
    ) -> bool:
        """
        Send an immediate notification to the given chat_id.

        Args:
            chat_id: Telegram chat ID (user or group).
            message: Text message to send.
            priority: One of "low", "normal", "high", "urgent" or Priority enum.

        Returns:
            True if sent successfully, False otherwise.
        """
        if isinstance(priority, str):
            try:
                priority = Priority(priority.lower())
            except ValueError:
                priority = Priority.NORMAL

        prefix = _priority_prefix(priority)
        full_message = f"{prefix}{message}" if prefix else message

        try:
            bot = self._get_bot()
            await bot.send_message(
                chat_id=int(chat_id),
                text=full_message,
            )
            logger.debug(
                "Notification sent to chat_id={} priority={}",
                chat_id,
                priority.value,
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to send notification to chat_id={}: {}",
                chat_id,
                e,
                exc_info=True,
            )
            return False

    def schedule_notification(
        self,
        chat_id: str | int,
        message: str,
        when: datetime,
        priority: str | Priority = "normal",
        tags: tuple[str, ...] = (),
    ) -> None:
        """
        Schedule a notification to be sent at a specific time.

        The scheduler runs in the background when start_scheduler() is called.
        Until then, or if scheduler is not running, scheduled items are stored
        and sent when the scheduler processes them.

        Args:
            chat_id: Telegram chat ID.
            message: Text message to send.
            when: Datetime when to send.
            priority: Notification priority.
            tags: Optional tags for filtering/tracking.
        """
        if isinstance(priority, str):
            try:
                priority = Priority(priority.lower())
            except ValueError:
                priority = Priority.NORMAL

        notification = Notification(
            chat_id=chat_id,
            message=message,
            priority=priority,
            scheduled_at=when,
            tags=tags,
        )
        self._scheduled.append(notification)
        logger.info(
            "Scheduled notification for chat_id={} at {} (priority={})",
            chat_id,
            when.isoformat(),
            priority.value,
        )

    async def _scheduler_loop(self) -> None:
        """Background loop that sends scheduled notifications when due."""
        while self._running:
            try:
                now = datetime.now()
                to_send: list[Notification] = []
                remaining: list[Notification] = []

                for n in self._scheduled:
                    if n.scheduled_at and n.scheduled_at <= now:
                        to_send.append(n)
                    else:
                        remaining.append(n)

                self._scheduled = remaining

                for n in to_send:
                    await self.send_notification(
                        n.chat_id,
                        n.message,
                        n.priority,
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Scheduler loop error: {}", e, exc_info=True)

            await asyncio.sleep(10)

    def start_scheduler(self) -> None:
        """Start the background scheduler for delayed notifications."""
        if self._scheduler_task and not self._scheduler_task.done():
            logger.debug("Notification scheduler already running")
            return
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Notification scheduler started")

    def stop_scheduler(self) -> None:
        """Stop the background scheduler."""
        self._running = False
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
        self._scheduler_task = None
        logger.info("Notification scheduler stopped")
