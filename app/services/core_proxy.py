from __future__ import annotations

import asyncio
from threading import Lock
from typing import Any

from app.services.core_client import get_core_traffic_snapshot, unavailable_traffic_snapshot


class CoreTrafficProxy:
    def __init__(self, *, refresh_interval: float = 1.0) -> None:
        self._refresh_interval = refresh_interval
        self._lock = Lock()
        self._snapshot: dict[str, Any] = unavailable_traffic_snapshot("Waiting for aprs-core.")
        self._revision = 0
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._updated_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="aprsbox-core-traffic-proxy")

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

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._snapshot)

    def revision(self) -> int:
        with self._lock:
            return self._revision

    async def wait_for_update(self, previous_revision: int, timeout: float = 15.0) -> tuple[int, dict[str, Any]]:
        while True:
            current_revision = self.revision()
            if current_revision != previous_revision:
                return current_revision, self.snapshot()

            self._updated_event.clear()
            try:
                await asyncio.wait_for(self._updated_event.wait(), timeout=timeout)
            except TimeoutError:
                return self.revision(), self.snapshot()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            snapshot = await asyncio.to_thread(get_core_traffic_snapshot)
            changed = self._update_snapshot(snapshot)
            if changed:
                self._updated_event.set()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._refresh_interval)
            except TimeoutError:
                pass

    def _update_snapshot(self, snapshot: dict[str, Any]) -> bool:
        with self._lock:
            if snapshot == self._snapshot:
                return False
            self._snapshot = snapshot
            self._revision += 1
            return True
