"""Heartbeat service - periodic agent wake-up to check for tasks."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine

from loguru import logger

from nanobot.heartbeat.tasks import parse_heartbeat

# Default interval: 30 minutes
DEFAULT_HEARTBEAT_INTERVAL_S = 30 * 60

# The prompt sent to agent during heartbeat
HEARTBEAT_PROMPT = """Read HEARTBEAT.md in your workspace (if it exists).
Follow any instructions or tasks listed there.
If nothing needs attention, reply with just: HEARTBEAT_OK"""

# Token that indicates "nothing to do"
HEARTBEAT_OK_TOKEN = "HEARTBEAT_OK"


def _now_iso() -> str:
    """Текущее время в ISO-формате (UTC)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class HeartbeatService:
    """
    Periodic heartbeat service that wakes the agent to check for tasks.

    Улучшения:
    - lock-файл с TTL против дублирования тиков;
    - статус-файл heartbeat.json;
    - retry/backoff;
    - встроенные метрики выполнения.
    """

    def __init__(
        self,
        workspace: Path,
        on_heartbeat: Callable[[str], Coroutine[Any, Any, str]] | None = None,
        interval_s: int = DEFAULT_HEARTBEAT_INTERVAL_S,
        enabled: bool = True,
        max_retries: int = 3,
        on_notify: Callable[[str], Coroutine[Any, Any, None]] | None = None,
    ):
        self.workspace = workspace
        self.on_heartbeat = on_heartbeat
        self.interval_s = interval_s
        self.enabled = enabled
        self.max_retries = max(0, int(max_retries))
        self.on_notify = on_notify
        self._running = False
        self._task: asyncio.Task | None = None

        data_dir = Path.home() / ".nanobot"
        self.lock_file = data_dir / "heartbeat.lock"
        self.status_file = data_dir / "heartbeat.json"

        # Метрики heartbeat
        self.ticks_total = 0
        self.ticks_skipped = 0
        self.tasks_executed = 0
        self.errors_total = 0

        self._recent_errors: list[str] = []
        self._load_status()

    @property
    def heartbeat_file(self) -> Path:
        return self.workspace / "HEARTBEAT.md"

    def _ensure_data_dir(self) -> None:
        self.status_file.parent.mkdir(parents=True, exist_ok=True)

    def _read_heartbeat_file(self) -> str | None:
        """Read HEARTBEAT.md content."""
        if self.heartbeat_file.exists():
            try:
                return self.heartbeat_file.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    def _load_status(self) -> None:
        """Загружает предыдущий статус и историю ошибок (если есть)."""
        self._ensure_data_dir()
        if not self.status_file.exists():
            return

        try:
            data = json.loads(self.status_file.read_text(encoding="utf-8"))
            errors = data.get("errors", [])
            if isinstance(errors, list):
                self._recent_errors = [str(e) for e in errors][-5:]
        except Exception:
            self._recent_errors = []

    def _write_status(self, last_status: str, tasks_executed: int, error: str | None = None) -> None:
        """Обновляет heartbeat.json после каждого тика."""
        if error:
            self._recent_errors.append(f"{_now_iso()} {error}")
            self._recent_errors = self._recent_errors[-5:]

        payload = {
            "last_tick": _now_iso(),
            "last_status": last_status,
            "tasks_executed": int(tasks_executed),
            "errors": self._recent_errors[-5:],
        }
        self._ensure_data_dir()
        self.status_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_lock_expiry(self) -> float:
        """Читает время истечения lock-файла. Возвращает 0.0 при ошибке."""
        if not self.lock_file.exists():
            return 0.0
        try:
            data = json.loads(self.lock_file.read_text(encoding="utf-8"))
            return float(data.get("expires_at", 0.0))
        except Exception:
            return 0.0

    def acquire_lock(self) -> bool:
        """
        Пытается захватить lock-файл heartbeat.

        TTL lock: 2 * interval_s.
        Если lock существует и не истек, тик пропускается.
        """
        self._ensure_data_dir()
        ttl_s = max(1, int(2 * self.interval_s))

        for _ in range(2):
            now = time.time()
            if self.lock_file.exists():
                expires_at = self._read_lock_expiry()
                if expires_at > now:
                    return False
                # stale lock — удаляем
                try:
                    self.lock_file.unlink()
                except Exception:
                    return False

            payload = {
                "acquired_at": now,
                "expires_at": now + ttl_s,
                "pid": os.getpid(),
            }
            try:
                with self.lock_file.open("x", encoding="utf-8") as f:
                    json.dump(payload, f)
                return True
            except FileExistsError:
                # Кто-то успел захватить lock между проверкой и созданием.
                continue
            except Exception:
                return False

        return False

    def release_lock(self) -> None:
        """Освобождает lock-файл heartbeat."""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except Exception:
            pass

    async def _notify_failure(self, message: str) -> None:
        """Отправляет уведомление об ошибке heartbeat (если подключено)."""
        if self.on_notify:
            try:
                await self.on_notify(message)
            except Exception as exc:
                logger.error(f"Heartbeat notify callback failed: {exc}")
        else:
            logger.error(f"Heartbeat failure: {message}")

    async def _mark_failed(self, error: str) -> None:
        """Фиксирует фатальную ошибку тика и уведомляет о ней."""
        self.errors_total += 1
        self._write_status(last_status="error", tasks_executed=0, error=error)
        await self._notify_failure(error)

    async def _execute_with_retry(self, prompt: str) -> str | None:
        """Запускает heartbeat callback с retry + экспоненциальным backoff."""
        if not self.on_heartbeat:
            return None

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await self.on_heartbeat(prompt)
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                wait_s = 2 ** (attempt + 1)
                logger.warning(
                    f"Heartbeat attempt {attempt + 1} failed: {exc}. "
                    f"Retrying in {wait_s}s..."
                )
                await asyncio.sleep(wait_s)

        await self._mark_failed(
            f"Heartbeat execution failed after {self.max_retries + 1} attempts: {last_error}"
        )
        return None

    async def start(self) -> None:
        """Start the heartbeat service."""
        if not self.enabled:
            logger.info("Heartbeat disabled")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Heartbeat started (every {self.interval_s}s)")

    def stop(self) -> None:
        """Stop the heartbeat service."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run_loop(self) -> None:
        """Main heartbeat loop."""
        while self._running:
            try:
                await asyncio.sleep(self.interval_s)
                if self._running:
                    await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                await self._mark_failed(f"Heartbeat loop error: {e}")

    async def _tick(self) -> None:
        """Execute a single heartbeat tick."""
        self.ticks_total += 1

        if not self.acquire_lock():
            self.ticks_skipped += 1
            self._write_status(last_status="skipped", tasks_executed=0)
            logger.debug("Heartbeat: skipped (active lock)")
            return

        try:
            content = self._read_heartbeat_file()
            parsed = parse_heartbeat(content)

            # Skip if HEARTBEAT.md has no actionable tasks
            if not parsed.actionable_tasks:
                self.ticks_skipped += 1
                self._write_status(last_status="skipped", tasks_executed=0)
                logger.debug("Heartbeat: no tasks (HEARTBEAT.md has no actionable items)")
                return

            if not self.on_heartbeat:
                self.ticks_skipped += 1
                self._write_status(last_status="skipped", tasks_executed=0)
                logger.debug("Heartbeat: skipped (no callback configured)")
                return

            logger.info(f"Heartbeat: checking {len(parsed.actionable_tasks)} tasks...")
            response = await self._execute_with_retry(HEARTBEAT_PROMPT)
            if response is None:
                return  # Ошибка уже зафиксирована в _execute_with_retry

            normalized = response.upper().replace("_", "")
            if HEARTBEAT_OK_TOKEN.replace("_", "") in normalized:
                self._write_status(last_status="ok", tasks_executed=0)
                logger.info("Heartbeat: OK (no action needed)")
                return

            # Если агент вернул не HEARTBEAT_OK — считаем, что задачи выполнялись.
            executed_now = max(1, len(parsed.actionable_tasks))
            self.tasks_executed += executed_now
            self._write_status(last_status="ok", tasks_executed=executed_now)
            logger.info(f"Heartbeat: completed tasks ({executed_now})")
        finally:
            self.release_lock()

    def get_metrics(self) -> dict[str, int]:
        """Возвращает текущие счетчики heartbeat-метрик."""
        return {
            "ticks_total": self.ticks_total,
            "ticks_skipped": self.ticks_skipped,
            "tasks_executed": self.tasks_executed,
            "errors_total": self.errors_total,
        }

    async def trigger_now(self) -> str | None:
        """Manually trigger a heartbeat callback with retry policy."""
        if not self.on_heartbeat:
            return None
        return await self._execute_with_retry(HEARTBEAT_PROMPT)
