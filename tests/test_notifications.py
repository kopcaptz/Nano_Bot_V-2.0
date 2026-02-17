"""Tests for the notification system."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.agent.tools.cron import CronTool, _parse_when
from nanobot.cron.service import CronService
from nanobot.cron.types import CronSchedule
from nanobot.notifications.manager import NotificationManager
from nanobot.notifications.triggers import EventTrigger
from nanobot.notifications.types import Priority


# =============================================================================
# NotificationManager
# =============================================================================


@pytest.mark.asyncio
async def test_send_notification_mocked():
    """Test NotificationManager.send_notification with mocked Telegram Bot."""
    with patch("nanobot.notifications.manager.Bot") as mock_bot_cls:
        mock_send = AsyncMock(return_value=None)
        mock_bot_cls.return_value.send_message = mock_send
        mock_bot_cls.return_value.get_me = AsyncMock(return_value=MagicMock(username="test_bot"))

        manager = NotificationManager(bot_token="fake_token")
        result = await manager.send_notification(
            chat_id=123456789,
            message="Test message",
            priority="normal",
        )

        assert result is True
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["chat_id"] == 123456789
        assert "Test message" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_send_system_alert_levels():
    """Test send_system_alert maps levels to correct prefixes."""
    with patch("nanobot.notifications.manager.Bot") as mock_bot_cls:
        mock_send = AsyncMock(return_value=None)
        mock_bot_cls.return_value.send_message = mock_send

        manager = NotificationManager(bot_token="fake_token")

        await manager.send_system_alert(123, "info msg", level="info")
        assert "ℹ️" in mock_send.call_args_list[0].kwargs["text"] or "info" in str(mock_send.call_args_list[0])

        await manager.send_system_alert(123, "success msg", level="success")
        assert "✅" in mock_send.call_args_list[1].kwargs["text"]

        await manager.send_system_alert(123, "warning msg", level="warning")
        assert "⚠️" in mock_send.call_args_list[2].kwargs["text"]

        await manager.send_system_alert(123, "error msg", level="error")
        assert "🚨" in mock_send.call_args_list[3].kwargs["text"]


# =============================================================================
# schedule_reminder via cron
# =============================================================================


@pytest.fixture
def temp_cron_store():
    """Create temporary cron store path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "jobs.json"


@pytest.fixture
def cron_service(temp_cron_store):
    """Create CronService with temp store."""
    return CronService(temp_cron_store)


@pytest.fixture
def mock_notification_manager():
    """Create mock NotificationManager for schedule_notification."""
    manager = MagicMock(spec=NotificationManager)
    manager.schedule_notification = MagicMock()
    return manager


@pytest.mark.asyncio
async def test_schedule_reminder_parse_when():
    """Test _parse_when parses relative time strings."""
    assert _parse_when("30 minutes") == 1800
    assert _parse_when("1 hour") == 3600
    assert _parse_when("2 hours") == 7200
    assert _parse_when("90 seconds") == 90
    assert _parse_when("") is None
    assert _parse_when("invalid") is None


@pytest.mark.asyncio
async def test_cron_tool_schedule_reminder(cron_service, mock_notification_manager):
    """Test CronTool schedule_reminder calls NotificationManager.schedule_notification."""
    mock_notification_manager.start_scheduler = MagicMock()

    tool = CronTool(cron_service, notification_manager=mock_notification_manager)
    tool.set_context("telegram", "123456789")

    result = await tool.execute(
        action="remind",
        message="Позвонить маме",
        when="30 minutes",
    )

    assert "Reminder set" in result
    mock_notification_manager.schedule_notification.assert_called_once()
    call_args = mock_notification_manager.schedule_notification.call_args
    assert call_args.kwargs["chat_id"] == 123456789
    assert call_args.kwargs["message"] == "Позвонить маме"
    assert call_args.kwargs["priority"] == "high"


@pytest.mark.asyncio
async def test_cron_tool_schedule_reminder_no_manager(cron_service):
    """Test schedule_reminder without NotificationManager returns error."""
    tool = CronTool(cron_service, notification_manager=None)
    tool.set_context("telegram", "123456789")

    result = await tool.execute(action="remind", message="test", when="30 minutes")

    assert "not configured" in result or "Error" in result


