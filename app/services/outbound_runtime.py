from __future__ import annotations

import asyncio
from typing import Any

from app.db import log_event
from app.services.outbound import (
    build_beacon_tnc2,
    build_tnc2_kiss_frame,
    claim_next_outbound_job,
    mark_outbound_job_failed,
    mark_outbound_job_sent,
    persist_outbound_frame,
)


class OutboundService:
    def __init__(self, *, poll_interval: float = 1.0) -> None:
        self._poll_interval = poll_interval
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="aprsbox-outbound-worker")

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
            job = claim_next_outbound_job()
            if job is None:
                await self._sleep(self._poll_interval)
                continue
            await self._process_job(job)

    async def _process_job(self, job: dict[str, Any]) -> None:
        job_id = int(job["id"])
        try:
            modem_type = str(job.get("modem_type") or "").strip().upper()
            interface_name = str(job.get("interface_name") or f"interface-{job.get('interface_id') or 'unknown'}")
            device_path = str(job.get("device_path") or "").strip()
            if modem_type != "TCP":
                raise ValueError(f"Interface {interface_name} uses unsupported modem type {modem_type or '-'}")
            endpoint = self._parse_endpoint(device_path)
            if endpoint is None:
                raise ValueError(f"Interface {interface_name} has invalid TCP endpoint.")

            kind = str(job.get("kind") or "").strip()
            if kind != "beacon":
                raise ValueError(f"Unsupported outbound job kind: {kind or '-'}")

            tnc2_line = build_beacon_tnc2(job.get("payload") or {})
            frame = build_tnc2_kiss_frame(tnc2_line)
            host, port = endpoint
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)
            try:
                writer.write(frame)
                await writer.drain()
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
                _ = reader

            persist_outbound_frame(
                source=interface_name,
                line=tnc2_line,
                payload_hex=frame.hex(" ").upper(),
            )
            mark_outbound_job_sent(job_id)
            log_event("INFO", "outbound", f"Sent outbound job #{job_id} via {interface_name}")
        except Exception as exc:
            error = str(exc).strip() or exc.__class__.__name__
            mark_outbound_job_failed(job_id, error)
            log_event("WARNING", "outbound", f"Outbound job #{job_id} failed: {error}")

    async def _sleep(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass

    def _parse_endpoint(self, value: str) -> tuple[str, int] | None:
        host, separator, port_text = value.strip().rpartition(":")
        if not separator or not host or not port_text:
            return None
        try:
            port = int(port_text)
        except ValueError:
            return None
        if port < 1 or port > 65535:
            return None
        return host.strip(), port
