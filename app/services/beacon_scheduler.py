from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.db import get_app_setting, log_event, set_app_setting
from app.services.beacon_pathing import (
    BEACON_INTERVAL_MODE_FIXED,
    BEACON_INTERVAL_MODE_PROPORTIONAL,
    PROPORTIONAL_BEACON_INTERVAL_MINUTES,
    normalize_beacon_interval_mode,
    proportional_path_signature,
    resolve_proportional_beacon_path,
)
from app.services.content import get_station_settings
from app.services.outbound import enqueue_beacon_job, enqueue_status_job, pending_beacon_job_count, pending_status_job_count


LAST_SCHEDULED_BEACON_AT_KEY = "scheduler.beacon.last_enqueued_at"
LAST_SCHEDULED_STATUS_AT_KEY = "scheduler.status.last_enqueued_at"
PROPORTIONAL_BEACON_STEP_KEY = "scheduler.beacon.proportional.step"
PROPORTIONAL_BEACON_SIGNATURE_KEY = "scheduler.beacon.proportional.signature"


class BeaconSchedulerService:
    def __init__(self, *, poll_interval: float = 15.0) -> None:
        self._poll_interval = poll_interval
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="aprsbox-beacon-scheduler")

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
            await asyncio.to_thread(self._tick)
            await self._sleep(self._poll_interval)

    def _tick(self) -> None:
        station_settings = get_station_settings()
        if not station_settings or not bool(station_settings.get("tx_enabled")):
            return

        now = datetime.now(timezone.utc)
        self._schedule_beacon(station_settings, now)
        self._schedule_status(station_settings, now)

    def _schedule_beacon(self, station_settings: dict[str, object], now: datetime) -> None:
        interval_mode = normalize_beacon_interval_mode(
            station_settings.get("beacon_interval_mode"),
            default=BEACON_INTERVAL_MODE_FIXED,
        )
        if interval_mode == BEACON_INTERVAL_MODE_PROPORTIONAL:
            self._schedule_proportional_beacon(station_settings, now)
            return

        interval_minutes = int(station_settings.get("beacon_interval_minutes") or 30)
        if interval_minutes <= 0:
            return
        if pending_beacon_job_count() > 0:
            log_event("INFO", "outbound", "Beacon scheduler skipped enqueue because a beacon job is already pending")
            return
        if not _is_schedule_due(LAST_SCHEDULED_BEACON_AT_KEY, interval_minutes, now):
            return
        log_event("INFO", "outbound", f"Beacon scheduler due check passed at {now.replace(microsecond=0).isoformat()}")
        success, message = enqueue_beacon_job(station_settings, trigger="scheduled")
        if success:
            set_app_setting(LAST_SCHEDULED_BEACON_AT_KEY, now.replace(microsecond=0).isoformat())
            log_event("INFO", "outbound", "Beacon scheduler enqueued scheduled beacon")
        else:
            log_event("WARNING", "outbound", f"Beacon scheduler failed to enqueue beacon: {message}")

    def _schedule_proportional_beacon(self, station_settings: dict[str, object], now: datetime) -> None:
        if pending_beacon_job_count() > 0:
            log_event("INFO", "outbound", "Beacon scheduler skipped enqueue because a beacon job is already pending")
            return
        if not _is_schedule_due(LAST_SCHEDULED_BEACON_AT_KEY, PROPORTIONAL_BEACON_INTERVAL_MINUTES, now):
            return

        configured_path = str(station_settings.get("beacon_path") or "").strip().upper()
        signature = proportional_path_signature(configured_path)
        stored_signature = str(get_app_setting(PROPORTIONAL_BEACON_SIGNATURE_KEY) or "").strip()
        step_index = _parse_proportional_step(get_app_setting(PROPORTIONAL_BEACON_STEP_KEY))
        if stored_signature != signature:
            step_index = 0

        effective_path = resolve_proportional_beacon_path(configured_path, step_index)
        success, message = enqueue_beacon_job(
            station_settings,
            trigger="scheduled",
            beacon_path_override=effective_path,
        )
        if success:
            set_app_setting(LAST_SCHEDULED_BEACON_AT_KEY, now.replace(microsecond=0).isoformat())
            set_app_setting(PROPORTIONAL_BEACON_STEP_KEY, str(step_index + 1))
            set_app_setting(PROPORTIONAL_BEACON_SIGNATURE_KEY, signature)
            path_label = effective_path or "DIRECT"
            log_event(
                "INFO",
                "outbound",
                f"Beacon scheduler enqueued proportional beacon step={step_index} path={path_label}",
            )
        else:
            log_event("WARNING", "outbound", f"Beacon scheduler failed to enqueue proportional beacon: {message}")

    def _schedule_status(self, station_settings: dict[str, object], now: datetime) -> None:
        if not bool(station_settings.get("status_enabled")):
            return
        interval_minutes = int(station_settings.get("status_interval_minutes") or 30)
        if interval_minutes <= 0:
            return
        if pending_status_job_count() > 0:
            log_event("INFO", "outbound", "Status scheduler skipped enqueue because a status job is already pending")
            return
        if not _is_schedule_due(LAST_SCHEDULED_STATUS_AT_KEY, interval_minutes, now):
            return
        log_event("INFO", "outbound", f"Status scheduler due check passed at {now.replace(microsecond=0).isoformat()}")
        success, message = enqueue_status_job(station_settings, trigger="scheduled")
        if success:
            set_app_setting(LAST_SCHEDULED_STATUS_AT_KEY, now.replace(microsecond=0).isoformat())
            log_event("INFO", "outbound", "Status scheduler enqueued scheduled status frame")
        else:
            log_event("WARNING", "outbound", f"Status scheduler failed to enqueue status frame: {message}")

    async def _sleep(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_schedule_due(setting_key: str, interval_minutes: int, now: datetime) -> bool:
    last_enqueued_at = _parse_timestamp(get_app_setting(setting_key))
    if last_enqueued_at is None:
        return True
    elapsed_seconds = (now - last_enqueued_at).total_seconds()
    return elapsed_seconds >= interval_minutes * 60


def _parse_proportional_step(value: str | None) -> int:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return 0
    return parsed if parsed >= 0 else 0
