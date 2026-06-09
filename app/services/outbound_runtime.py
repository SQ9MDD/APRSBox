from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from app.db import execute, fetch_one, log_event, utc_now
from app.services.activation_schedule import compute_activation_state
from app.services.messages import (
    QUERY_MESSAGE_KIND,
    expire_direct_message_timeouts,
    mark_message_failed,
    register_direct_message_transmission,
    register_query_message_transmission,
)
from app.services.digi_flows import LOCAL_TX_SOURCE_KIND, LOCAL_TX_SOURCE_REF
from app.services.outbound import (
    LOCAL_TX_ORIGIN,
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
    recover_stale_processing_beacon_jobs,
    recover_stale_processing_wx_jobs,
)
from app.services.traffic import TrafficMonitorService

KISS_FEND = 0xC0


def _kiss_frame_hex_preview(frame: bytes, *, max_bytes: int = 32) -> str:
    if not frame:
        return "<empty>"
    if len(frame) <= max_bytes:
        return frame.hex(" ").upper()
    head_len = max_bytes // 2
    tail_len = max_bytes - head_len
    head = frame[:head_len].hex(" ").upper()
    tail = frame[-tail_len:].hex(" ").upper()
    return f"{head} ... {tail}"


class OutboundService:
    def __init__(
        self,
        *,
        poll_interval: float = 1.0,
        traffic_monitor: TrafficMonitorService | None = None,
        digi_flow_runtime: Any | None = None,
        min_tx_gap_seconds: float = 0.35,
    ) -> None:
        self._poll_interval = poll_interval
        self._traffic_monitor = traffic_monitor
        self._digi_flow_runtime = digi_flow_runtime
        self._min_tx_gap_seconds = max(0.0, float(min_tx_gap_seconds))
        self._last_tx_monotonic_by_interface: dict[int, float] = {}
        self._local_tx_forwarded_event_ids: set[str] = set()
        self._local_tx_forwarded_event_order: list[str] = []
        self._local_tx_forwarded_event_limit = 512
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        recovered_job_ids = recover_stale_processing_beacon_jobs()
        for job_id in recovered_job_ids:
            log_event(
                "WARNING",
                "outbound",
                (
                    f"Recovered stale beacon outbound job #{job_id}: "
                    "beacon was not transmitted before APRSBox core restart."
                ),
            )
        recovered_wx_job_ids = recover_stale_processing_wx_jobs()
        for job_id in recovered_wx_job_ids:
            message = (
                f"Recovered stale WX outbound job #{job_id}: "
                "WX frame was not transmitted before APRSBox core restart."
            )
            log_event("WARNING", "outbound", message)
            log_event("WARNING", "wx", message)
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
            skip_reason = _skip_reason_for_inactive_aprs_content(kind=kind, payload=payload, now=datetime.now(timezone.utc))
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
            self._forward_local_tx_to_digi_flow(job=job, kind=kind, payload=payload, tnc2_line=tnc2_line)
            log_event("INFO", "outbound", f"Generating {kind} frame for outbound job #{job_id}")
            if kind == "wx":
                log_event("INFO", "wx", f"Generating WX frame for outbound job #{job_id}")
            if kind != OUTBOUND_KIND_DIGI_TX and _payload_flag(payload.get("internal_tx_only"), default=False):
                mark_outbound_job_sent(job_id)
                message_kind = str(payload.get("message_kind") or "").strip()
                if kind == "message" and payload.get("aprs_message_id") is not None:
                    if message_kind == "direct_message":
                        register_direct_message_transmission(int(payload["aprs_message_id"]), job_id)
                    elif message_kind == QUERY_MESSAGE_KIND:
                        register_query_message_transmission(int(payload["aprs_message_id"]), job_id)
                elif kind in {"beacon", "status"} and payload.get("aprs_message_id") is not None:
                    register_query_message_transmission(int(payload["aprs_message_id"]), job_id)
                log_event("INFO", "outbound", f"Sent {kind} outbound job #{job_id} via Internal TX routing")
                if kind == "wx":
                    log_event("INFO", "wx", f"Sent WX outbound job #{job_id} via Internal TX routing")
                return
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
                if kind == "wx":
                    log_event("WARNING", "wx", f"Skipped WX outbound job #{job_id}: interface {interface_name} is disabled")
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
                if kind == "wx":
                    log_event("WARNING", "wx", f"Skipped WX outbound job #{job_id}: TX is blocked on interface {interface_name}")
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
                        if kind == "wx":
                            log_event("INFO", "wx", f"Sent WX outbound job #{job_id} via {interface_name}")
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
                if self._traffic_monitor is None:
                    message = (
                        f"Serial TX for {kind} outbound job #{job_id} via {interface_name} requires "
                        "an active traffic monitor runtime. Direct serial fallback is disabled."
                    )
                    log_event("ERROR", "outbound", message)
                    log_event("ERROR", "system", message)
                    raise RuntimeError(message)
                self._log_serial_runtime_tx(
                    job_id=job_id,
                    kind=kind,
                    interface_name=interface_name,
                    frame=frame,
                    using_shared_runtime=True,
                )
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
                    if kind == "wx":
                        log_event("INFO", "wx", f"Sent WX outbound job #{job_id} via {interface_name}")
                    return
                self._log_serial_runtime_tx(
                    job_id=job_id,
                    kind=kind,
                    interface_name=interface_name,
                    frame=frame,
                    using_shared_runtime=False,
                )
                message = (
                    f"Traffic monitor could not send {kind} outbound job #{job_id} via {interface_name}. "
                    "Serial TX must use the active shared runtime; no direct fallback will be used."
                )
                log_event("WARNING", "outbound", message)
                log_event("WARNING", "system", message)
                raise RuntimeError(message)
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
            if kind == "wx":
                log_event("INFO", "wx", f"Sent WX outbound job #{job_id} via {interface_name}")
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
            if kind == "wx":
                log_event("WARNING", "wx", f"WX outbound job #{job_id} failed: {error}")

    async def _sleep(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass

    def _forward_local_tx_to_digi_flow(self, *, job: dict[str, Any], kind: str, payload: dict[str, Any], tnc2_line: str) -> None:
        if kind == OUTBOUND_KIND_DIGI_TX or self._digi_flow_runtime is None:
            return

        purpose_by_kind = {
            "beacon": "beacon",
            "status": "status",
            "object": "object",
            "message": "message",
            "wx": "wx",
        }
        purpose = purpose_by_kind.get(str(kind or "").strip())
        if not purpose:
            return

        raw_metadata = payload.get("local_tx_metadata")
        metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
        metadata["origin"] = str(metadata.get("origin") or LOCAL_TX_ORIGIN).strip() or LOCAL_TX_ORIGIN
        metadata["local_generated"] = _payload_flag(metadata.get("local_generated"), default=True)
        metadata["own_station"] = _payload_flag(metadata.get("own_station"), default=True)
        metadata["frame_purpose"] = str(metadata.get("frame_purpose") or purpose).strip() or purpose

        event_id = str(payload.get("local_tx_event_id") or "").strip()
        forward_key = event_id or f"legacy:{kind}:{tnc2_line}"
        if forward_key in self._local_tx_forwarded_event_ids:
            return
        self._local_tx_forwarded_event_ids.add(forward_key)
        self._local_tx_forwarded_event_order.append(forward_key)
        if len(self._local_tx_forwarded_event_order) > self._local_tx_forwarded_event_limit:
            stale_key = self._local_tx_forwarded_event_order.pop(0)
            self._local_tx_forwarded_event_ids.discard(stale_key)

        created_at = str(job.get("scheduled_at") or "").strip() or None
        try:
            self._digi_flow_runtime.enqueue_tnc2_frame(
                source_kind=LOCAL_TX_SOURCE_KIND,
                source_ref=LOCAL_TX_SOURCE_REF,
                raw_payload=tnc2_line,
                created_at=created_at,
                metadata=metadata,
            )
        except Exception as exc:
            error = str(exc).strip() or exc.__class__.__name__
            log_event("WARNING", "outbound", f"Failed to enqueue Local TX frame to routing runtime: {error}")

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

    def _log_serial_runtime_tx(
        self,
        *,
        job_id: int,
        kind: str,
        interface_name: str,
        frame: bytes,
        using_shared_runtime: bool,
    ) -> None:
        command_text = "n/a"
        if len(frame) >= 2 and frame[0] == KISS_FEND:
            command = frame[1]
            command_text = f"0x{command:02X}"
        preview = _kiss_frame_hex_preview(frame)
        if using_shared_runtime:
            message = (
                f"Serial TX {kind} job #{job_id} via {interface_name} uses shared runtime: "
                f"len={len(frame)} cmd={command_text} frame={preview}"
            )
            log_event("DEBUG", "outbound", message)
            return
        message = (
            f"Serial TX {kind} job #{job_id} via {interface_name} shared runtime unavailable: "
            f"len={len(frame)} cmd={command_text} frame={preview}"
        )
        log_event("WARNING", "outbound", message)


def _payload_flag(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _skip_reason_for_inactive_aprs_content(*, kind: str, payload: dict[str, Any], now: datetime) -> str | None:
    if kind == "object":
        if _payload_flag(payload.get("force_send"), default=False):
            return None
        object_id = _normalize_payload_id(payload.get("object_id"))
        if object_id is None:
            return None
        row = fetch_one("SELECT * FROM aprs_objects WHERE id = ?", (object_id,))
        if row is None:
            return None
        record = dict(row)
        activation_state = compute_activation_state(record, now)
        if activation_state.active_now:
            return None
        if activation_state.reason == "manual_expired":
            valid_until_utc = str(record.get("valid_until_utc") or "").strip()
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
        return f"TX skipped: object #{object_id} is outside its activation window ({activation_state.reason})."

    if kind == "message":
        message_id = _normalize_payload_id(payload.get("message_id"))
        if message_id is None:
            return None
        row = fetch_one("SELECT * FROM bulletins WHERE id = ?", (message_id,))
        if row is None:
            return None
        record = dict(row)
        activation_state = compute_activation_state(record, now)
        if activation_state.active_now:
            return None
        if activation_state.reason == "manual_expired":
            valid_until_utc = str(record.get("valid_until_utc") or "").strip()
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
        return f"TX skipped: bulletin #{message_id} is outside its activation window ({activation_state.reason})."

    return None


def _normalize_payload_id(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
