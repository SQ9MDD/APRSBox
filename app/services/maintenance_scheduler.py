from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.db import (
    DEFAULT_EVENT_LOG_KEEP_ROWS,
    DEFAULT_OUTBOUND_JOB_PRUNE_BATCH_SIZE,
    get_app_setting,
    log_event,
    prune_event_logs,
    prune_outbound_jobs_batch,
    prune_traffic_frames_batch,
    set_app_setting,
)
from app.services.igate_messaging import prune_igate_runtime_state
from app.services.alerts import expire_aprs_alerts


LAST_EVENT_LOG_PRUNE_DATE_KEY = "scheduler.maintenance.event_logs.last_pruned_date"
TRAFFIC_FRAME_PRUNE_BATCH_SIZE = 1000
OUTBOUND_JOB_PRUNE_BATCH_SIZE = DEFAULT_OUTBOUND_JOB_PRUNE_BATCH_SIZE


class MaintenanceSchedulerService:
    def __init__(self, *, poll_interval: float = 300.0, event_log_keep_rows: int = DEFAULT_EVENT_LOG_KEEP_ROWS) -> None:
        self._poll_interval = poll_interval
        self._event_log_keep_rows = max(0, int(event_log_keep_rows))
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="aprsbox-maintenance-scheduler")

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

    def _tick(self, now: datetime | None = None) -> None:
        current = now if now is not None else datetime.now(timezone.utc)
        current_date = current.date().isoformat()
        try:
            expired_alerts = expire_aprs_alerts(now=current)
            if expired_alerts:
                log_event(
                    "INFO",
                    "alerts",
                    f"Automatically expired {expired_alerts} APRS alert(s).",
                )
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            log_event(
                "WARNING",
                "maintenance",
                f"Automatic APRS alert expiration failed: {message}",
            )
        if str(get_app_setting(LAST_EVENT_LOG_PRUNE_DATE_KEY) or "").strip() != current_date:
            try:
                prune_event_logs(keep_rows=self._event_log_keep_rows)
                set_app_setting(LAST_EVENT_LOG_PRUNE_DATE_KEY, current_date)
            except Exception as exc:
                message = str(exc).strip() or exc.__class__.__name__
                log_event("WARNING", "maintenance", f"Automatic event log pruning failed: {message}")
        try:
            prune_traffic_frames_batch(limit=TRAFFIC_FRAME_PRUNE_BATCH_SIZE)
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            log_event("WARNING", "maintenance", f"Automatic traffic frame pruning failed: {message}")
        try:
            prune_outbound_jobs_batch(limit=OUTBOUND_JOB_PRUNE_BATCH_SIZE)
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            log_event("WARNING", "maintenance", f"Automatic outbound job pruning failed: {message}")
        try:
            prune_igate_runtime_state(now=current)
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            log_event("WARNING", "maintenance", f"Automatic IGate state pruning failed: {message}")

    async def _sleep(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass
