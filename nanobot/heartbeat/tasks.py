"""Парсер HEARTBEAT.md для выделения секций и задач."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


_HEADING_RE = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")
_CHECKBOX_RE = re.compile(r"^[-*]\s*\[(?P<mark>[ xX])\]\s*(?P<text>.+?)\s*$")
_BULLET_RE = re.compile(r"^[-*]\s+(?P<text>.+?)\s*$")


@dataclass
class HeartbeatTask:
    """Одна задача, извлеченная из HEARTBEAT.md."""

    section: str
    text: str
    done: bool = False
    line_no: int = 0


@dataclass
class HeartbeatParseResult:
    """Результат разбора HEARTBEAT.md."""

    sections: dict[str, list[str]] = field(default_factory=dict)
    tasks: list[HeartbeatTask] = field(default_factory=list)
    actionable_tasks: list[HeartbeatTask] = field(default_factory=list)


def _normalize_section(name: str) -> str:
    return (name or "").strip().lower()


def _is_completed_section(name: str) -> bool:
    """Секция, из которой задачи не нужно выполнять."""
    norm = _normalize_section(name)
    return any(word in norm for word in ("completed", "done", "archive", "closed"))


def _is_active_section(name: str) -> bool:
    """Секция, где допустимы plain-text задачи (без чекбоксов)."""
    norm = _normalize_section(name)
    return any(word in norm for word in ("active", "task", "todo", "to-do", "inbox"))


def parse_heartbeat(content: str | None) -> HeartbeatParseResult:
    """
    Разбирает HEARTBEAT.md по секциям и задачам.

    Поддерживается:
    - markdown-заголовки как секции;
    - чекбоксы: - [ ] / - [x];
    - обычные bullet-пункты: - task;
    - plain text в Active/Todo-секциях (как fallback).
    """
    result = HeartbeatParseResult()
    if not content:
        return result

    current_section = "root"
    result.sections[current_section] = []

    for idx, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.rstrip()
        stripped = line.strip()

        # Заголовок секции
        heading_match = _HEADING_RE.match(stripped)
        if heading_match:
            current_section = heading_match.group("title").strip()
            result.sections.setdefault(current_section, [])
            continue

        result.sections.setdefault(current_section, []).append(line)

        # Игнор служебных/пустых строк
        if not stripped:
            continue
        if stripped.startswith("<!--") or stripped.startswith("-->"):
            continue

        # Чекбокс-задача
        cb = _CHECKBOX_RE.match(stripped)
        if cb:
            done = cb.group("mark").lower() == "x"
            text = cb.group("text").strip()
            if text:
                task = HeartbeatTask(
                    section=current_section,
                    text=text,
                    done=done,
                    line_no=idx,
                )
                result.tasks.append(task)
                if not task.done and not _is_completed_section(current_section):
                    result.actionable_tasks.append(task)
            continue

        # Обычный bullet
        blt = _BULLET_RE.match(stripped)
        if blt:
            text = blt.group("text").strip()
            if text:
                task = HeartbeatTask(
                    section=current_section,
                    text=text,
                    done=False,
                    line_no=idx,
                )
                result.tasks.append(task)
                if not _is_completed_section(current_section):
                    result.actionable_tasks.append(task)
            continue

        # Plain text считаем задачей только в активных секциях
        if _is_active_section(current_section):
            task = HeartbeatTask(
                section=current_section,
                text=stripped,
                done=False,
                line_no=idx,
            )
            result.tasks.append(task)
            if not _is_completed_section(current_section):
                result.actionable_tasks.append(task)

    return result


def count_actionable_tasks(content: str | None) -> int:
    """Возвращает количество задач, которые нужно выполнить."""
    return len(parse_heartbeat(content).actionable_tasks)
