from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.db import log_event
from app.services.own_alerts import (
    dispatch_due_own_alerts,
    restore_own_alert_schedules,
)


class OwnAlertSchedulerService:
    def __init__(self, *, poll_interval: float = 15.0) -> None:
        self._poll_interval = poll_interval
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        restored = restore_own_alert_schedules()
        if restored:
            log_event(
                "INFO",
                "alerts",
                f"Restored {restored} own APRS alarm schedule(s).",
            )
        self._task = asyncio.create_task(
            self._run(),
            name="aprsbox-own-alert-scheduler",
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            self._tick()
            await self._sleep(self._poll_interval)

    def _tick(self, now: datetime | None = None) -> int:
        reference = now or datetime.now(timezone.utc)
        try:
            return dispatch_due_own_alerts(now=reference)
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            log_event(
                "ERROR",
                "alerts",
                f"Own APRS alarm scheduler failed: {message}",
            )
            return 0

    async def _sleep(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass
