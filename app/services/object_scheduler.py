from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone

from app.db import fetch_all, get_app_setting, set_app_setting
from app.services.content import get_station_settings
from app.services.outbound import enqueue_object_job, latest_object_dispatch_at


OBJECT_LAST_ENQUEUED_KEY_PREFIX = "scheduler.object.last_enqueued_at."


class ObjectSchedulerService:
    def __init__(self, *, poll_interval: float = 15.0, jitter_seconds: tuple[int, int] = (5, 10)) -> None:
        self._poll_interval = poll_interval
        self._jitter_seconds = jitter_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="aprsbox-object-scheduler")

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
        if not station_settings or not station_settings.get("callsign") or station_settings.get("beacon_interface_id") in {None, ""}:
            return

        now = datetime.now(timezone.utc)
        due_objects = []
        for row in fetch_all(
            """
            SELECT id, name, lifetime, state, is_enabled, interval_minutes, latitude, longitude, symbol_table, symbol_code, path, comment, updated_at
            FROM aprs_objects
            WHERE is_enabled = 1
            ORDER BY id ASC
            """
        ):
            obj = dict(row)
            interval_minutes = int(obj.get("interval_minutes") or 30)
            last_enqueued = _parse_timestamp(get_app_setting(f"{OBJECT_LAST_ENQUEUED_KEY_PREFIX}{obj['id']}"))
            if last_enqueued is not None and (now - last_enqueued).total_seconds() < interval_minutes * 60:
                continue
            due_objects.append(obj)

        if not due_objects:
            return

        cursor = latest_object_dispatch_at()
        for obj in due_objects:
            scheduled_for = now
            if cursor is not None:
                scheduled_for = max(now, cursor + timedelta(seconds=random.randint(*self._jitter_seconds)))
            success, _ = enqueue_object_job(obj, station_settings, trigger="scheduled", scheduled_for=scheduled_for)
            if success:
                timestamp = scheduled_for.replace(microsecond=0).isoformat()
                set_app_setting(f"{OBJECT_LAST_ENQUEUED_KEY_PREFIX}{obj['id']}", timestamp)
                cursor = scheduled_for

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
