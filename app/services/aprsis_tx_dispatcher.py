from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any, Callable

from app.db import log_event


APRSIS_TX_QUEUE_MAX_FRAMES = 256


@dataclass(frozen=True)
class AprsIsTxRequest:
    line: str
    telemetry: dict[str, Any]
    on_result: Callable[[bool, str], Any] | None = None


class AprsIsTxDispatcher:
    def __init__(self, *, client: Any, queue_max_frames: int = APRSIS_TX_QUEUE_MAX_FRAMES) -> None:
        self._client = client
        self._queue: asyncio.Queue[AprsIsTxRequest] = asyncio.Queue(maxsize=max(1, int(queue_max_frames)))
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._high_water = 0
        self._enqueued = 0
        self._sent = 0
        self._failed = 0
        self._dropped_overflow = 0
        self._diagnostic_tasks: set[asyncio.Task[Any]] = set()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name="aprsbox-aprsis-tx-dispatcher")

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        if self._diagnostic_tasks:
            await asyncio.gather(*list(self._diagnostic_tasks), return_exceptions=True)

    def enqueue(
        self,
        *,
        line: str,
        telemetry: dict[str, Any] | None = None,
        on_result: Callable[[bool, str], Any] | None = None,
    ) -> tuple[bool, str]:
        if not self._running:
            return False, "APRS-IS TX dispatcher is not running."
        request = AprsIsTxRequest(
            line=str(line or "").rstrip("\r\n"),
            telemetry=dict(telemetry or {}),
            on_result=on_result,
        )
        try:
            self._queue.put_nowait(request)
        except asyncio.QueueFull:
            self._dropped_overflow += 1
            task = asyncio.create_task(self._handle_overflow(request))
            self._diagnostic_tasks.add(task)
            task.add_done_callback(self._diagnostic_tasks.discard)
            return False, "APRS-IS TX queue is full."
        self._enqueued += 1
        self._high_water = max(self._high_water, self._queue.qsize())
        return True, "APRS-IS TX queued."

    async def wait_until_idle(self) -> None:
        await self._queue.join()
        while self._diagnostic_tasks:
            await asyncio.gather(*list(self._diagnostic_tasks), return_exceptions=True)

    def latency_snapshot(self) -> dict[str, int]:
        return {
            "current_queue_depth": self._queue.qsize(),
            "queue_capacity": self._queue.maxsize,
            "high_water": self._high_water,
            "enqueued": self._enqueued,
            "sent": self._sent,
            "failed": self._failed,
            "dropped_overflow": self._dropped_overflow,
        }

    async def _run(self) -> None:
        while self._running:
            request = await self._queue.get()
            try:
                telemetry = dict(request.telemetry)
                telemetry["aprsis_dispatch_queue_wait_ms"] = max(
                    0.0,
                    (time.monotonic() - float(telemetry.get("aprsis_dispatch_enqueued_monotonic") or time.monotonic()))
                    * 1000.0,
                )
                try:
                    success, detail = await self._client.send_tnc2_line(
                        request.line,
                        telemetry=telemetry,
                    )
                except TypeError:
                    success, detail = await self._client.send_tnc2_line(request.line)
                if success:
                    self._sent += 1
                else:
                    self._failed += 1
                await self._notify_result(request, bool(success), str(detail or ""))
            except Exception as exc:
                self._failed += 1
                detail = str(exc).strip() or exc.__class__.__name__
                await self._notify_result(request, False, detail)
                await asyncio.to_thread(
                    log_event,
                    "WARNING",
                    "aprsis_tx_dispatcher",
                    f"APRS-IS TX worker failed: {detail}",
                )
            finally:
                self._queue.task_done()

    async def _handle_overflow(self, request: AprsIsTxRequest) -> None:
        detail = "APRS-IS TX queue is full."
        await asyncio.to_thread(
            log_event,
            "WARNING",
            "aprsis_tx_dispatcher",
            (
                "Dropped APRS-IS TX frame because the bounded queue is full "
                f"(limit={self._queue.maxsize}, drops={self._dropped_overflow})."
            ),
        )
        await self._notify_result(request, False, detail)

    @staticmethod
    async def _notify_result(request: AprsIsTxRequest, success: bool, detail: str) -> None:
        if request.on_result is None:
            return
        result = request.on_result(success, detail)
        if inspect.isawaitable(result):
            await result