# =============================================================================
# EventTrigger (mock)
# =============================================================================


@pytest.fixture
def mock_nm_for_trigger():
    """Mock NotificationManager for EventTrigger tests."""
    nm = AsyncMock(spec=NotificationManager)
    nm.send_system_alert = AsyncMock(return_value=True)
    return nm


@pytest.mark.asyncio
async def test_event_trigger_on_error(mock_nm_for_trigger):
    """Test EventTrigger.on_error sends notification."""
    trigger = EventTrigger(notification_manager=mock_nm_for_trigger, default_chat_id=999)
    result = await trigger.on_error(ValueError("test error"), context={"tool": "exec"}, chat_id=123)

    assert result is True
    mock_nm_for_trigger.send_system_alert.assert_called_once()
    call_kwargs = mock_nm_for_trigger.send_system_alert.call_args.kwargs
    assert call_kwargs["chat_id"] == 123
    assert "Ошибка" in call_kwargs["message"]
    assert call_kwargs["level"] == "error"


@pytest.mark.asyncio
async def test_event_trigger_on_task_complete(mock_nm_for_trigger):
    """Test EventTrigger.on_task_complete sends for significant tools."""
    trigger = EventTrigger(notification_manager=mock_nm_for_trigger, default_chat_id=999)

    result = await trigger.on_task_complete("web_search", chat_id=123)
    assert result is True
    mock_nm_for_trigger.send_system_alert.assert_called_once()
    assert "web_search" in mock_nm_for_trigger.send_system_alert.call_args.kwargs["message"]


@pytest.mark.asyncio
async def test_event_trigger_on_task_complete_skips_routine_tools(mock_nm_for_trigger):
    """Test EventTrigger skips routine tools by default."""
    trigger = EventTrigger(notification_manager=mock_nm_for_trigger, default_chat_id=999)

    result = await trigger.on_task_complete("read_file", chat_id=123)
    assert result is False
    mock_nm_for_trigger.send_system_alert.assert_not_called()


@pytest.mark.asyncio
async def test_event_trigger_on_system_alert(mock_nm_for_trigger):
    """Test EventTrigger.on_system_alert."""
    trigger = EventTrigger(notification_manager=mock_nm_for_trigger, default_chat_id=999)
    result = await trigger.on_system_alert(
        "Память заканчивается: 90%",
        level="warning",
        chat_id=123,
    )

    assert result is True
    mock_nm_for_trigger.send_system_alert.assert_called_once_with(
        chat_id=123,
        message="Память заканчивается: 90%",
        level="warning",
    )


@pytest.mark.asyncio
async def test_event_trigger_no_manager_returns_false():
    """Test EventTrigger returns False when no manager."""
    trigger = EventTrigger(notification_manager=None)
    assert await trigger.on_error("err", chat_id=123) is False
    assert await trigger.on_task_complete("exec", chat_id=123) is False
    assert await trigger.on_system_alert("msg", chat_id=123) is False


# =============================================================================
# Config migration
# =============================================================================


def test_config_migration_adds_notifications():
    """Test _migrate_config adds notifications section if missing."""
    from nanobot.config.loader import _migrate_config

    data = {"agents": {"defaults": {}}}
    migrated = _migrate_config(data)
    assert "notifications" in migrated["agents"]["defaults"]
    n = migrated["agents"]["defaults"]["notifications"]
    assert n["enabled"] is False
    assert n.get("botToken", "") == ""
    assert n.get("defaultChatId", "") == ""


# =============================================================================
# Integration test with real Telegram (skip by default)
# =============================================================================


@pytest.mark.skip(reason="Integration test; set NANOBOT_TEST_TELEGRAM=1 to run")
@pytest.mark.asyncio
async def test_send_notification_real_telegram():
    """Integration test: send real notification to Telegram. Skip by default."""
    import os

    if not os.environ.get("NANOBOT_TEST_TELEGRAM"):
        pytest.skip("Set NANOBOT_TEST_TELEGRAM=1, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        pytest.skip("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID required")

    manager = NotificationManager(bot_token=token)
    result = await manager.send_notification(
        chat_id=int(chat_id),
        message="[test] Notification system OK",
        priority="normal",
    )
    assert result is True
