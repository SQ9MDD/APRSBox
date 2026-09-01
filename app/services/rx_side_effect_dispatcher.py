from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable

from app.db import log_event


RX_SIDE_EFFECT_QUEUE_MAX_FRAMES = 2048


@dataclass(frozen=True)
class RxSideEffectRequest:
    processor: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    enqueued_monotonic: float


class RxSideEffectDispatcher:
    """Run ordered, synchronous RX observers outside the asyncio event loop."""

    def __init__(
        self,
        *,
        queue_max_frames: int = RX_SIDE_EFFECT_QUEUE_MAX_FRAMES,
        worker_name: str = "aprsbox-rx-side-effects",
    ) -> None:
        self._queue: asyncio.Queue[RxSideEffectRequest] = asyncio.Queue(
            maxsize=max(1, int(queue_max_frames))
        )
        self._worker_name = str(worker_name or "aprsbox-rx-side-effects")
        self._task: asyncio.Task[None] | None = None
        self._accepting = False
        self._high_water = 0
        self._enqueued = 0
        self._completed = 0
        self._failed = 0
        self._dropped_overflow = 0
        self._rejected_not_running = 0
        self._metrics_ms: dict[str, dict[str, float | int | None]] = {}

    async def start(self) -> None:
        if self._task is not None:
            return
        self._accepting = True
        self._task = asyncio.create_task(self._run(), name=self._worker_name)

    async def stop(self) -> None:
        """Stop accepting work, drain all accepted jobs, then stop the worker."""

        self._accepting = False
        task = self._task
        if task is None:
            return
        await self._queue.join()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self._task = None

    def is_running(self) -> bool:
        task = self._task
        return self._accepting and task is not None and not task.done()

    def enqueue(
        self,
        processor: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        enqueue_started = time.monotonic()
        if not self.is_running():
            self._rejected_not_running += 1
            self._record_metric(
                "rx_side_effect_enqueue",
                max(0.0, (time.monotonic() - enqueue_started) * 1000.0),
            )
            return False
        request = RxSideEffectRequest(
            processor=processor,
            args=tuple(args),
            kwargs=dict(kwargs),
            enqueued_monotonic=time.monotonic(),
        )
        try:
            self._queue.put_nowait(request)
        except asyncio.QueueFull:
            self._dropped_overflow += 1
            self._record_metric(
                "rx_side_effect_enqueue",
                max(0.0, (time.monotonic() - enqueue_started) * 1000.0),
            )
            return False
        self._enqueued += 1
        self._high_water = max(self._high_water, self._queue.qsize())
        self._record_metric(
            "rx_side_effect_enqueue",
            max(0.0, (time.monotonic() - enqueue_started) * 1000.0),
        )
        return True

    async def wait_until_idle(self) -> None:
        await self._queue.join()

    def snapshot(self) -> dict[str, Any]:
        return {
            "current_queue_depth": self._queue.qsize(),
            "queue_capacity": self._queue.maxsize,
            "high_water": self._high_water,
            "enqueued": self._enqueued,
            "completed": self._completed,
            "failed": self._failed,
            "dropped_overflow": self._dropped_overflow,
            "rejected_not_running": self._rejected_not_running,
            "running": self.is_running(),
            "metrics_ms": {
                name: dict(values) for name, values in self._metrics_ms.items()
            },
        }

    async def _run(self) -> None:
        while True:
            request = await self._queue.get()
            try:
                processing_started = time.monotonic()
                self._record_metric(
                    "rx_side_effect_queue_wait",
                    max(
                        0.0,
                        (processing_started - request.enqueued_monotonic) * 1000.0,
                    ),
                )
                try:
                    await asyncio.to_thread(
                        request.processor,
                        *request.args,
                        **request.kwargs,
                    )
                except Exception as exc:
                    self._failed += 1
                    await self._log_failure(exc)
                else:
                    self._completed += 1
                finally:
                    self._record_metric(
                        "rx_side_effect_processing",
                        max(0.0, (time.monotonic() - processing_started) * 1000.0),
                    )
            finally:
                self._queue.task_done()

    async def _log_failure(self, exc: Exception) -> None:
        detail = str(exc).strip() or exc.__class__.__name__
        try:
            await asyncio.to_thread(
                log_event,
                "WARNING",
                "rx_side_effects",
                f"RX side-effect worker failed: {detail}",
            )
        except Exception:
            # Logging is an observer too; its failure must not terminate the worker.
            return

    def _record_metric(self, name: str, value_ms: float) -> None:
        metric = self._metrics_ms.setdefault(
            name,
            {"count": 0, "total_ms": 0.0, "last_ms": None, "max_ms": 0.0},
        )
        metric["count"] = int(metric["count"] or 0) + 1
        metric["total_ms"] = float(metric["total_ms"] or 0.0) + value_ms
        metric["last_ms"] = value_ms
        metric["max_ms"] = max(float(metric["max_ms"] or 0.0), value_ms)
        metric["avg_ms"] = float(metric["total_ms"] or 0.0) / int(metric["count"] or 1)
