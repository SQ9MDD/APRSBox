from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone

from app.db import connection_scope, execute, fetch_all, log_event, set_app_setting, utc_now
from app.services.activation_schedule import compute_activation_state
from app.services.content import get_station_settings, station_has_tx_target
from app.services.outbound import enqueue_message_job, latest_message_dispatch_at


BULLETIN_LAST_ENQUEUED_KEY_PREFIX = "scheduler.message.last_enqueued_at."


class BulletinSchedulerService:
    def __init__(self, *, poll_interval: float = 15.0, jitter_seconds: tuple[int, int] = (5, 10)) -> None:
        self._poll_interval = poll_interval
        self._jitter_seconds = jitter_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="aprsbox-bulletin-scheduler")

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
        with connection_scope():
            self._tick_scoped()

    def _tick_scoped(self) -> None:
        station_settings = get_station_settings()
        if not station_settings or not station_settings.get("callsign") or not station_has_tx_target(station_settings):
            return

        now = datetime.now(timezone.utc)
        due_rows = []
        for row in fetch_all(
            """
            SELECT bulletins.id, bulletins.message_kind, bulletins.bulletin_code, bulletins.group_name,
                   bulletins.is_enabled, bulletins.interval_minutes, bulletins.valid_until_utc,
                   activation_mode, active_from_utc, active_until_utc, first_activation_utc,
                   recurrence_duration_minutes, recurrence_interval_value, recurrence_interval_unit, recurrence_until_utc,
                   path, message_text, bulletins.updated_at, scheduler_setting.value AS last_enqueued_at
            FROM bulletins
            LEFT JOIN app_settings AS scheduler_setting
              ON scheduler_setting.key = ? || bulletins.id
            WHERE bulletins.is_enabled = 1
            ORDER BY bulletins.id ASC
            """,
            (BULLETIN_LAST_ENQUEUED_KEY_PREFIX,),
        ):
            bulletin = dict(row)
            activation_state = compute_activation_state(bulletin, now)
            if activation_state.reason == "manual_expired":
                _disable_expired_bulletin(int(bulletin["id"]), str(bulletin.get("valid_until_utc") or ""))
                continue
            if not activation_state.active_now:
                continue
            interval_minutes = int(bulletin.get("interval_minutes") or 30)
            last_enqueued = _parse_timestamp(bulletin.get("last_enqueued_at"))
            if last_enqueued is not None and (now - last_enqueued).total_seconds() < interval_minutes * 60:
                continue
            due_rows.append(bulletin)

        if not due_rows:
            return

        cursor = latest_message_dispatch_at()
        for bulletin in due_rows:
            scheduled_for = now
            if cursor is not None:
                scheduled_for = max(now, cursor + timedelta(seconds=random.randint(*self._jitter_seconds)))
            success, _ = enqueue_message_job(bulletin, station_settings, trigger="scheduled", scheduled_for=scheduled_for)
            if success:
                timestamp = scheduled_for.replace(microsecond=0).isoformat()
                set_app_setting(f"{BULLETIN_LAST_ENQUEUED_KEY_PREFIX}{bulletin['id']}", timestamp)
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


def _disable_expired_bulletin(bulletin_id: int, valid_until_utc: str) -> None:
    execute(
        """
        UPDATE bulletins
        SET is_enabled = 0,
            updated_at = ?
        WHERE id = ?
          AND is_enabled = 1
        """,
        (utc_now(), bulletin_id),
    )
    log_event(
        "INFO",
        "outbound",
        f"Auto-disabled bulletin #{bulletin_id}: validity date {valid_until_utc} UTC has passed.",
    )
