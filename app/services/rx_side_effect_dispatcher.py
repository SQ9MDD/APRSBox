from __future__ import annotations

import asyncio
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from app.db import log_event


RX_SIDE_EFFECT_QUEUE_MAX_FRAMES = 2048


@dataclass(frozen=True)
class RxSideEffectStageSample:
    name: str
    elapsed_ms: float


class RxSideEffectStageCollector:
    def __init__(self) -> None:
        self.samples: list[RxSideEffectStageSample] = []
        self.stage_order: list[str] = []
        self.radar_metrics: dict[str, dict[str, float | int | None]] = {}

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        normalized_name = str(name or "unknown").strip() or "unknown"
        self.stage_order.append(normalized_name)
        started = time.monotonic()
        try:
            yield
        finally:
            self.samples.append(
                RxSideEffectStageSample(
                    name=normalized_name,
                    elapsed_ms=max(0.0, (time.monotonic() - started) * 1000.0),
                )
            )

    @contextmanager
    def measure_radar(self, name: str) -> Iterator[None]:
        normalized_name = str(name or "unknown").strip() or "unknown"
        started = time.monotonic()
        try:
            yield
        finally:
            self._update_local_metric(
                normalized_name,
                max(0.0, (time.monotonic() - started) * 1000.0),
            )

    def _update_local_metric(self, name: str, value_ms: float) -> None:
        metric = self.radar_metrics.setdefault(
            name,
            {"count": 0, "total_ms": 0.0, "last_ms": None, "max_ms": 0.0},
        )
        metric["count"] = int(metric["count"] or 0) + 1
        metric["total_ms"] = float(metric["total_ms"] or 0.0) + value_ms
        metric["last_ms"] = value_ms
        metric["max_ms"] = max(float(metric["max_ms"] or 0.0), value_ms)


_active_stage_collector: ContextVar[RxSideEffectStageCollector | None] = ContextVar(
    "rx_side_effect_stage_collector",
    default=None,
)
_active_radar_stage_collector: ContextVar[RxSideEffectStageCollector | None] = ContextVar(
    "rx_radar_stage_collector",
    default=None,
)
_noop_rx_side_effect_stage = nullcontext()


def current_rx_side_effect_stage_collector() -> RxSideEffectStageCollector | None:
    return _active_stage_collector.get()


def current_rx_radar_stage_collector() -> RxSideEffectStageCollector | None:
    return _active_radar_stage_collector.get()


@contextmanager
def collect_rx_radar_stages(
    collector: RxSideEffectStageCollector | None,
) -> Iterator[RxSideEffectStageCollector | None]:
    token = _active_radar_stage_collector.set(collector)
    try:
        yield collector
    finally:
        _active_radar_stage_collector.reset(token)


def rx_side_effect_stage(
    collector: RxSideEffectStageCollector | None,
    name: str,
):
    if collector is None:
        return _noop_rx_side_effect_stage
    return collector.measure(name)


def rx_radar_stage(
    collector: RxSideEffectStageCollector | None,
    name: str,
):
    if collector is None:
        return _noop_rx_side_effect_stage
    return collector.measure_radar(name)


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
        self._stage_breakdown_ms: dict[str, dict[str, float | int | None]] = {}
        self._last_stage_order: list[str] = []
        self._radar_breakdown_ms: dict[str, dict[str, float | int | None]] = {}

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
            "stage_breakdown_ms": {
                name: dict(values) for name, values in self._stage_breakdown_ms.items()
            },
            "last_stage_order": list(self._last_stage_order),
            "radar_breakdown_ms": {
                name: dict(values) for name, values in self._radar_breakdown_ms.items()
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
                collector = RxSideEffectStageCollector()
                collector_token = _active_stage_collector.set(collector)
                try:
                    await asyncio.to_thread(
                        request.processor,
                        *request.args,
                        **request.kwargs,
                    )
                except Exception as exc:
                    self._failed += 1
                    with collector.measure("worker_exception_log"):
                        await self._log_failure(exc)
                else:
                    self._completed += 1
                finally:
                    _active_stage_collector.reset(collector_token)
                    self._record_stage_breakdown(collector)
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

    def _record_stage_breakdown(self, collector: RxSideEffectStageCollector) -> None:
        self._last_stage_order = list(collector.stage_order)
        for sample in collector.samples:
            self._update_metric(
                self._stage_breakdown_ms,
                sample.name,
                sample.elapsed_ms,
            )
        for name, metric in collector.radar_metrics.items():
            self._merge_metric(self._radar_breakdown_ms, name, metric)

    def _record_metric(self, name: str, value_ms: float) -> None:
        self._update_metric(self._metrics_ms, name, value_ms)

    @staticmethod
    def _update_metric(
        metrics: dict[str, dict[str, float | int | None]],
        name: str,
        value_ms: float,
    ) -> None:
        metric = metrics.setdefault(
            name,
            {"count": 0, "total_ms": 0.0, "last_ms": None, "max_ms": 0.0},
        )
        metric["count"] = int(metric["count"] or 0) + 1
        metric["total_ms"] = float(metric["total_ms"] or 0.0) + value_ms
        metric["last_ms"] = value_ms
        metric["max_ms"] = max(float(metric["max_ms"] or 0.0), value_ms)
        metric["avg_ms"] = float(metric["total_ms"] or 0.0) / int(metric["count"] or 1)

    @staticmethod
    def _merge_metric(
        metrics: dict[str, dict[str, float | int | None]],
        name: str,
        sample: dict[str, float | int | None],
    ) -> None:
        metric = metrics.setdefault(
            name,
            {"count": 0, "total_ms": 0.0, "last_ms": None, "max_ms": 0.0},
        )
        metric["count"] = int(metric["count"] or 0) + int(sample["count"] or 0)
        metric["total_ms"] = float(metric["total_ms"] or 0.0) + float(sample["total_ms"] or 0.0)
        metric["last_ms"] = sample["last_ms"]
        metric["max_ms"] = max(
            float(metric["max_ms"] or 0.0),
            float(sample["max_ms"] or 0.0),
        )
        metric["avg_ms"] = float(metric["total_ms"] or 0.0) / int(metric["count"] or 1)
