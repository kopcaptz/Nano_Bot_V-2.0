"""Tests for session history character-budget trimming."""

from __future__ import annotations

from nanobot.session.manager import Session


def test_get_history_respects_max_messages():
    session = Session(key="cli:test")
    for idx in range(10):
        session.add_message("user", f"message-{idx}")

    history = session.get_history(max_messages=3)
    assert len(history) == 3
    assert history[0]["content"] == "message-7"
    assert history[2]["content"] == "message-9"


def test_get_history_respects_character_budget_from_tail():
    session = Session(key="cli:test")
    session.add_message("user", "A" * 20)    # msg 1
    session.add_message("assistant", "B" * 20)  # msg 2
    session.add_message("user", "C" * 15)    # msg 3

    history = session.get_history(max_messages=10, max_chars=35)

    # Should keep newest messages that fit budget from the tail:
    # msg3 (15) + msg2 (20) = 35
    assert len(history) == 2
    assert history[0]["content"] == "B" * 20
    assert history[1]["content"] == "C" * 15


def test_get_history_keeps_latest_message_even_if_over_budget():
    session = Session(key="cli:test")
    session.add_message("user", "short")
    session.add_message("assistant", "X" * 500)

    history = session.get_history(max_messages=10, max_chars=100)

    assert len(history) == 1
    assert history[0]["content"] == "X" * 500
