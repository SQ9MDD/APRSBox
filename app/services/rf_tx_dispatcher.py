from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass
from typing import Any

from app.db import log_event
from app.services.digi_flows import get_digi_flow_routing_snapshot, reload_digi_flow_routing_snapshot
from app.services.outbound import build_tnc2_kiss_frame, persist_outbound_frame


RF_TX_QUEUE_MAX_FRAMES = 128


@dataclass(frozen=True)
class _RfTxJob:
    interface_name: str
    line: str
    flow_id: int | None
    frame_uid: str | None
    received_monotonic: float
    max_age_seconds: float
    enqueued_monotonic: float


class RfTxDispatcher:
    """Ephemeral DIGI RF TX queues, isolated per physical interface."""

    def __init__(
        self,
        *,
        traffic_monitor: Any | None = None,
        min_tx_gap_seconds: float = 0.35,
        queue_max_frames: int = RF_TX_QUEUE_MAX_FRAMES,
    ) -> None:
        self._traffic_monitor = traffic_monitor
        self._min_tx_gap_seconds = max(0.0, float(min_tx_gap_seconds))
        self._queue_max_frames = max(1, int(queue_max_frames))
        self._known_targets: set[str] = set()
        self._queues: dict[str, asyncio.Queue[_RfTxJob]] = {}
        self._workers: dict[str, asyncio.Task[None]] = {}
        self._history_tasks: set[asyncio.Task[None]] = set()
        self._last_tx_monotonic: dict[str, float] = {}
        self._running = False
        self._max_queue_depth = 0
        self._max_queue_depth_by_interface: dict[str, int] = {}

    async def start(self) -> None:
        if self._running:
            return
        snapshot = reload_digi_flow_routing_snapshot()
        self._known_targets = {
            name
            for name, modem in snapshot.modems_by_name.items()
            if str(modem.get("modem_type") or "").strip().upper() in {"TCP", "SERIALL", "SERIAL"}
        }
        self._running = True

    async def stop(self) -> None:
        self._running = False
        workers = list(self._workers.values())
        for worker in workers:
            worker.cancel()
        for worker in workers:
            with contextlib.suppress(asyncio.CancelledError):
                await worker
        self._workers.clear()
        self._queues.clear()
        self._last_tx_monotonic.clear()
        await self._wait_for_history_persistence()

    def enqueue_digi_tx(
        self,
        *,
        interface_name: str,
        line: str,
        flow_id: int | None = None,
        frame_uid: str | None = None,
        received_monotonic: float | None = None,
        max_age_seconds: float = 5.0,
    ) -> tuple[bool, str]:
        target = str(interface_name or "").strip()
        tnc2_line = str(line or "").strip()
        if not self._running:
            return False, "RF TX dispatcher is not running."
        if not target:
            return False, "RF target is required."
        if target not in self._known_targets:
            return False, "Selected interface does not exist."
        if not tnc2_line:
            return False, "Packet line is required."

        queue = self._queues.get(target)
        if queue is None:
            queue = asyncio.Queue(maxsize=self._queue_max_frames)
            self._queues[target] = queue
            self._workers[target] = asyncio.create_task(
                self._run_interface(target, queue),
                name=f"aprsbox-rf-tx-{target}",
            )
        now = time.monotonic()
        job = _RfTxJob(
            interface_name=target,
            line=tnc2_line,
            flow_id=flow_id,
            frame_uid=str(frame_uid).strip() if frame_uid is not None else None,
            received_monotonic=float(received_monotonic) if isinstance(received_monotonic, (int, float)) else now,
            max_age_seconds=max(0.1, float(max_age_seconds)),
            enqueued_monotonic=now,
        )
        try:
            queue.put_nowait(job)
        except asyncio.QueueFull:
            return False, f"RF TX queue is full for interface {target}."
        self._max_queue_depth = max(self._max_queue_depth, queue.qsize())
        self._max_queue_depth_by_interface[target] = max(
            self._max_queue_depth_by_interface.get(target, 0),
            queue.qsize(),
        )
        return True, f"DIGI TX queued in RAM for interface {target}."

    async def wait_until_idle(self) -> None:
        await asyncio.gather(*(queue.join() for queue in list(self._queues.values())))
        await self._wait_for_history_persistence()

    def latency_snapshot(self) -> dict[str, Any]:
        depths = {name: queue.qsize() for name, queue in self._queues.items()}
        return {
            "queue_depth_by_interface": depths,
            "max_queue_depth_by_interface": dict(self._max_queue_depth_by_interface),
            "current_queue_depth": sum(depths.values()),
            "max_queue_depth": self._max_queue_depth,
            "worker_count": len(self._workers),
        }

    async def _run_interface(self, target: str, queue: asyncio.Queue[_RfTxJob]) -> None:
        while self._running:
            job = await queue.get()
            try:
                await self._send(job)
            except Exception as exc:
                error = str(exc).strip() or exc.__class__.__name__
                log_event("WARNING", "rf_tx_dispatcher", f"DIGI TX failed via {target}: {error}")
            finally:
                queue.task_done()

    async def _send(self, job: _RfTxJob) -> None:
        age_seconds = max(0.0, time.monotonic() - job.received_monotonic)
        if age_seconds > job.max_age_seconds:
            log_event(
                "WARNING",
                "rf_tx_dispatcher",
                f"Dropped stale DIGI TX via {job.interface_name}: age={age_seconds:.1f}s limit={job.max_age_seconds:.1f}s",
            )
            return
        modem = dict(get_digi_flow_routing_snapshot().modems_by_name.get(job.interface_name) or {})
        if not modem:
            raise RuntimeError("Selected interface no longer exists.")
        if int(modem.get("enabled") or 0) != 1:
            raise RuntimeError("Selected interface is disabled.")
        if int(modem.get("tx_blocked") or 0) == 1:
            raise RuntimeError("TX is blocked on selected interface.")

        previous = self._last_tx_monotonic.get(job.interface_name)
        if previous is not None:
            remaining = self._min_tx_gap_seconds - (time.monotonic() - previous)
            if remaining > 0:
                await asyncio.sleep(remaining)
        if time.monotonic() - job.received_monotonic > job.max_age_seconds:
            return

        frame = build_tnc2_kiss_frame(job.line)
        interface_id = int(modem["id"])
        sent = False
        if self._traffic_monitor is not None:
            sent = await self._traffic_monitor.send_outbound_frame(interface_id=interface_id, frame=frame)

        modem_type = str(modem.get("modem_type") or "").strip().upper()
        if modem_type == "SERIAL":
            modem_type = "SERIALL"
        if not sent and modem_type == "TCP":
            endpoint = self._parse_endpoint(str(modem.get("device_path") or ""))
            if endpoint is None:
                raise RuntimeError("Selected interface has an invalid TCP endpoint.")
            reader, writer = await asyncio.wait_for(asyncio.open_connection(*endpoint), timeout=5)
            try:
                writer.write(frame)
                await writer.drain()
                sent = True
            finally:
                writer.close()
                with contextlib.suppress(OSError):
                    await writer.wait_closed()
                _ = reader
        if not sent:
            raise RuntimeError("Active shared KISS runtime could not send the frame.")

        self._last_tx_monotonic[job.interface_name] = time.monotonic()
        self._schedule_history_persistence(
            source=job.interface_name,
            interface_id=interface_id,
            band=str(modem.get("band") or "").strip(),
            line=job.line,
            payload_hex=frame.hex(" ").upper(),
        )

    def _schedule_history_persistence(
        self,
        *,
        source: str,
        interface_id: int,
        band: str,
        line: str,
        payload_hex: str,
    ) -> None:
        task = asyncio.create_task(
            self._persist_sent_frame(
                source=source,
                interface_id=interface_id,
                band=band,
                line=line,
                payload_hex=payload_hex,
            ),
            name=f"aprsbox-rf-tx-history-{source}",
        )
        self._history_tasks.add(task)
        task.add_done_callback(self._history_tasks.discard)

    async def _persist_sent_frame(
        self,
        *,
        source: str,
        interface_id: int,
        band: str,
        line: str,
        payload_hex: str,
    ) -> None:
        try:
            await asyncio.to_thread(
                persist_outbound_frame,
                source=source,
                interface_id=interface_id,
                band=band,
                line=line,
                payload_hex=payload_hex,
                source_kind="rf",
            )
        except Exception as exc:
            error = str(exc).strip() or exc.__class__.__name__
            await asyncio.to_thread(
                log_event,
                "WARNING",
                "rf_tx_dispatcher",
                f"Could not persist sent DIGI TX via {source}: {error}",
            )

    async def _wait_for_history_persistence(self) -> None:
        while self._history_tasks:
            await asyncio.gather(*tuple(self._history_tasks), return_exceptions=True)

    @staticmethod
    def _parse_endpoint(value: str) -> tuple[str, int] | None:
        host, separator, port_text = value.strip().rpartition(":")
        if not separator or not host or not port_text:
            return None
        try:
            port = int(port_text)
        except ValueError:
            return None
        if not 1 <= port <= 65535:
            return None
        return host.strip(), port
