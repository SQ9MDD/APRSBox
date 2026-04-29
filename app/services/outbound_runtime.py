from __future__ import annotations

import asyncio
import time
from datetime import date, datetime, timezone
from typing import Any

from app.db import execute, fetch_one, log_event, utc_now
from app.services.messages import (
    QUERY_MESSAGE_KIND,
    expire_direct_message_timeouts,
    mark_message_failed,
    register_direct_message_transmission,
    register_query_message_transmission,
)
from app.services.outbound import (
    OUTBOUND_KIND_DIGI_TX,
    build_beacon_tnc2,
    build_message_tnc2,
    build_object_tnc2,
    build_status_tnc2,
    build_wx_tnc2,
    build_tnc2_kiss_frame,
    claim_next_outbound_job,
    mark_outbound_job_failed,
    mark_outbound_job_skipped,
    mark_outbound_job_sent,
    persist_outbound_frame,
)
from app.services.serial_tnc import (
    close_serial_device,
    normalize_serial_baud_rate,
    normalize_serial_device_path,
    open_serial_device,
    write_serial_data,
)
from app.services.traffic import TrafficMonitorService


class OutboundService:
    def __init__(
        self,
        *,
        poll_interval: float = 1.0,
        traffic_monitor: TrafficMonitorService | None = None,
        min_tx_gap_seconds: float = 0.35,
    ) -> None:
        self._poll_interval = poll_interval
        self._traffic_monitor = traffic_monitor
        self._min_tx_gap_seconds = max(0.0, float(min_tx_gap_seconds))
        self._last_tx_monotonic_by_interface: dict[int, float] = {}
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
            expire_direct_message_timeouts()
            job = claim_next_outbound_job()
            if job is None:
                await self._sleep(self._poll_interval)
                continue
            await self._process_job(job)

    async def _process_job(self, job: dict[str, Any]) -> None:
        job_id = int(job["id"])
        try:
            modem_type = str(job.get("modem_type") or "").strip().upper()
            if modem_type == "SERIAL":
                modem_type = "SERIALL"
            interface_name = str(job.get("interface_name") or f"interface-{job.get('interface_id') or 'unknown'}")
            device_path = str(job.get("device_path") or "").strip()
            interface_id = job.get("interface_id")
            try:
                normalized_interface_id = int(interface_id) if interface_id is not None else None
            except (TypeError, ValueError):
                normalized_interface_id = None

            kind = str(job.get("kind") or "").strip()
            payload = job.get("payload") or {}
            skip_reason = _skip_reason_for_expired_aprs_content(kind=kind, payload=payload, now=datetime.now(timezone.utc))
            if skip_reason:
                mark_outbound_job_skipped(job_id, skip_reason)
                log_event("INFO", "outbound", f"Skipped {kind} outbound job #{job_id}: {skip_reason}")
                return
            if kind == "beacon":
                tnc2_line = build_beacon_tnc2(payload)
            elif kind == "status":
                tnc2_line = build_status_tnc2(payload)
            elif kind == "object":
                tnc2_line = build_object_tnc2(payload)
            elif kind == "message":
                tnc2_line = build_message_tnc2(payload)
            elif kind == "wx":
                tnc2_line = build_wx_tnc2(payload)
            elif kind == OUTBOUND_KIND_DIGI_TX:
                tnc2_line = str(payload.get("line") or "").strip()
                if not tnc2_line:
                    raise ValueError("DIGI TX outbound job is missing packet line.")
            else:
                raise ValueError(f"Unsupported outbound job kind: {kind or '-'}")
            log_event("INFO", "outbound", f"Generating {kind} frame for outbound job #{job_id}")
            frame = build_tnc2_kiss_frame(tnc2_line)
            if job.get("interface_enabled") in {0, "0", False}:
                skip_reason = f"TX skipped: interface {interface_name} is disabled in configuration."
                mark_outbound_job_skipped(job_id, skip_reason)
                persist_outbound_frame(
                    source=interface_name,
                    interface_id=normalized_interface_id,
                    band=str(job.get("band") or "").strip(),
                    line=tnc2_line,
                    command="TX-SKIP",
                    payload_hex=frame.hex(" ").upper(),
                )
                message_kind = str(payload.get("message_kind") or "").strip()
                if kind == "message" and payload.get("aprs_message_id") is not None:
                    if message_kind == "direct_message":
                        register_direct_message_transmission(int(payload["aprs_message_id"]), job_id)
                    elif message_kind == QUERY_MESSAGE_KIND:
                        register_query_message_transmission(int(payload["aprs_message_id"]), job_id)
                elif kind in {"beacon", "status"} and payload.get("aprs_message_id") is not None:
                    register_query_message_transmission(int(payload["aprs_message_id"]), job_id)
                log_event("WARNING", "outbound", f"Skipped {kind} outbound job #{job_id}: interface {interface_name} is disabled")
                return
            if normalized_interface_id is not None and self._is_interface_tx_blocked(normalized_interface_id):
                skip_reason = f"TX skipped: TX is blocked on interface {interface_name}."
                mark_outbound_job_skipped(job_id, skip_reason)
                persist_outbound_frame(
                    source=interface_name,
                    interface_id=normalized_interface_id,
                    band=str(job.get("band") or "").strip(),
                    line=tnc2_line,
                    command="TX-SKIP",
                    payload_hex=frame.hex(" ").upper(),
                )
                message_kind = str(payload.get("message_kind") or "").strip()
                if kind == "message" and payload.get("aprs_message_id") is not None:
                    if message_kind == "direct_message":
                        register_direct_message_transmission(int(payload["aprs_message_id"]), job_id)
                    elif message_kind == QUERY_MESSAGE_KIND:
                        register_query_message_transmission(int(payload["aprs_message_id"]), job_id)
                elif kind in {"beacon", "status"} and payload.get("aprs_message_id") is not None:
                    register_query_message_transmission(int(payload["aprs_message_id"]), job_id)
                log_event(
                    "WARNING",
                    "outbound",
                    f"Skipped {kind} outbound job #{job_id}: TX is blocked on interface {interface_name}",
                )
                return
            tx_gap_seconds = self._resolve_tx_gap_seconds(job)
            await self._wait_for_tx_gap(interface_id=normalized_interface_id, gap_seconds=tx_gap_seconds)
            if modem_type == "TCP":
                if self._traffic_monitor is not None:
                    sent_via_monitor = await self._traffic_monitor.send_outbound_frame(
                        interface_id=normalized_interface_id,
                        frame=frame,
                    )
                    if sent_via_monitor:
                        persist_outbound_frame(
                            source=interface_name,
                            interface_id=normalized_interface_id,
                            band=str(job.get("band") or "").strip(),
                            line=tnc2_line,
                            payload_hex=frame.hex(" ").upper(),
                        )
                        mark_outbound_job_sent(job_id)
                        self._remember_tx_timestamp(interface_id=normalized_interface_id)
                        message_kind = str(payload.get("message_kind") or "").strip()
                        if kind == "message" and payload.get("aprs_message_id") is not None:
                            if message_kind == "direct_message":
                                register_direct_message_transmission(int(payload["aprs_message_id"]), job_id)
                            elif message_kind == QUERY_MESSAGE_KIND:
                                register_query_message_transmission(int(payload["aprs_message_id"]), job_id)
                        elif kind in {"beacon", "status"} and payload.get("aprs_message_id") is not None:
                            register_query_message_transmission(int(payload["aprs_message_id"]), job_id)
                        log_event("INFO", "outbound", f"Sent {kind} outbound job #{job_id} via {interface_name}")
                        return
                    self._log_monitor_fallback(
                        job_id=job_id,
                        kind=kind,
                        interface_name=interface_name,
                        transport="TCP",
                    )
                endpoint = self._parse_endpoint(device_path)
                if endpoint is None:
                    raise ValueError(f"Interface {interface_name} has invalid TCP endpoint.")
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
            elif modem_type in {"SERIALL", "SERIAL"}:
                if self._traffic_monitor is not None:
                    sent_via_monitor = await self._traffic_monitor.send_outbound_frame(
                        interface_id=normalized_interface_id,
                        frame=frame,
                    )
                    if sent_via_monitor:
                        persist_outbound_frame(
                            source=interface_name,
                            interface_id=normalized_interface_id,
                            band=str(job.get("band") or "").strip(),
                            line=tnc2_line,
                            payload_hex=frame.hex(" ").upper(),
                        )
                        mark_outbound_job_sent(job_id)
                        self._remember_tx_timestamp(interface_id=normalized_interface_id)
                        message_kind = str(payload.get("message_kind") or "").strip()
                        if kind == "message" and payload.get("aprs_message_id") is not None:
                            if message_kind == "direct_message":
                                register_direct_message_transmission(int(payload["aprs_message_id"]), job_id)
                            elif message_kind == QUERY_MESSAGE_KIND:
                                register_query_message_transmission(int(payload["aprs_message_id"]), job_id)
                        elif kind in {"beacon", "status"} and payload.get("aprs_message_id") is not None:
                            register_query_message_transmission(int(payload["aprs_message_id"]), job_id)
                        log_event("INFO", "outbound", f"Sent {kind} outbound job #{job_id} via {interface_name}")
                        return
                    self._log_monitor_fallback(
                        job_id=job_id,
                        kind=kind,
                        interface_name=interface_name,
                        transport="serial",
                    )
                serial_path = normalize_serial_device_path(device_path)
                baud_rate = normalize_serial_baud_rate(job.get("baud_rate"))
                serial_fd = await asyncio.to_thread(open_serial_device, serial_path, baud_rate)
                try:
                    await asyncio.to_thread(write_serial_data, serial_fd, frame, drain=True)
                finally:
                    await asyncio.to_thread(close_serial_device, serial_fd)
            else:
                raise ValueError(f"Interface {interface_name} uses unsupported modem type {modem_type or '-'}")

            persist_outbound_frame(
                source=interface_name,
                interface_id=int(job["interface_id"]) if job.get("interface_id") is not None else None,
                band=str(job.get("band") or "").strip(),
                line=tnc2_line,
                payload_hex=frame.hex(" ").upper(),
            )
            mark_outbound_job_sent(job_id)
            self._remember_tx_timestamp(interface_id=normalized_interface_id)
            message_kind = str(payload.get("message_kind") or "").strip()
            if kind == "message" and payload.get("aprs_message_id") is not None:
                if message_kind == "direct_message":
                    register_direct_message_transmission(int(payload["aprs_message_id"]), job_id)
                elif message_kind == QUERY_MESSAGE_KIND:
                    register_query_message_transmission(int(payload["aprs_message_id"]), job_id)
            elif kind in {"beacon", "status"} and payload.get("aprs_message_id") is not None:
                register_query_message_transmission(int(payload["aprs_message_id"]), job_id)
            log_event("INFO", "outbound", f"Sent {kind} outbound job #{job_id} via {interface_name}")
        except Exception as exc:
            error = str(exc).strip() or exc.__class__.__name__
            mark_outbound_job_failed(job_id, error)
            kind = str(job.get("kind") or "unknown").strip() or "unknown"
            payload = job.get("payload") or {}
            if kind in {"message", "beacon", "status"} and (
                kind != "message" or str(payload.get("message_kind") or "").strip() in {"direct_message", QUERY_MESSAGE_KIND}
            ) and payload.get("aprs_message_id") is not None:
                mark_message_failed(int(payload["aprs_message_id"]), error)
            log_event("WARNING", "outbound", f"{kind.capitalize()} outbound job #{job_id} failed: {error}")

    async def _sleep(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass

    def _resolve_tx_gap_seconds(self, job: dict[str, Any]) -> float:
        try:
            configured = float(job.get("tx_min_gap_seconds"))
        except (TypeError, ValueError):
            configured = self._min_tx_gap_seconds
        return max(0.0, configured)

    async def _wait_for_tx_gap(self, *, interface_id: int | None, gap_seconds: float) -> None:
        if gap_seconds <= 0 or interface_id is None:
            return
        previous = self._last_tx_monotonic_by_interface.get(interface_id)
        if previous is None:
            return
        remaining = gap_seconds - (time.monotonic() - previous)
        if remaining > 0:
            await self._sleep(remaining)

    def _remember_tx_timestamp(self, *, interface_id: int | None) -> None:
        if interface_id is None:
            return
        self._last_tx_monotonic_by_interface[interface_id] = time.monotonic()

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

    def _is_interface_tx_blocked(self, interface_id: int) -> bool:
        try:
            row = fetch_one("SELECT tx_blocked FROM modems WHERE id = ?", (interface_id,))
        except Exception:
            return False
        if row is None:
            return False
        try:
            return bool(int(row["tx_blocked"]))
        except (TypeError, ValueError, KeyError):
            return False

    def _log_monitor_fallback(self, *, job_id: int, kind: str, interface_name: str, transport: str) -> None:
        message = (
            f"Traffic monitor could not send {kind} outbound job #{job_id} via {interface_name}; "
            f"using direct {transport} fallback."
        )
        log_event("WARNING", "outbound", message)
        log_event("WARNING", "system", message)


def _skip_reason_for_expired_aprs_content(*, kind: str, payload: dict[str, Any], now: datetime) -> str | None:
    if kind == "object":
        object_id = _normalize_payload_id(payload.get("object_id"))
        if object_id is None:
            return None
        row = fetch_one("SELECT valid_until_utc FROM aprs_objects WHERE id = ?", (object_id,))
        if row is None:
            return None
        valid_until_utc = str(row["valid_until_utc"] or "").strip()
        if not _is_expired_utc_date(valid_until_utc, now):
            return None
        execute(
            """
            UPDATE aprs_objects
            SET is_enabled = 0,
                updated_at = ?
            WHERE id = ?
              AND is_enabled = 1
            """,
            (utc_now(), object_id),
        )
        return f"TX skipped: object #{object_id} expired on {valid_until_utc} UTC."

    if kind == "message":
        message_id = _normalize_payload_id(payload.get("message_id"))
        if message_id is None:
            return None
        row = fetch_one("SELECT valid_until_utc FROM bulletins WHERE id = ?", (message_id,))
        if row is None:
            return None
        valid_until_utc = str(row["valid_until_utc"] or "").strip()
        if not _is_expired_utc_date(valid_until_utc, now):
            return None
        execute(
            """
            UPDATE bulletins
            SET is_enabled = 0,
                updated_at = ?
            WHERE id = ?
              AND is_enabled = 1
            """,
            (utc_now(), message_id),
        )
        return f"TX skipped: bulletin #{message_id} expired on {valid_until_utc} UTC."

    return None


def _normalize_payload_id(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_utc_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _is_expired_utc_date(value: str | None, now: datetime) -> bool:
    valid_until = _parse_utc_date(value)
    if valid_until is None:
        return False
    return now.date() > valid_until
