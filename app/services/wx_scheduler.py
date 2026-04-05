from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.db import get_app_setting, log_event
from app.services.wx import WX_REFRESH_LAST_AT_KEY, get_wx_config, refresh_wx_runtime


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
            self._tick()
            await self._sleep(self._poll_interval)

    def _tick(self) -> None:
        config = get_wx_config()
        if not bool(config.get("enabled")):
            return
        interval_seconds = int(config.get("refresh_interval_s") or 300)
        last_refresh_at = _parse_timestamp(get_app_setting(WX_REFRESH_LAST_AT_KEY))
        now = datetime.now(timezone.utc)
        if last_refresh_at is not None and int((now - last_refresh_at).total_seconds()) < interval_seconds:
            return
        try:
            refresh_wx_runtime(trigger="scheduled")
        except Exception as exc:
            log_event("WARNING", "wx", f"WX scheduler refresh failed: {exc}")

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
