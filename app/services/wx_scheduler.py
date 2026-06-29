from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.db import get_app_setting, log_event, set_app_setting
from app.services.outbound import oldest_pending_outbound_job, pending_wx_job_count
from app.services.wx import WX_REFRESH_LAST_AT_KEY, get_wx_config, refresh_wx_runtime, safe_enqueue_wx_outbound


LAST_SCHEDULED_WX_AT_KEY = "scheduler.wx.last_enqueued_at"


class WxSchedulerService:
    def __init__(self, *, poll_interval: float = 15.0) -> None:
        self._poll_interval = poll_interval
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="aprsbox-wx-scheduler")

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
            await self._tick()
            await self._sleep(self._poll_interval)

    async def _tick(self) -> None:
        config = get_wx_config()
        if not bool(config.get("enabled")):
            return
        interval_seconds = int(config.get("refresh_interval_s") or 300)
        now = datetime.now(timezone.utc)
        last_refresh_at = _parse_timestamp(get_app_setting(WX_REFRESH_LAST_AT_KEY))
        if last_refresh_at is None or int((now - last_refresh_at).total_seconds()) >= interval_seconds:
            try:
                await asyncio.to_thread(refresh_wx_runtime, trigger="scheduled")
            except Exception as exc:
                log_event("WARNING", "wx", f"WX scheduler refresh failed: {exc}")
                return
        if pending_wx_job_count() > 0:
            pending = oldest_pending_outbound_job("wx")
            if pending is None:
                log_event("INFO", "wx", "WX scheduler skipped enqueue because a WX job is already pending")
            else:
                job_id = int(pending["id"])
                status = str(pending.get("status") or "").strip() or "unknown"
                started_at = str(pending.get("started_at") or "").strip() or "-"
                log_event(
                    "INFO",
                    "wx",
                    (
                        f"WX scheduler skipped enqueue because WX job #{job_id} is still pending "
                        f"(status={status}, started_at={started_at})"
                    ),
                )
            return
        last_enqueued_at = _parse_timestamp(get_app_setting(LAST_SCHEDULED_WX_AT_KEY))
        if last_enqueued_at is not None and int((now - last_enqueued_at).total_seconds()) < interval_seconds:
            return
        success, message = safe_enqueue_wx_outbound(trigger="scheduled")
        if success:
            set_app_setting(LAST_SCHEDULED_WX_AT_KEY, now.replace(microsecond=0).isoformat())
            log_event("INFO", "wx", "WX scheduler enqueued scheduled WX frame")
        else:
            log_event("WARNING", "wx", f"WX scheduler failed to enqueue WX frame: {message}")

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
