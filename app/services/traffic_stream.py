from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any, Callable, Hashable

from app.db import log_event


class TrafficStreamCapacityError(RuntimeError):
    pass


class TrafficSnapshotBroadcaster:
    def __init__(
        self,
        *,
        snapshot_provider: Callable[[], dict[str, Any]],
        change_token_provider: Callable[[], Hashable] | None = None,
        tick_seconds: float = 1.0,
        heartbeat_seconds: float = 25.0,
        max_clients: int = 20,
    ) -> None:
        self._snapshot_provider = snapshot_provider
        self._change_token_provider = change_token_provider
        self._tick_seconds = max(0.1, float(tick_seconds))
        self._heartbeat_seconds = max(1.0, float(heartbeat_seconds))
        self._max_clients = max(1, int(max_clients))
        self._task: asyncio.Task[None] | None = None
        self._runner_lock = asyncio.Lock()
        self._subscribers_lock = asyncio.Lock()
        self._subscribers: dict[int, asyncio.Queue[str]] = {}
        self._next_subscriber_id = 1
        self._last_payload = ""
        self._last_change_token: Hashable | object = object()
        self._last_heartbeat_monotonic = 0.0

    async def start(self) -> None:
        await self._ensure_running(log_on_start=True)

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            log_event("INFO", "traffic", "Traffic SSE broadcaster stopped.")
        async with self._subscribers_lock:
            self._subscribers.clear()
        self._last_payload = ""
        self._last_change_token = object()
        self._last_heartbeat_monotonic = 0.0

    async def subscribe(self) -> tuple[int, asyncio.Queue[str]]:
        await self._ensure_running(log_on_start=False)
        async with self._subscribers_lock:
            current = len(self._subscribers)
            if current >= self._max_clients:
                log_event(
                    "WARNING",
                    "traffic",
                    (
                        "Traffic SSE client limit reached "
                        f"({current}/{self._max_clients}). Rejecting new stream subscription."
                    ),
                )
                raise TrafficStreamCapacityError("Traffic SSE client limit reached.")
            subscriber_id = self._next_subscriber_id
            self._next_subscriber_id += 1
            queue: asyncio.Queue[str] = asyncio.Queue(maxsize=2)
            self._subscribers[subscriber_id] = queue
            if self._last_payload and self._change_token_provider is None:
                queue.put_nowait(f"data: {self._last_payload}\n\n")
            return subscriber_id, queue

    async def unsubscribe(self, subscriber_id: int) -> None:
        async with self._subscribers_lock:
            self._subscribers.pop(subscriber_id, None)

    async def _ensure_running(self, *, log_on_start: bool) -> None:
        task = self._task
        if task is not None and not task.done():
            return
        if task is not None and task.done():
            self._task = None
            with contextlib.suppress(asyncio.CancelledError):
                exception = task.exception()
                if exception is not None:
                    log_event("WARNING", "traffic", f"Traffic SSE broadcaster task ended unexpectedly: {exception}.")
        async with self._runner_lock:
            if self._task is not None and not self._task.done():
                return
            self._task = asyncio.create_task(self._run(), name="aprsbox-traffic-sse-broadcaster")
            if log_on_start:
                log_event("INFO", "traffic", "Traffic SSE broadcaster started.")

    async def _run(self) -> None:
        self._last_heartbeat_monotonic = time.monotonic()
        while True:
            try:
                subscriber_count = await self._subscriber_count()
                now = time.monotonic()

                if subscriber_count > 0:
                    should_refresh = True
                    if self._change_token_provider is not None:
                        change_token = await asyncio.to_thread(self._change_token_provider)
                        should_refresh = change_token != self._last_change_token
                        self._last_change_token = change_token
                    if should_refresh:
                        snapshot = await asyncio.to_thread(self._snapshot_provider)
                        payload = json.dumps(snapshot, separators=(",", ":"))
                        if payload != self._last_payload:
                            self._last_payload = payload
                            await self._fanout(f"data: {payload}\n\n")

                    if now - self._last_heartbeat_monotonic >= self._heartbeat_seconds:
                        await self._fanout(": ping\n\n")
                        self._last_heartbeat_monotonic = now
                else:
                    # Avoid expensive DB snapshot calls when no UI client is connected.
                    self._last_heartbeat_monotonic = now

                await asyncio.sleep(self._tick_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log_event("WARNING", "traffic", f"Traffic SSE broadcaster tick failed: {exc}.")
                await asyncio.sleep(self._tick_seconds)

    async def _subscriber_count(self) -> int:
        async with self._subscribers_lock:
            return len(self._subscribers)

    async def _fanout(self, event: str) -> None:
        async with self._subscribers_lock:
            subscribers = list(self._subscribers.values())
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Keep only the newest payload/heartbeat for slow clients.
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(event)
