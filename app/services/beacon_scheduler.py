from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.db import get_app_setting, set_app_setting
from app.services.content import get_station_settings
from app.services.outbound import enqueue_beacon_job, pending_beacon_job_count


LAST_SCHEDULED_BEACON_AT_KEY = "scheduler.beacon.last_enqueued_at"


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
            self._tick()
            await self._sleep(self._poll_interval)

    def _tick(self) -> None:
        station_settings = get_station_settings()
        if not station_settings or not bool(station_settings.get("tx_enabled")):
            return

        interval_minutes = int(station_settings.get("beacon_interval_minutes") or 30)
        if interval_minutes <= 0:
            return
        if pending_beacon_job_count() > 0:
            return

        last_enqueued_at = _parse_timestamp(get_app_setting(LAST_SCHEDULED_BEACON_AT_KEY))
        now = datetime.now(timezone.utc)
        if last_enqueued_at is not None:
            elapsed_seconds = (now - last_enqueued_at).total_seconds()
            if elapsed_seconds < interval_minutes * 60:
                return

        success, _ = enqueue_beacon_job(station_settings, trigger="scheduled")
        if success:
            set_app_setting(LAST_SCHEDULED_BEACON_AT_KEY, now.replace(microsecond=0).isoformat())

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
