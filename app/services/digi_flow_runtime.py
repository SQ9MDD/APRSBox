from __future__ import annotations

import asyncio
import contextlib
import math
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from app.db import fetch_one, log_event, utc_now
from app.i18n import get_app_language, get_format_translator, get_translator
from app.services.aprsis import (
    APRSIS_TX_MAX_FRAME_AGE_SECONDS,
    APRSIS_STRICT_REASON_BLOCKED_NOGATE_RFONLY,
    APRSIS_STRICT_REASON_BLOCKED_TCPIP_TCPXX,
    APRSIS_STRICT_REASON_MALFORMED_THIRD_PARTY,
    APRSIS_STRICT_REASON_OTHER,
    AprsisClientService,
    record_aprsis_strict_reject,
    record_aprsis_tx_result,
)
from app.services.content import get_station_settings, parse_tnc2_frame
from app.services.aprsis_rf import (
    ALLOW_RULES_STEP_TYPE,
    APRSIS_FLOW_SOURCE_KIND,
    MESSAGE_DELIVERY_STEP_TYPE,
    RF_GUARD_DEFAULTS,
    RF_GUARD_STEP_TYPE,
    RF_TX_GUARD_STEP_TYPE,
    aprsis_rf_guard_reject_reason,
    logical_packet_hash,
    matches_default_deny_filter,
    normalize_default_deny_config,
    normalize_rf_guard_config,
    record_aprsis_rf_stat,
    validate_aprsis_rf_target,
)
from app.services.igate_messaging import (
    clear_pending_sender_position,
    evaluate_message_delivery,
    mark_pending_sender_position,
    message_return_capable_for_rf_source,
)
from app.services.digi_flows import LOCAL_TX_SOURCE_KIND, get_digi_flow, list_enabled_digi_flows, log_digi_flow_event
from app.services.outbound import (
    APRSIS_TO_RF_ORIGIN,
    build_aprsis_third_party_tnc2,
    enqueue_digi_tx_job,
    persist_outbound_frame,
)
from app.services.traffic_source import APRSIS_SOURCE_KIND
from app.services.messages import split_callsign_ssid

_N_N_PATH_RE = re.compile(r"^(?P<alias>[A-Z0-9]+)(?P<width>\d+)-(?P<remaining>\d+)$")
_DUPLICATE_FILTER_WINDOW_DEFAULT_SEC = 5
_DUPLICATE_FILTER_WINDOW_ALLOWED = {2, 3, 4, 5, 6, 7}
DIGI_GUARD_LOCAL_MESSAGE_MY_STATION = "DIGI_GUARD_LOCAL_MESSAGE_MY_STATION"
DIGI_GUARD_LOCAL_QUERY_MY_STATION = "DIGI_GUARD_LOCAL_QUERY_MY_STATION"
DIGI_GUARD_LOCAL_MESSAGE_WX = "DIGI_GUARD_LOCAL_MESSAGE_WX"
DIGI_GUARD_LOCAL_QUERY_WX = "DIGI_GUARD_LOCAL_QUERY_WX"
DIGI_GUARD_LOCAL_SOURCE_MY_STATION = "DIGI_GUARD_LOCAL_SOURCE_MY_STATION"
DIGI_GUARD_LOCAL_SOURCE_WX = "DIGI_GUARD_LOCAL_SOURCE_WX"
DIGI_GUARD_THIRD_PARTY = "DIGI_GUARD_THIRD_PARTY"
DIGI_GUARD_ALREADY_REPEATED_BY_LOCAL = "DIGI_GUARD_ALREADY_REPEATED_BY_LOCAL"
_LOCAL_IDENTITY_MY = "my_station"
_LOCAL_IDENTITY_WX = "wx_station"
DIGI_FLOW_QUEUE_MAX_FRAMES = 256


def _monotonic_delta_ms(start: Any, end: Any) -> float | None:
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return None
    delta_ms = (float(end) - float(start)) * 1000.0
    if delta_ms < 0:
        return 0.0
    return delta_ms


def _t(message: object) -> str:
    return get_translator(get_app_language())(message)


def _tf(message: object, params: dict[str, object] | None = None) -> str:
    return get_format_translator(get_app_language())(message, params)


@dataclass
class _ViscousDelayEntry:
    flow_id: int
    step_id: int
    source_callsign: str
    payload: str
    window_sec: int
    expires_at: float
    first_context: dict[str, Any] | None
    first_next_step_index: int
    duplicate_seen: bool = False
    first_finalized: bool = False
    cleanup_task: asyncio.Task[None] | None = None


@dataclass
class _AprsisRfSeenEntry:
    is_seen_at: float | None = None
    is_frame_uid: str | None = None
    rf_seen_at: float | None = None
    queued_at: float | None = None


@dataclass
class _AprsisRfPendingEntry:
    flow_id: int
    guard_step_id: int | None
    target_step_id: int
    packet_hash: str
    source_callsign: str
    context: dict[str, Any]
    created_at: float
    delay_sec: float
    cancel_event: asyncio.Event
    cleanup_task: asyncio.Task[None] | None = None


@dataclass
class _TokenBucket:
    tokens: float
    updated_at: float


class DigiFlowRuntimeService:
    def __init__(
        self,
        *,
        poll_interval: float = 0.5,
        aprsis_client: AprsisClientService | None = None,
        aprsis_rf_delay_override: float | None = None,
        queue_max_frames: int = DIGI_FLOW_QUEUE_MAX_FRAMES,
        aprsis_tx_max_frame_age_seconds: float = APRSIS_TX_MAX_FRAME_AGE_SECONDS,
    ) -> None:
        self._poll_interval = poll_interval
        self._aprsis_client = aprsis_client
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max(1, int(queue_max_frames)))
        self._aprsis_tx_max_frame_age_seconds = max(0.1, float(aprsis_tx_max_frame_age_seconds))
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._viscous_delay_lock = asyncio.Lock()
        self._viscous_delay_entries: dict[tuple[int, int, str, str], _ViscousDelayEntry] = {}
        self._pending_viscous_wait_count = 0
        self._rate_limit_last_passed: dict[tuple[int, int, str, str], float] = {}
        self._aprsis_rf_delay_override = aprsis_rf_delay_override
        self._aprsis_rf_seen: OrderedDict[str, _AprsisRfSeenEntry] = OrderedDict()
        self._aprsis_rf_pending: dict[tuple[int, str], _AprsisRfPendingEntry] = {}
        self._aprsis_rf_flow_buckets: dict[tuple[int, str], _TokenBucket] = {}
        self._aprsis_rf_source_buckets: dict[tuple[int, str, str], _TokenBucket] = {}
        self._aprsis_rf_recipient_buckets: dict[tuple[int, str, str], _TokenBucket] = {}

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="aprsbox-digi-flow-runtime")

    async def stop(self) -> None:
        self._stop_event.set()
        cleanup_tasks: list[asyncio.Task[None]] = []
        async with self._viscous_delay_lock:
            cleanup_tasks = [
                entry.cleanup_task
                for entry in self._viscous_delay_entries.values()
                if entry.cleanup_task is not None and not entry.cleanup_task.done()
            ]
            self._viscous_delay_entries.clear()
            self._pending_viscous_wait_count = 0
            self._rate_limit_last_passed.clear()
        aprsis_rf_tasks = [
            entry.cleanup_task
            for entry in self._aprsis_rf_pending.values()
            if entry.cleanup_task is not None and not entry.cleanup_task.done()
        ]
        self._aprsis_rf_pending.clear()
        self._aprsis_rf_seen.clear()
        self._aprsis_rf_flow_buckets.clear()
        self._aprsis_rf_source_buckets.clear()
        self._aprsis_rf_recipient_buckets.clear()
        for task in aprsis_rf_tasks:
            task.cancel()
        for task in aprsis_rf_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for task in cleanup_tasks:
            task.cancel()
        for task in cleanup_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def wait_until_idle(self) -> None:
        await self._queue.join()
        while True:
            async with self._viscous_delay_lock:
                pending = self._pending_viscous_wait_count
            if pending <= 0 and not self._aprsis_rf_pending:
                return
            await asyncio.sleep(0.01)

    def enqueue_tnc2_frame(
        self,
        *,
        source_kind: str,
        source_ref: str,
        raw_payload: str,
        frame_uid: str | None = None,
        created_at: str | None = None,
        rx_received_monotonic: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        enqueue_monotonic = time.monotonic()
        frame = self._build_frame(
            source_kind=source_kind,
            source_ref=source_ref,
            raw_payload=raw_payload,
            frame_uid=frame_uid,
            created_at=created_at,
            enqueue_monotonic=enqueue_monotonic,
            rx_received_monotonic=rx_received_monotonic,
            metadata=metadata,
        )
        try:
            self._queue.put_nowait(frame)
        except asyncio.QueueFull:
            matching_flows = self._matching_flows(
                source_kind=str(frame["source_kind"]),
                source_ref=str(frame["source_ref"]),
            )
            aprsis_targeted = any(
                str(flow.get("target_kind") or "").strip() == "tx_aprsis"
                for flow in matching_flows
            )
            if aprsis_targeted:
                record_aprsis_tx_result(sent=False, frame_line=str(frame["raw_payload"]))
            log_event(
                "WARNING",
                "digi_flow_runtime",
                (
                    "Dropped routing frame because the bounded queue is full "
                    f"(limit={self._queue.maxsize}) | frame_uid={frame['frame_uid']} | "
                    f"source={frame['source_kind']}:{frame['source_ref']} | line={frame['raw_payload']}"
                ),
            )
            return {
                "frame_uid": frame["frame_uid"],
                "created_at": frame["created_at"],
                "queue_depth": self._queue.qsize(),
                "parsed": bool(frame["parsed"]),
                "accepted": False,
                "drop_reason": "routing_queue_full",
            }
        source_is_aprsis = str(frame["source_kind"]) == APRSIS_FLOW_SOURCE_KIND
        log_event(
            "DEBUG" if source_is_aprsis else "INFO",
            "digi_flow_runtime",
            (
                "Enqueued DIGI Flow frame "
                f"{frame['frame_uid']} from {frame['source_kind']}:{frame['source_ref']} "
                f"(queue_depth={self._queue.qsize()}) | line={frame['raw_payload']}"
            ),
        )
        return {
            "frame_uid": frame["frame_uid"],
            "created_at": frame["created_at"],
            "queue_depth": self._queue.qsize(),
            "parsed": bool(frame["parsed"]),
            "accepted": True,
        }

    def enqueue_rx_tnc2_frame(
        self,
        line: str,
        *,
        source_ref: str,
        rx_received_at: str | None = None,
        rx_received_monotonic: float | None = None,
    ) -> None:
        parsed = parse_tnc2_frame(line)
        packet_hash = logical_packet_hash(parsed)
        if packet_hash:
            now = time.monotonic()
            self._prune_aprsis_rf_state(now)
            seen = self._aprsis_rf_seen.setdefault(packet_hash, _AprsisRfSeenEntry())
            seen.rf_seen_at = now
            self._aprsis_rf_seen.move_to_end(packet_hash)
            for (pending_flow_id, pending_hash), entry in list(self._aprsis_rf_pending.items()):
                _ = pending_flow_id
                if pending_hash == packet_hash:
                    entry.cancel_event.set()
        matching_flows = self._matching_flows(source_kind="receiver_rf", source_ref=source_ref)
        if not matching_flows:
            log_event(
                "INFO",
                "digi_flow_runtime",
                f"Ignored RF frame for source {source_ref} because no enabled DIGI Flow matched that receiver.",
            )
            return
        self.enqueue_tnc2_frame(
            source_kind="receiver_rf",
            source_ref=source_ref,
            raw_payload=line,
            created_at=rx_received_at,
            rx_received_monotonic=rx_received_monotonic,
        )

    def enqueue_aprsis_tnc2_frame(
        self,
        line: str,
        *,
        source_ref: str,
        source_interface_id: int | None = None,
        rx_received_at: str | None = None,
        rx_received_monotonic: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        matching_flows = self._matching_flows(source_kind=APRSIS_FLOW_SOURCE_KIND, source_ref=source_ref)
        if not matching_flows:
            log_event(
                "DEBUG",
                "digi_flow_runtime",
                f"Ignored APRS-IS frame for interface {source_ref}: no enabled Packet Routing flow matched.",
            )
            return
        normalized_metadata = dict(metadata or {})
        if source_interface_id is not None:
            normalized_metadata["aprsis_interface_id"] = int(source_interface_id)
        self.enqueue_tnc2_frame(
            source_kind=APRSIS_FLOW_SOURCE_KIND,
            source_ref=source_ref,
            raw_payload=line,
            created_at=rx_received_at,
            rx_received_monotonic=rx_received_monotonic,
            metadata=normalized_metadata,
        )

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                frame = await asyncio.wait_for(self._queue.get(), timeout=self._poll_interval)
            except TimeoutError:
                continue

            try:
                await self._process_frame(frame)
            except Exception as exc:
                error = str(exc).strip() or exc.__class__.__name__
                log_event("WARNING", "digi_flow_runtime", f"Failed to process DIGI Flow frame {frame['frame_uid']}: {error}")
            finally:
                self._queue.task_done()

    async def _process_frame(self, frame: dict[str, Any]) -> None:
        flows = self._matching_flows(
            source_kind=str(frame["source_kind"]),
            source_ref=str(frame["source_ref"]),
        )
        if not flows:
            return

        for flow in flows:
            flow_id = int(flow["id"])
            if str(frame.get("source_kind") or "") == APRSIS_FLOW_SOURCE_KIND:
                record_aprsis_rf_stat(flow_id, "received_from_aprsis")
            flow_name = str(flow.get("name") or f"flow-{flow_id}")
            source_label = f"{frame['source_kind']}:{frame['source_ref']}"
            log_digi_flow_event(
                frame_uid=str(frame["frame_uid"]),
                flow_id=flow_id,
                step_id=None,
                event_type="frame_received",
                decision="queued",
                message=f"Frame accepted from {source_label} | line={frame['raw_payload']}",
                created_at=str(frame["created_at"]),
            )
            log_digi_flow_event(
                frame_uid=str(frame["frame_uid"]),
                flow_id=flow_id,
                step_id=None,
                event_type="flow_matched",
                decision="matched",
                message=f"Matched flow {flow_name}.",
                created_at=str(frame["created_at"]),
            )
            context = {
                "flow": flow,
                "frame_uid": str(frame["frame_uid"]),
                "created_at": str(frame["created_at"]),
                "enqueue_monotonic": frame.get("enqueue_monotonic"),
                "rx_received_monotonic": frame.get("rx_received_monotonic"),
                "source_kind": str(frame["source_kind"]),
                "source_ref": str(frame["source_ref"]),
                "raw_payload": str(frame["raw_payload"]),
                "current_line": str(frame["raw_payload"]),
                "parsed": dict(frame["parsed"]) if frame["parsed"] else None,
                "original_parsed": dict(frame["parsed"]) if frame["parsed"] else None,
                "metadata": dict(frame.get("metadata") or {}),
            }
            await self._execute_flow(context)

    def _matching_flows(self, *, source_kind: str, source_ref: str) -> list[dict[str, Any]]:
        normalized_kind = str(source_kind or "").strip()
        normalized_ref = str(source_ref or "").strip()
        flows = list_enabled_digi_flows(source_kind=normalized_kind)
        if normalized_kind != "receiver_rf":
            return [flow for flow in flows if str(flow.get("source_ref") or "").strip() == normalized_ref]
        return [
            flow
            for flow in flows
            if _receiver_source_ref_matches(str(flow.get("source_ref") or ""), normalized_ref)
        ]

    async def _execute_flow(self, context: dict[str, Any], *, start_index: int = 0) -> None:
        flow = context["flow"]
        flow_id = int(flow["id"])
        last_decision = "continue"

        steps = list(flow.get("steps") or [])
        for step_index in range(start_index, len(steps)):
            step = steps[step_index]
            step_id = int(step["id"])
            step_type = str(step["step_type"])
            step_title = str(step.get("title") or step_type)
            if int(step.get("enabled") or 0) != 1:
                log_digi_flow_event(
                    frame_uid=context["frame_uid"],
                    flow_id=flow_id,
                    step_id=step_id,
                    event_type="step_skipped",
                    decision="disabled",
                    message=f"Skipped disabled step {step_title}.",
                )
                continue

            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="step_entered",
                decision="continue",
                message=f"Entering step {step_title}.",
            )
            result = await self._execute_step(context, step, step_index=step_index)
            last_decision = str(result["decision"])
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="step_decision",
                decision=last_decision,
                message=f"Step {step_title} returned decision {last_decision}.",
            )
            if last_decision == "defer":
                return
            if last_decision != "continue":
                self._log_pipeline_finished(context, decision=last_decision)
                return

        self._log_pipeline_finished(context, decision=last_decision)

    async def _execute_step(self, context: dict[str, Any], step: dict[str, Any], *, step_index: int) -> dict[str, str]:
        step_type = str(step["step_type"])
        if step_type in {"receiver_rf", "receiver_aprsis", LOCAL_TX_SOURCE_KIND}:
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=int(context["flow"]["id"]),
                step_id=int(step["id"]),
                event_type="source_step",
                decision="continue",
                message=f"Source step confirmed for {context['source_kind']}:{context['source_ref']}.",
            )
            if step_type == APRSIS_FLOW_SOURCE_KIND and not any(
                str(candidate.get("step_type") or "") == RF_GUARD_STEP_TYPE
                for candidate in list(context["flow"].get("steps") or [])[1:-1]
            ):
                return self._execute_aprsis_rf_input_guard(context, None)
            return {"decision": "continue"}
        if step_type == RF_GUARD_STEP_TYPE:
            return self._execute_aprsis_rf_input_guard(context, step)
        if step_type == MESSAGE_DELIVERY_STEP_TYPE:
            return self._execute_aprsis_message_delivery(context, step)
        if step_type == RF_TX_GUARD_STEP_TYPE:
            return self._execute_aprsis_rf_tx_guard(context, step)
        if step_type == ALLOW_RULES_STEP_TYPE:
            return self._execute_aprsis_allow_rules(context, step)
        if step_type == "filter_dupe":
            return await self._execute_duplicate_filter(context, step, step_index=step_index)
        if step_type == "filter_callsign":
            return self._execute_callsign_filter(context, step)
        if step_type == "filter_path":
            return self._execute_path_rule(context, step)
        if step_type == "filter_strict":
            return self._execute_strict_filter(context, step)
        if step_type == "filter_direct_only":
            return self._execute_direct_only_filter(context, step)
        if step_type == "filter_digi":
            return self._execute_digi_filter(context, step)
        if step_type == "filter_packet_type":
            return self._execute_packet_type_filter(context, step)
        if step_type == "filter_icon":
            return self._execute_icon_filter(context, step)
        if step_type == "filter_distance":
            return self._execute_distance_filter(context, step)
        if step_type == "filter_rate_limit":
            return self._execute_rate_limit_filter(context, step)
        if step_type == "action_log":
            deny_result = self._aprsis_default_deny_result(context, step)
            if deny_result is not None:
                return deny_result
            return self._execute_log_only(context, step)
        if step_type == "action_drop":
            deny_result = self._aprsis_default_deny_result(context, step)
            if deny_result is not None:
                return deny_result
            return self._execute_drop(context, step)
        if step_type == "tx_rf":
            deny_result = self._aprsis_default_deny_result(context, step)
            if deny_result is not None:
                return deny_result
            return await self._execute_tx_rf(context, step)
        if step_type == "tx_aprsis":
            return await self._execute_tx_aprsis(context, step)

        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=int(context["flow"]["id"]),
            step_id=int(step["id"]),
            event_type="step_stub",
            decision="continue",
            message=f"Step type {step_type} is not implemented in ETAP 2 and was skipped.",
        )
        return {"decision": "continue"}

    def _execute_aprsis_rf_input_guard(
        self,
        context: dict[str, Any],
        step: dict[str, Any] | None,
    ) -> dict[str, str]:
        if str(context.get("source_kind") or "") != APRSIS_FLOW_SOURCE_KIND:
            return {"decision": "continue"}
        if bool(context.get("aprsis_rf_guard_input_checked")):
            return {"decision": "continue"}

        flow = dict(context.get("flow") or {})
        flow_id = int(flow["id"])
        step_id = _optional_int((step or {}).get("id"))
        tx_guard_step = next(
            (
                candidate
                for candidate in list(flow.get("steps") or [])[1:-1]
                if str(candidate.get("step_type") or "") == RF_TX_GUARD_STEP_TYPE
            ),
            None,
        )
        try:
            guard_config = normalize_rf_guard_config(
                (tx_guard_step or {}).get("config")
                or (step or {}).get("config")
                or RF_GUARD_DEFAULTS
            )
        except ValueError:
            guard_config = dict(RF_GUARD_DEFAULTS)
        context["aprsis_rf_guard_config"] = guard_config

        target_kind = str(flow.get("target_kind") or "").strip()
        if target_kind not in {"tx_rf", "action_drop", "action_log"}:
            return self._drop_aprsis_rf(
                context,
                step_id=step_id,
                reason_code="invalid_target_type",
                stat_counter="dropped_safety_guard",
            )
        if target_kind == "tx_rf":
            _target, target_reason = validate_aprsis_rf_target(flow.get("target_ref"), require_active=True)
            if target_reason:
                return self._drop_aprsis_rf(
                    context,
                    step_id=step_id,
                    reason_code=target_reason,
                    stat_counter="dropped_safety_guard",
                )

        parsed = context.get("parsed")
        reject_reason = aprsis_rf_guard_reject_reason(parsed)
        if reject_reason:
            return self._drop_aprsis_rf(
                context,
                step_id=step_id,
                reason_code=reject_reason,
                stat_counter="dropped_safety_guard",
            )

        packet_hash = logical_packet_hash(parsed)
        if not packet_hash:
            return self._drop_aprsis_rf(
                context,
                step_id=step_id,
                reason_code="invalid_aprs",
                stat_counter="dropped_safety_guard",
            )
        now = time.monotonic()
        self._prune_aprsis_rf_state(now)
        seen = self._aprsis_rf_seen.setdefault(packet_hash, _AprsisRfSeenEntry())
        duplicate_window = float(guard_config["duplicate_window_sec"])
        if seen.rf_seen_at is not None and now - seen.rf_seen_at <= duplicate_window:
            return self._drop_aprsis_rf(
                context,
                step_id=step_id,
                reason_code="duplicate_rf_seen",
                stat_counter="dropped_duplicate",
            )
        if seen.queued_at is not None and now - seen.queued_at <= duplicate_window:
            return self._drop_aprsis_rf(
                context,
                step_id=step_id,
                reason_code="duplicate_is_seen",
                stat_counter="dropped_duplicate",
            )
        frame_uid = str(context.get("frame_uid") or "")
        if (
            seen.is_seen_at is not None
            and seen.is_frame_uid != frame_uid
            and now - seen.is_seen_at <= duplicate_window
        ):
            return self._drop_aprsis_rf(
                context,
                step_id=step_id,
                reason_code="duplicate_is_seen",
                stat_counter="dropped_duplicate",
            )
        seen.is_seen_at = now
        seen.is_frame_uid = frame_uid
        self._aprsis_rf_seen.move_to_end(packet_hash)
        context["normalized_packet_hash"] = packet_hash
        context["aprsis_rf_guard_input_checked"] = True
        log_digi_flow_event(
            frame_uid=frame_uid,
            flow_id=flow_id,
            step_id=step_id,
            event_type="rf_guard",
            decision="passed",
            message=f"APRS-IS Input Safety Rule passed | normalized_packet_hash={packet_hash[:16]}",
        )
        return {"decision": "continue"}

    def _execute_aprsis_rf_tx_guard(
        self,
        context: dict[str, Any],
        step: dict[str, Any],
    ) -> dict[str, str]:
        if str(context.get("source_kind") or "") != APRSIS_FLOW_SOURCE_KIND:
            return {"decision": "continue"}

        if not bool(context.get("aprsis_rf_guard_input_checked")):
            input_step = next(
                (
                    candidate
                    for candidate in list(context["flow"].get("steps") or [])[1:-1]
                    if str(candidate.get("step_type") or "") == RF_GUARD_STEP_TYPE
                ),
                None,
            )
            input_result = self._execute_aprsis_rf_input_guard(context, input_step)
            if input_result["decision"] != "continue":
                return input_result

        deny_result = self._aprsis_default_deny_result(context, step)
        if deny_result is not None:
            return deny_result

        try:
            guard_config = normalize_rf_guard_config(dict(step.get("config") or {}))
        except ValueError:
            guard_config = dict(RF_GUARD_DEFAULTS)
        context["aprsis_rf_guard_config"] = guard_config

        target_step = next(
            (
                candidate
                for candidate in reversed(list(context["flow"].get("steps") or []))
                if str(candidate.get("step_type") or "") == "tx_rf"
            ),
            None,
        )
        if target_step is None:
            return self._drop_aprsis_rf(
                context,
                step_id=_optional_int(step.get("id")),
                reason_code="invalid_target_type",
                stat_counter="dropped_safety_guard",
                event_type="rf_tx_guard",
            )
        return self._schedule_aprsis_rf_pending(context, step, target_step)

    def _execute_aprsis_message_delivery(
        self,
        context: dict[str, Any],
        step: dict[str, Any],
    ) -> dict[str, str]:
        if str(context.get("source_kind") or "") != APRSIS_FLOW_SOURCE_KIND:
            return {"decision": "continue"}
        flow = dict(context.get("flow") or {})
        flow_id = int(flow["id"])
        step_id = int(step["id"])
        result = evaluate_message_delivery(
            context.get("parsed"),
            flow_id=flow_id,
            local_igate=_local_station_identity(),
        )
        route = str(result.get("route") or "")
        reason = str(result.get("reason") or "message_policy_rejected")
        context["aprsis_message_delivery_result"] = dict(result)

        if route == "not_applicable":
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="message_delivery",
                decision="skipped",
                message=_t(
                    "APRS-IS Message Delivery Rule skipped: packet is not message traffic; "
                    "continuing to the callsign-and-radius rule."
                ),
            )
            return {"decision": "continue"}

        if route in {"message", "associated_position"}:
            context["aprsis_route_authorization"] = route
            context["aprsis_default_deny_filter_matched"] = True
            stat_counter = (
                "matched_message_rule"
                if route == "message"
                else "matched_associated_position"
            )
            record_aprsis_rf_stat(flow_id, stat_counter)
            if route == "message":
                message = (
                    "APRS-IS Message Delivery Rule passed "
                    f"| route=igate_message sender={result.get('sender') or '-'} "
                    f"recipient={result.get('recipient') or '-'} "
                    f"heard_interface={result.get('heard_interface') or '-'} "
                    f"heard_age={int(result.get('heard_age_seconds') or 0)}s "
                    f"consumed_hops={int(result.get('consumed_hops') or 0)}"
                )
            else:
                message = (
                    "APRS-IS Message Delivery Rule passed "
                    f"| route=associated_position sender={result.get('sender') or '-'}"
                )
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="message_delivery",
                decision="passed",
                message=message,
            )
            return {"decision": "continue"}

        stat_counter = {
            "message_recipient_seen_internet": "dropped_recipient_seen_internet",
            "message_sender_heard_local_rf": "dropped_sender_heard_rf",
        }.get(reason, "dropped_recipient_not_local")
        return self._drop_aprsis_rf(
            context,
            step_id=step_id,
            reason_code=reason,
            stat_counter=stat_counter,
            event_type="message_delivery",
        )

    def _execute_aprsis_allow_rules(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        if str(context.get("source_kind") or "") != APRSIS_FLOW_SOURCE_KIND:
            return {"decision": "continue"}
        flow_id = int(context["flow"]["id"])
        step_id = int(step["id"])
        route_authorization = str(context.get("aprsis_route_authorization") or "")
        if route_authorization in {"message", "associated_position"}:
            context["aprsis_default_deny_filter_matched"] = True
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="inclusive_allow_rules",
                decision="bypassed",
                message=(
                    "APRS-IS Callsign and Radius Rule bypassed because the mandatory "
                    f"message-delivery route already authorized this packet ({route_authorization})."
                ),
            )
            return {"decision": "continue"}
        try:
            config = normalize_default_deny_config(dict(step.get("config") or {}))
        except ValueError:
            config = normalize_default_deny_config({})
        matched = matches_default_deny_filter(
            context.get("parsed"),
            config,
            get_station_settings(),
        )
        if not matched:
            context["aprsis_default_deny_filter_matched"] = False
            return self._drop_aprsis_rf(
                context,
                step_id=step_id,
                reason_code="default_deny_filter_mismatch",
                stat_counter="dropped_no_allow_rule",
                event_type="inclusive_allow_rules",
            )
        context["aprsis_default_deny_filter_matched"] = True
        record_aprsis_rf_stat(flow_id, "matched_allow_rule")
        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=step_id,
            event_type="inclusive_allow_rules",
            decision="passed",
            message="APRS-IS Callsign and Radius Rule matched exact callsign AND radius from My Station.",
        )
        return {"decision": "continue"}

    def _aprsis_default_deny_result(
        self,
        context: dict[str, Any],
        step: dict[str, Any],
    ) -> dict[str, str] | None:
        if str(context.get("source_kind") or "") != APRSIS_FLOW_SOURCE_KIND:
            return None
        if str(context.get("aprsis_route_authorization") or "") in {
            "message",
            "associated_position",
        }:
            return None
        if bool(context.get("aprsis_default_deny_filter_matched")):
            return None
        return self._drop_aprsis_rf(
            context,
            step_id=_optional_int(step.get("id")),
            reason_code="default_deny_filter_mismatch",
            stat_counter="dropped_no_allow_rule",
            event_type="inclusive_allow_rules",
        )

    def _drop_aprsis_rf(
        self,
        context: dict[str, Any],
        *,
        step_id: int | None,
        reason_code: str,
        stat_counter: str,
        event_type: str = "rf_guard",
    ) -> dict[str, str]:
        flow_id = int(context["flow"]["id"])
        record_aprsis_rf_stat(flow_id, stat_counter)
        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=step_id,
            event_type=event_type,
            decision="rejected",
            message=f"DROP reason={reason_code}",
        )
        log_event(
            "DEBUG",
            "aprsis_rf",
            f"DROP reason={reason_code} flow_id={flow_id} line={str(context.get('raw_payload') or '')}",
        )
        return {"decision": "drop"}

    async def _execute_duplicate_filter(self, context: dict[str, Any], step: dict[str, Any], *, step_index: int) -> dict[str, str]:
        parsed = context.get("parsed")
        flow_id = int(context["flow"]["id"])
        step_id = int(step["id"])
        if parsed is None:
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="filter_dupe",
                decision="rejected",
                message=_t("Duplicate filter (viscous-delay) rejected frame because TNC2 parsing failed."),
            )
            return {"decision": "drop"}

        source_callsign = str(parsed.get("source") or "").strip().upper()
        payload = str(parsed.get("info") or "")
        if not source_callsign:
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="filter_dupe",
                decision="rejected",
                message=_t("Duplicate filter (viscous-delay) rejected frame because source callsign could not be parsed."),
            )
            return {"decision": "drop"}

        window_sec = self._duplicate_window_seconds(step)
        fingerprint_label = self._duplicate_fingerprint_label(source_callsign, payload)
        entry_key = (flow_id, step_id, source_callsign, payload)
        first_context_to_drop: dict[str, Any] | None = None
        created_entry = False
        now = time.monotonic()
        async with self._viscous_delay_lock:
            entry = self._viscous_delay_entries.get(entry_key)
            if entry is None:
                expires_at = now + float(window_sec)
                entry = _ViscousDelayEntry(
                    flow_id=flow_id,
                    step_id=step_id,
                    source_callsign=source_callsign,
                    payload=payload,
                    window_sec=window_sec,
                    expires_at=expires_at,
                    first_context=context,
                    first_next_step_index=step_index + 1,
                )
                entry.cleanup_task = asyncio.create_task(
                    self._finalize_viscous_delay_entry(entry_key, expires_at=expires_at),
                    name=f"aprsbox-viscous-delay-{flow_id}-{step_id}",
                )
                self._viscous_delay_entries[entry_key] = entry
                self._pending_viscous_wait_count += 1
                created_entry = True
            else:
                entry.duplicate_seen = True
                if entry.first_context is not None and not entry.first_finalized:
                    first_context_to_drop = entry.first_context
                    entry.first_context = None
                    entry.first_finalized = True
                    self._pending_viscous_wait_count = max(0, self._pending_viscous_wait_count - 1)

        if created_entry:
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="filter_dupe",
                decision="waiting",
                message=_tf(
                    "Duplicate filter (viscous-delay): fingerprint {fingerprint} created, waiting for duplicate window {window_sec}s.",
                    {"fingerprint": fingerprint_label, "window_sec": window_sec},
                ),
            )
            return {"decision": "defer"}

        duplicate_message = _tf(
            "Duplicate filter (viscous-delay): duplicate seen within {window_sec}s for fingerprint {fingerprint}; dropped.",
            {"window_sec": window_sec, "fingerprint": fingerprint_label},
        )
        if first_context_to_drop is not None:
            log_digi_flow_event(
                frame_uid=first_context_to_drop["frame_uid"],
                flow_id=int(first_context_to_drop["flow"]["id"]),
                step_id=step_id,
                event_type="filter_dupe",
                decision="rejected",
                message=duplicate_message,
            )
            self._log_pipeline_finished(first_context_to_drop, decision="drop")

        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=step_id,
            event_type="filter_dupe",
            decision="rejected",
            message=duplicate_message,
        )
        return {"decision": "drop"}

    async def _finalize_viscous_delay_entry(self, entry_key: tuple[int, int, str, str], *, expires_at: float) -> None:
        sleep_seconds = max(0.0, expires_at - time.monotonic())
        if sleep_seconds > 0:
            await asyncio.sleep(sleep_seconds)

        entry_to_resume: _ViscousDelayEntry | None = None
        resume_context: dict[str, Any] | None = None
        async with self._viscous_delay_lock:
            entry = self._viscous_delay_entries.pop(entry_key, None)
            if entry is None:
                return
            if entry.first_context is not None and not entry.first_finalized and not entry.duplicate_seen:
                entry_to_resume = entry
                resume_context = entry.first_context
                entry.first_context = None
                entry.first_finalized = True
                self._pending_viscous_wait_count = max(0, self._pending_viscous_wait_count - 1)

        if entry_to_resume is None:
            return
        if self._stop_event.is_set():
            return

        if resume_context is None:
            return
        log_digi_flow_event(
            frame_uid=resume_context["frame_uid"],
            flow_id=entry_to_resume.flow_id,
            step_id=entry_to_resume.step_id,
            event_type="filter_dupe",
            decision="passed",
            message=_tf(
                "Duplicate filter (viscous-delay): duplicate window expired after {window_sec}s for fingerprint {fingerprint}; frame allowed to continue.",
                {
                    "window_sec": entry_to_resume.window_sec,
                    "fingerprint": self._duplicate_fingerprint_label(entry_to_resume.source_callsign, entry_to_resume.payload),
                },
            ),
        )
        await self._execute_flow(resume_context, start_index=entry_to_resume.first_next_step_index)

    def _duplicate_window_seconds(self, step: dict[str, Any]) -> int:
        config = dict(step.get("config") or {})
        try:
            parsed = int(str(config.get("window_sec") or _DUPLICATE_FILTER_WINDOW_DEFAULT_SEC).strip())
        except ValueError:
            return _DUPLICATE_FILTER_WINDOW_DEFAULT_SEC
        if parsed not in _DUPLICATE_FILTER_WINDOW_ALLOWED:
            return _DUPLICATE_FILTER_WINDOW_DEFAULT_SEC
        return parsed

    def _duplicate_fingerprint_label(self, source_callsign: str, payload: str) -> str:
        return f"{source_callsign} | {payload}"

    def _log_pipeline_finished(self, context: dict[str, Any], *, decision: str) -> None:
        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=int(context["flow"]["id"]),
            step_id=None,
            event_type="pipeline_finished",
            decision=decision,
            message=f"Flow finished with decision {decision}.",
        )

    def _execute_callsign_filter(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        parsed = context.get("parsed") or {}
        callsign = str(parsed.get("source") or "").strip().upper()
        config = dict(step.get("config") or {})
        mode = str(config.get("mode") or "allow").strip().lower() or "allow"
        configured = [str(item).strip().upper() for item in config.get("callsigns") or [] if str(item).strip()]
        matched_pattern = _find_matching_callsign_pattern(callsign, configured) if callsign else None

        if not callsign:
            decision = "drop"
            message = _t("Callsign filter rejected frame because source callsign could not be parsed.")
        elif mode == "allow":
            passed = matched_pattern is not None
            decision = "continue" if passed else "drop"
            if configured:
                message = (
                    _tf(
                        "Callsign filter ({mode}) inspected {callsign}: passed because it matched pattern {pattern}.",
                        {"mode": mode, "callsign": callsign, "pattern": matched_pattern or ""},
                    )
                    if passed
                    else _tf(
                        "Callsign filter ({mode}) inspected {callsign}: rejected because it did not match any allow pattern.",
                        {"mode": mode, "callsign": callsign},
                    )
                )
            else:
                message = _tf(
                    "Callsign filter ({mode}) inspected {callsign}: rejected because the allow list is empty.",
                    {"mode": mode, "callsign": callsign},
                )
        else:
            blocked = matched_pattern is not None
            decision = "drop" if blocked else "continue"
            if configured:
                message = (
                    _tf(
                        "Callsign filter ({mode}) inspected {callsign}: rejected because it matched pattern {pattern}.",
                        {"mode": mode, "callsign": callsign, "pattern": matched_pattern or ""},
                    )
                    if blocked
                    else _tf(
                        "Callsign filter ({mode}) inspected {callsign}: passed because it did not match any deny pattern.",
                        {"mode": mode, "callsign": callsign},
                    )
                )
            else:
                message = _tf(
                    "Callsign filter ({mode}) inspected {callsign}: passed because the deny list is empty.",
                    {"mode": mode, "callsign": callsign},
                )

        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=int(context["flow"]["id"]),
            step_id=int(step["id"]),
            event_type="filter_callsign",
            decision="passed" if decision == "continue" else "rejected",
            message=message,
        )
        return {"decision": decision}

    def _execute_path_rule(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        parsed = context.get("parsed")
        flow_id = int(context["flow"]["id"])
        step_id = int(step["id"])
        if parsed is None:
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="path_rule",
                decision="rejected",
                message=_t("Path rule rejected frame because TNC2 parsing failed."),
            )
            return {"decision": "drop"}

        local_identities = _local_station_identities()
        aprs_data = dict(parsed.get("aprs_data") or {})
        packet_group = str(aprs_data.get("packet_group") or "").strip().casefold()
        addressee = _canonical_callsign_identity(aprs_data.get("addressee"))
        addressee_owner = local_identities.get(addressee) if addressee else None
        info_field = str(parsed.get("info") or "")

        if bool(parsed.get("is_third_party")) or info_field.startswith("}"):
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="path_rule",
                decision="rejected",
                message=_tf(
                    "RF Digipeating Path Rule rejected frame ({reason_code}) because APRS payload starts with third-party encapsulation marker {marker}.",
                    {"reason_code": DIGI_GUARD_THIRD_PARTY, "marker": "}"},
                ),
            )
            return {"decision": "drop"}

        source_identity = _canonical_callsign_identity(parsed.get("source"))
        source_owner = local_identities.get(source_identity) if source_identity else None
        if source_owner:
            if source_owner == _LOCAL_IDENTITY_WX:
                reason_code = DIGI_GUARD_LOCAL_SOURCE_WX
                identity_label = _t("WX station")
            else:
                reason_code = DIGI_GUARD_LOCAL_SOURCE_MY_STATION
                identity_label = _t("My station")
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="path_rule",
                decision="rejected",
                message=_tf(
                    "RF Digipeating Path Rule rejected frame ({reason_code}) because its source is local {identity_label} {local_identity}.",
                    {
                        "reason_code": reason_code,
                        "identity_label": identity_label,
                        "local_identity": source_identity,
                    },
                ),
            )
            return {"decision": "drop"}

        if packet_group == "message" and addressee_owner:
            if addressee_owner == _LOCAL_IDENTITY_WX:
                reason_code = DIGI_GUARD_LOCAL_MESSAGE_WX
                identity_label = _t("WX station")
            else:
                reason_code = DIGI_GUARD_LOCAL_MESSAGE_MY_STATION
                identity_label = _t("My station")
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="path_rule",
                decision="rejected",
                message=_tf(
                    "RF Digipeating Path Rule rejected frame ({reason_code}) because APRS message is addressed to local {identity_label} {local_identity}.",
                    {
                        "reason_code": reason_code,
                        "identity_label": identity_label,
                        "local_identity": addressee or "-",
                    },
                ),
            )
            return {"decision": "drop"}

        if packet_group == "query" and addressee_owner:
            if addressee_owner == _LOCAL_IDENTITY_WX:
                reason_code = DIGI_GUARD_LOCAL_QUERY_WX
                identity_label = _t("WX station")
            else:
                reason_code = DIGI_GUARD_LOCAL_QUERY_MY_STATION
                identity_label = _t("My station")
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="path_rule",
                decision="rejected",
                message=_tf(
                    "RF Digipeating Path Rule rejected frame ({reason_code}) because APRS query is addressed to local {identity_label} {local_identity}.",
                    {
                        "reason_code": reason_code,
                        "identity_label": identity_label,
                        "local_identity": addressee or "-",
                    },
                ),
            )
            return {"decision": "drop"}

        input_path = str(parsed.get("path") or "").strip().upper()
        path_tokens = _split_path_tokens(input_path)
        if not path_tokens:
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="path_rule",
                decision="rejected",
                message=_t("Path rule rejected frame because the packet has no remaining path."),
            )
            return {"decision": "drop"}

        first_unconsumed_index = next((index for index, token in enumerate(path_tokens) if not token.endswith("*")), None)
        if first_unconsumed_index is None:
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="path_rule",
                decision="rejected",
                message=_tf(
                    "Path rule rejected frame because the input path {path} is already fully consumed.",
                    {"path": input_path or "-"},
                ),
            )
            return {"decision": "drop"}

        local_identity = _local_station_identity()
        consumed_local = _find_consumed_local_identity(path_tokens, local_identities)
        if consumed_local is not None:
            consumed_identity = consumed_local[0]
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="path_rule",
                decision="rejected",
                message=_tf(
                    "RF Digipeating Path Rule rejected frame ({reason_code}) because local identity {local_identity} is already marked as consumed in path {path}.",
                    {
                        "reason_code": DIGI_GUARD_ALREADY_REPEATED_BY_LOCAL,
                        "local_identity": consumed_identity,
                        "path": input_path or "-",
                    },
                ),
            )
            return {"decision": "drop"}

        candidate = path_tokens[first_unconsumed_index]
        config = dict(step.get("config") or {})
        trace_specs = [str(item).strip().upper() for item in config.get("trace_paths") or [] if str(item).strip()]
        no_trace_specs = [str(item).strip().upper() for item in config.get("no_trace_paths") or [] if str(item).strip()]
        matched_trace = _find_matching_path_spec(candidate, trace_specs)
        matched_no_trace = _find_matching_path_spec(candidate, no_trace_specs)

        if matched_trace:
            if not local_identity:
                log_digi_flow_event(
                    frame_uid=context["frame_uid"],
                    flow_id=flow_id,
                    step_id=step_id,
                    event_type="path_rule",
                    decision="rejected",
                    message=_tf(
                        "Path rule matched TRACE {matched_trace} but local station callsign is not configured.",
                        {"matched_trace": matched_trace},
                    ),
                )
                return {"decision": "drop"}
            updated_tokens = _rewrite_trace_path(path_tokens, first_unconsumed_index, local_identity)
            updated_path = ",".join(updated_tokens)
            self._apply_updated_path(context, updated_path)
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="path_rule",
                decision="trace",
                message=_tf(
                    "TRACE matched {matched_trace}. Path {input_path} -> {updated_path}.",
                    {"matched_trace": matched_trace, "input_path": input_path or "-", "updated_path": updated_path or "-"},
                ),
            )
            return {"decision": "continue"}

        if matched_no_trace:
            updated_tokens = _rewrite_no_trace_path(path_tokens, first_unconsumed_index)
            updated_path = ",".join(updated_tokens)
            self._apply_updated_path(context, updated_path)
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="path_rule",
                decision="no_trace",
                message=_tf(
                    "NO_TRACE matched {matched_no_trace}. Path {input_path} -> {updated_path}.",
                    {"matched_no_trace": matched_no_trace, "input_path": input_path or "-", "updated_path": updated_path or "-"},
                ),
            )
            return {"decision": "continue"}

        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=step_id,
            event_type="path_rule",
            decision="rejected",
            message=_tf(
                "Path rule rejected frame because first remaining path {candidate} matched neither TRACE nor NO_TRACE. Input path: {input_path}",
                {"candidate": candidate, "input_path": input_path or "-"},
            ),
        )
        return {"decision": "drop"}

    def _execute_strict_filter(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        parsed = context.get("parsed")
        flow_id = int(context["flow"]["id"])
        step_id = int(step["id"])
        is_aprsis_target = str((context.get("flow") or {}).get("target_kind") or "").strip() == "tx_aprsis"
        if parsed is None:
            message = _t("Strict filter rejected frame because TNC2 parsing failed.")
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="strict_filter",
                decision="rejected",
                message=message,
            )
            if is_aprsis_target:
                record_aprsis_strict_reject(
                    reason_key=APRSIS_STRICT_REASON_OTHER,
                    frame_line=str(context.get("current_line") or ""),
                    reason_message=message,
                )
            return {"decision": "drop"}

        local_tx_reject = _local_tx_strict_reject_reason(context, parsed)
        if local_tx_reject is not None:
            message, reason_key = local_tx_reject
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="strict_filter",
                decision="rejected",
                message=message,
            )
            if is_aprsis_target:
                record_aprsis_strict_reject(
                    reason_key=reason_key,
                    frame_line=str(context.get("current_line") or ""),
                    reason_message=message,
                )
            return {"decision": "drop"}

        blocked = _find_blocked_strict_token(parsed)
        if blocked is None:
            input_path = str(parsed.get("path") or "").strip().upper()
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="strict_filter",
                decision="passed",
                message=_tf("Strict filter passed. Input path: {input_path}", {"input_path": input_path or "-"}),
            )
            return {"decision": "continue"}

        blocked_token = blocked["token"]
        blocked_scope = blocked["scope"]
        blocked_path = blocked["path"]
        if blocked_token == "THIRD_PARTY_INVALID":
            message = _t("Strict filter rejected frame because third-party encapsulation is malformed or invalid.")
        else:
            message = _tf(
                "Strict filter rejected frame because {scope} contains blocked token {blocked_token}. Input path: {input_path}",
                {"scope": blocked_scope, "blocked_token": blocked_token, "input_path": blocked_path or "-"},
            )
        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=step_id,
            event_type="strict_filter",
            decision="rejected",
            message=message,
        )
        if is_aprsis_target:
            record_aprsis_strict_reject(
                reason_key=_strict_reject_reason_key(blocked_token),
                frame_line=str(context.get("current_line") or ""),
                reason_message=message,
            )
        return {"decision": "drop"}

    def _execute_direct_only_filter(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        parsed = context.get("parsed")
        flow_id = int(context["flow"]["id"])
        step_id = int(step["id"])
        if parsed is None:
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="direct_only",
                decision="rejected",
                message=_t("Direct Only filter rejected frame because TNC2 parsing failed."),
            )
            return {"decision": "drop"}

        input_path = str(parsed.get("path") or "").strip().upper()
        consumed_hops = _consumed_path_hops(_split_path_tokens(input_path))
        if consumed_hops:
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="direct_only",
                decision="rejected",
                message=_tf(
                    "Direct Only filter rejected frame because the path already contains consumed digi hops: {hops}. Input path: {path}",
                    {"hops": ", ".join(consumed_hops), "path": input_path or "-"},
                ),
            )
            return {"decision": "drop"}

        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=step_id,
            event_type="direct_only",
            decision="passed",
            message=_tf(
                "Direct Only filter passed because the path has no consumed digi hops. Input path: {path}",
                {"path": input_path or "-"},
            ),
        )
        return {"decision": "continue"}

    def _execute_digi_filter(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        parsed = context.get("parsed")
        flow_id = int(context["flow"]["id"])
        step_id = int(step["id"])
        config = dict(step.get("config") or {})
        mode = str(config.get("mode") or "allow").strip().lower() or "allow"
        configured = [str(item).strip().upper() for item in config.get("digis") or [] if str(item).strip()]

        if parsed is None:
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="filter_digi",
                decision="rejected",
                message=_t("DIGI filter rejected frame because TNC2 parsing failed."),
            )
            return {"decision": "drop"}

        input_path = str(parsed.get("path") or "").strip().upper()
        consumed_hops = _consumed_path_hops(_split_path_tokens(input_path))
        matched_pattern, matched_hop = _find_matching_digi_pattern(consumed_hops, configured)

        if mode == "allow":
            passed = matched_pattern is not None
            decision = "continue" if passed else "drop"
            if configured:
                message = (
                    _tf(
                        "DIGI filter ({mode}) inspected consumed hops {hops}: passed because it matched pattern {pattern} on hop {hop}.",
                        {"mode": mode, "hops": ", ".join(consumed_hops) or "-", "pattern": matched_pattern or "", "hop": matched_hop or "-"},
                    )
                    if passed
                    else _tf(
                        "DIGI filter ({mode}) inspected consumed hops {hops}: rejected because it did not match any allow pattern.",
                        {"mode": mode, "hops": ", ".join(consumed_hops) or "-"},
                    )
                )
            else:
                message = _t("DIGI filter (allow) rejected frame because the allow list is empty.")
        else:
            blocked = matched_pattern is not None
            decision = "drop" if blocked else "continue"
            if configured:
                message = (
                    _tf(
                        "DIGI filter ({mode}) inspected consumed hops {hops}: rejected because it matched pattern {pattern} on hop {hop}.",
                        {"mode": mode, "hops": ", ".join(consumed_hops) or "-", "pattern": matched_pattern or "", "hop": matched_hop or "-"},
                    )
                    if blocked
                    else _tf(
                        "DIGI filter ({mode}) inspected consumed hops {hops}: passed because it did not match any deny pattern.",
                        {"mode": mode, "hops": ", ".join(consumed_hops) or "-"},
                    )
                )
            else:
                message = _t("DIGI filter (deny) passed because the deny list is empty.")

        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=step_id,
            event_type="filter_digi",
            decision="passed" if decision == "continue" else "rejected",
            message=message,
        )
        return {"decision": decision}

    def _execute_packet_type_filter(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        parsed = context.get("parsed")
        flow_id = int(context["flow"]["id"])
        step_id = int(step["id"])
        config = dict(step.get("config") or {})
        mode = str(config.get("mode") or "allow").strip().lower() or "allow"
        configured = [str(item).strip() for item in config.get("packet_types") or [] if str(item).strip()]
        matched_selector = _find_matching_packet_type_selector(parsed, configured)
        packet_group = _parsed_aprs_packet_group(parsed)
        packet_type_code = _parsed_aprs_packet_type_code(parsed)

        if not packet_group and not packet_type_code:
            decision = "drop" if mode == "allow" else "continue"
            message = (
                _t("Packet type filter rejected frame because APRS packet group could not be decoded.")
                if decision == "drop"
                else _t("Packet type filter passed because APRS packet group could not be decoded and deny list applies only to decoded groups.")
            )
        elif mode == "allow":
            matched = matched_selector is not None
            decision = "continue" if matched else "drop"
            inspected = _packet_type_filter_inspected_label(packet_group=packet_group, packet_type_code=packet_type_code)
            if configured:
                message = (
                    _tf(
                        "Packet type filter ({mode}) inspected {inspected}: passed because it matched configured group {matched_selector}.",
                        {"mode": mode, "inspected": inspected, "matched_selector": str(matched_selector or "")},
                    )
                    if matched
                    else _tf(
                        "Packet type filter ({mode}) inspected {inspected}: rejected because it did not match any allow group.",
                        {"mode": mode, "inspected": inspected},
                    )
                )
            else:
                message = _tf(
                    "Packet type filter ({mode}) inspected {inspected}: rejected because the allow list is empty.",
                    {"mode": mode, "inspected": inspected},
                )
        else:
            blocked = matched_selector is not None
            decision = "drop" if blocked else "continue"
            inspected = _packet_type_filter_inspected_label(packet_group=packet_group, packet_type_code=packet_type_code)
            if configured:
                message = (
                    _tf(
                        "Packet type filter ({mode}) inspected {inspected}: rejected because it matched configured group {matched_selector}.",
                        {"mode": mode, "inspected": inspected, "matched_selector": str(matched_selector or "")},
                    )
                    if blocked
                    else _tf(
                        "Packet type filter ({mode}) inspected {inspected}: passed because it did not match any deny group.",
                        {"mode": mode, "inspected": inspected},
                    )
                )
            else:
                message = _tf(
                    "Packet type filter ({mode}) inspected {inspected}: passed because the deny list is empty.",
                    {"mode": mode, "inspected": inspected},
                )

        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=step_id,
            event_type="filter_packet_type",
            decision="passed" if decision == "continue" else "rejected",
            message=message,
        )
        return {"decision": decision}

    def _execute_icon_filter(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        parsed = context.get("parsed")
        flow_id = int(context["flow"]["id"])
        step_id = int(step["id"])
        config = dict(step.get("config") or {})
        mode = str(config.get("mode") or "allow").strip().lower() or "allow"
        configured = [str(item).strip().upper() for item in config.get("icons") or [] if str(item).strip()]
        symbol = _parsed_aprs_symbol(parsed)

        if not symbol:
            decision = "drop" if mode == "allow" else "continue"
            message = (
                _t("Icon filter rejected frame because APRS symbol could not be decoded.")
                if decision == "drop"
                else _t("Icon filter passed because APRS symbol could not be decoded and deny list applies only to decoded symbols.")
            )
        elif mode == "allow":
            matched = symbol in configured
            decision = "continue" if matched else "drop"
            if configured:
                message = (
                    _tf(
                        "Icon filter ({mode}) inspected {symbol}: passed because it matched configured symbol {matched_symbol}.",
                        {"mode": mode, "symbol": symbol, "matched_symbol": symbol},
                    )
                    if matched
                    else _tf(
                        "Icon filter ({mode}) inspected {symbol}: rejected because it did not match any allow symbol.",
                        {"mode": mode, "symbol": symbol},
                    )
                )
            else:
                message = _tf(
                    "Icon filter ({mode}) inspected {symbol}: rejected because the allow list is empty.",
                    {"mode": mode, "symbol": symbol},
                )
        else:
            blocked = symbol in configured
            decision = "drop" if blocked else "continue"
            if configured:
                message = (
                    _tf(
                        "Icon filter ({mode}) inspected {symbol}: rejected because it matched configured symbol {matched_symbol}.",
                        {"mode": mode, "symbol": symbol, "matched_symbol": symbol},
                    )
                    if blocked
                    else _tf(
                        "Icon filter ({mode}) inspected {symbol}: passed because it did not match any deny symbol.",
                        {"mode": mode, "symbol": symbol},
                    )
                )
            else:
                message = _tf(
                    "Icon filter ({mode}) inspected {symbol}: passed because the deny list is empty.",
                    {"mode": mode, "symbol": symbol},
                )

        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=step_id,
            event_type="filter_icon",
            decision="passed" if decision == "continue" else "rejected",
            message=message,
        )
        return {"decision": decision}

    def _execute_distance_filter(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        flow_id = int(context["flow"]["id"])
        step_id = int(step["id"])
        config = dict(step.get("config") or {})
        zones = _distance_filter_zones(config)
        if not zones:
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="filter_distance",
                decision="skipped",
                message=_t("distance_filter: no zones configured, skipped"),
            )
            return {"decision": "continue"}

        position = _parsed_aprs_position(context.get("parsed"))
        if position is None:
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="filter_distance",
                decision="skipped",
                message=_t("distance_filter: no position, skipped"),
            )
            return {"decision": "continue"}

        latitude, longitude = position
        for zone_index, zone in enumerate(zones, start=1):
            distance_km = _distance_km_between_points(
                latitude,
                longitude,
                float(zone["latitude"]),
                float(zone["longitude"]),
            )
            if distance_km <= float(zone["radius_km"]):
                log_digi_flow_event(
                    frame_uid=context["frame_uid"],
                    flow_id=flow_id,
                    step_id=step_id,
                    event_type="filter_distance",
                    decision="passed",
                    message=_tf(
                        "distance_filter: matched zone #{zone_index}, distance {distance_km} km <= {radius_km} km",
                        {
                            "zone_index": zone_index,
                            "distance_km": _format_distance_km(distance_km),
                            "radius_km": _format_distance_km(float(zone["radius_km"])),
                        },
                    ),
                )
                return {"decision": "continue"}

        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=step_id,
            event_type="filter_distance",
            decision="rejected",
            message=_t("distance_filter: outside all zones, dropped"),
        )
        return {"decision": "drop"}

    def _execute_rate_limit_filter(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        flow_id = int(context["flow"]["id"])
        step_id = int(step["id"])
        config = dict(step.get("config") or {})
        source_callsign = str((context.get("parsed") or {}).get("source") or "").strip().upper()
        rules = _rate_limit_rules_from_config(config)
        matched_rule = _find_rate_limit_rule(source_callsign, rules)
        if matched_rule is None:
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="filter_rate_limit",
                decision="passed",
                message=_tf(
                    "Transmission Rate Filter skipped frame because source callsign {callsign} did not match any configured rule.",
                    {"callsign": source_callsign or "-"},
                ),
            )
            return {"decision": "continue"}

        rate_limit_seconds = int(matched_rule["rate_limit_seconds"])
        matched_pattern = str(matched_rule["source_callsign_pattern"])
        now = time.monotonic()
        timer_scope = "*" if matched_pattern == "*" else source_callsign
        state_key = (flow_id, step_id, matched_pattern, timer_scope)
        last_passed = self._rate_limit_last_passed.get(state_key)
        if last_passed is not None:
            elapsed_seconds = now - last_passed
            if elapsed_seconds <= rate_limit_seconds:
                log_digi_flow_event(
                    frame_uid=context["frame_uid"],
                    flow_id=flow_id,
                    step_id=step_id,
                    event_type="filter_rate_limit",
                    decision="rejected",
                    message=_tf(
                        "Transmission Rate Filter blocked frame for source callsign {callsign} with pattern {pattern} because only {elapsed_seconds}s elapsed since the last passed frame; limit is {rate_limit_seconds}s.",
                        {
                            "callsign": source_callsign or "-",
                            "pattern": matched_pattern,
                            "elapsed_seconds": f"{elapsed_seconds:.1f}".rstrip("0").rstrip("."),
                            "rate_limit_seconds": rate_limit_seconds,
                        },
                    ),
                )
                return {"decision": "drop"}

            self._rate_limit_last_passed[state_key] = now
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="filter_rate_limit",
                decision="passed",
                message=_tf(
                    "Transmission Rate Filter passed for source callsign {callsign} with pattern {pattern} after {elapsed_seconds}s since the last passed frame; limit is {rate_limit_seconds}s.",
                    {
                        "callsign": source_callsign or "-",
                        "pattern": matched_pattern,
                        "elapsed_seconds": f"{elapsed_seconds:.1f}".rstrip("0").rstrip("."),
                        "rate_limit_seconds": rate_limit_seconds,
                    },
                ),
            )
            return {"decision": "continue"}

        self._rate_limit_last_passed[state_key] = now
        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=step_id,
            event_type="filter_rate_limit",
            decision="passed",
            message=_tf(
                "Transmission Rate Filter passed for source callsign {callsign} with pattern {pattern} because no previous frame has been allowed yet; limit is {rate_limit_seconds}s.",
                {
                    "callsign": source_callsign or "-",
                    "pattern": matched_pattern,
                    "rate_limit_seconds": rate_limit_seconds,
                },
            ),
        )
        return {"decision": "continue"}

    def _execute_log_only(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        config = dict(step.get("config") or {})
        tag = str(config.get("log_tag") or "").strip()
        note = str(config.get("note") or "").strip()
        message_parts = [part for part in (f"tag={tag}" if tag else "", note, f"line={context['current_line']}") if part]
        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=int(context["flow"]["id"]),
            step_id=int(step["id"]),
            event_type="output_action",
            decision="log_only",
            message="LOG_ONLY " + " | ".join(message_parts),
        )
        return {"decision": "log_only"}

    def _execute_drop(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        config = dict(step.get("config") or {})
        note = str(config.get("note") or "").strip()
        message = f"DROP {note}" if note else "DROP packet."
        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=int(context["flow"]["id"]),
            step_id=int(step["id"]),
            event_type="output_action",
            decision="drop",
            message=message,
        )
        return {"decision": "drop"}

    async def _execute_tx_rf(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        if str(context.get("source_kind") or "") == APRSIS_FLOW_SOURCE_KIND:
            input_result = self._execute_aprsis_rf_input_guard(context, None)
            if input_result["decision"] != "continue":
                return input_result
            deny_result = self._aprsis_default_deny_result(context, step)
            if deny_result is not None:
                return deny_result
            return self._schedule_aprsis_rf_pending(context, None, step)
        config = dict(step.get("config") or {})
        target = str(config.get("rf_target") or "").strip()
        success, detail = enqueue_digi_tx_job(
            interface_name=target,
            line=str(context["current_line"]),
            flow_id=int(context["flow"]["id"]),
            frame_uid=str(context["frame_uid"]),
        )
        decision = "tx" if success else "drop"
        message = (
            f"Queued DIGI TX for target RF:{target or '-'}."
            if success
            else f"Failed to queue DIGI TX for target RF:{target or '-'}."
        )
        if detail:
            message = f"{message} {detail}"
        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=int(context["flow"]["id"]),
            step_id=int(step["id"]),
            event_type="output_action",
            decision=decision,
            message=f"{message} | line={context['current_line']}",
        )
        return {"decision": decision}

    def _schedule_aprsis_rf_pending(
        self,
        context: dict[str, Any],
        guard_step: dict[str, Any] | None,
        target_step: dict[str, Any],
    ) -> dict[str, str]:
        flow_id = int(context["flow"]["id"])
        guard_step_id = _optional_int((guard_step or {}).get("id"))
        target_step_id = int(target_step["id"])
        packet_hash = str(context.get("normalized_packet_hash") or "").strip()
        if not packet_hash:
            return self._drop_aprsis_rf(
                context,
                step_id=guard_step_id,
                reason_code="invalid_aprs",
                stat_counter="dropped_safety_guard",
                event_type="rf_tx_guard",
            )
        target = str(dict(target_step.get("config") or {}).get("rf_target") or "").strip()
        _target_row, target_reason = validate_aprsis_rf_target(target, require_active=True)
        if target_reason:
            return self._drop_aprsis_rf(
                context,
                step_id=guard_step_id,
                reason_code=target_reason,
                stat_counter="dropped_safety_guard",
                event_type="rf_tx_guard",
            )
        pending_key = (flow_id, packet_hash)
        if any(pending_hash == packet_hash for _pending_flow_id, pending_hash in self._aprsis_rf_pending):
            return self._drop_aprsis_rf(
                context,
                step_id=guard_step_id,
                reason_code="already_pending",
                stat_counter="dropped_duplicate",
                event_type="rf_tx_guard",
            )
        if len(self._aprsis_rf_pending) >= 256 or sum(1 for key in self._aprsis_rf_pending if key[0] == flow_id) >= 64:
            return self._drop_aprsis_rf(
                context,
                step_id=guard_step_id,
                reason_code="rate_limit_flow",
                stat_counter="dropped_rate_limit",
                event_type="rf_tx_guard",
            )

        guard_config = dict(context.get("aprsis_rf_guard_config") or RF_GUARD_DEFAULTS)
        delay_sec = float(guard_config.get("viscous_delay_sec") or RF_GUARD_DEFAULTS["viscous_delay_sec"])
        if self._aprsis_rf_delay_override is not None:
            delay_sec = max(0.0, float(self._aprsis_rf_delay_override))
        parsed = dict(context.get("original_parsed") or context.get("parsed") or {})
        source_callsign = str(parsed.get("source") or "").strip().upper()
        entry = _AprsisRfPendingEntry(
            flow_id=flow_id,
            guard_step_id=guard_step_id,
            target_step_id=target_step_id,
            packet_hash=packet_hash,
            source_callsign=source_callsign,
            context=context,
            created_at=time.monotonic(),
            delay_sec=delay_sec,
            cancel_event=asyncio.Event(),
        )
        entry.cleanup_task = asyncio.create_task(
            self._finalize_aprsis_rf_pending(pending_key, entry),
            name=f"aprsbox-aprsis-rf-{flow_id}-{packet_hash[:10]}",
        )
        self._aprsis_rf_pending[pending_key] = entry
        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=guard_step_id,
            event_type="rf_tx_guard",
            decision="waiting",
            message=f"APRS-IS to RF TX Safety Rule pending viscous delay {delay_sec:g}s | normalized_packet_hash={packet_hash[:16]}",
        )
        return {"decision": "defer"}

    async def _finalize_aprsis_rf_pending(
        self,
        pending_key: tuple[int, str],
        entry: _AprsisRfPendingEntry,
    ) -> None:
        try:
            try:
                await asyncio.wait_for(entry.cancel_event.wait(), timeout=entry.delay_sec)
                cancelled = True
            except TimeoutError:
                cancelled = False
            if self._stop_event.is_set():
                return
            if cancelled:
                self._finish_aprsis_rf_pending_drop(
                    entry,
                    reason_code="viscous_cancelled",
                    stat_counter="cancelled_during_viscous_delay",
                )
                return

            flow = get_digi_flow(entry.flow_id)
            if flow is None:
                log_event("DEBUG", "aprsis_rf", f"DROP reason=flow_disabled flow_id={entry.flow_id} (flow removed)")
                return
            if int(flow.get("enabled") or 0) != 1:
                self._finish_aprsis_rf_pending_drop(entry, reason_code="flow_disabled", stat_counter="dropped_safety_guard")
                return
            if str(flow.get("source_kind") or "") != APRSIS_FLOW_SOURCE_KIND or str(flow.get("target_kind") or "") != "tx_rf":
                self._finish_aprsis_rf_pending_drop(entry, reason_code="invalid_target_type", stat_counter="dropped_safety_guard")
                return

            target_step = next(
                (step for step in reversed(list(flow.get("steps") or [])) if str(step.get("step_type") or "") == "tx_rf"),
                None,
            )
            if target_step is None:
                self._finish_aprsis_rf_pending_drop(entry, reason_code="invalid_target_type", stat_counter="dropped_safety_guard")
                return
            target_config = dict(target_step.get("config") or {})
            target_name = str(target_config.get("rf_target") or flow.get("target_ref") or "").strip()
            target_row, target_reason = validate_aprsis_rf_target(target_name, require_active=True)
            if target_reason or target_row is None:
                self._finish_aprsis_rf_pending_drop(
                    entry,
                    reason_code=target_reason or "target_unavailable",
                    stat_counter="dropped_safety_guard",
                )
                return

            guard_step = next(
                (
                    step
                    for step in list(flow.get("steps") or [])[1:-1]
                    if str(step.get("step_type") or "") == RF_TX_GUARD_STEP_TYPE
                ),
                None,
            )
            entry.guard_step_id = _optional_int((guard_step or {}).get("id"))
            try:
                guard_config = normalize_rf_guard_config((guard_step or {}).get("config") or RF_GUARD_DEFAULTS)
            except ValueError:
                guard_config = dict(RF_GUARD_DEFAULTS)

            final_guard_reason = aprsis_rf_guard_reject_reason(
                dict(entry.context.get("original_parsed") or entry.context.get("parsed") or {})
            )
            if final_guard_reason:
                self._finish_aprsis_rf_pending_drop(
                    entry,
                    reason_code=final_guard_reason,
                    stat_counter="dropped_safety_guard",
                )
                return

            now = time.monotonic()
            self._prune_aprsis_rf_state(now)
            seen = self._aprsis_rf_seen.setdefault(entry.packet_hash, _AprsisRfSeenEntry())
            duplicate_window = float(guard_config["duplicate_window_sec"])
            if seen.rf_seen_at is not None and seen.rf_seen_at >= entry.created_at and now - seen.rf_seen_at <= duplicate_window:
                self._finish_aprsis_rf_pending_drop(entry, reason_code="duplicate_rf_seen", stat_counter="dropped_duplicate")
                return
            if seen.queued_at is not None and now - seen.queued_at <= duplicate_window:
                self._finish_aprsis_rf_pending_drop(entry, reason_code="duplicate_is_seen", stat_counter="dropped_duplicate")
                return

            limit_reason = self._consume_aprsis_rf_rate_limit(
                flow_id=entry.flow_id,
                source_callsign=entry.source_callsign,
                recipient_callsign=str(
                    dict(entry.context.get("aprsis_message_delivery_result") or {}).get("recipient")
                    or ""
                ),
                route_class=str(entry.context.get("aprsis_route_authorization") or "allow_rule"),
                config=guard_config,
                now=now,
            )
            if limit_reason:
                self._finish_aprsis_rf_pending_drop(entry, reason_code=limit_reason, stat_counter="dropped_rate_limit")
                return

            local_igate = _local_station_identity()
            if not local_igate:
                self._finish_aprsis_rf_pending_drop(entry, reason_code="invalid_aprs", stat_counter="dropped_safety_guard")
                return
            try:
                tx_line = build_aprsis_third_party_tnc2(
                    dict(entry.context.get("original_parsed") or entry.context.get("parsed") or {}),
                    igate_callsign=local_igate,
                    rf_path=str(target_config.get("rf_path") or ""),
                )
            except ValueError as exc:
                reason = str(exc).strip() or "invalid_aprs"
                if reason == "packet_too_long":
                    self._finish_aprsis_rf_pending_drop(entry, reason_code=reason, stat_counter="dropped_oversize")
                else:
                    self._finish_aprsis_rf_pending_drop(entry, reason_code=reason, stat_counter="dropped_safety_guard")
                return

            log_digi_flow_event(
                frame_uid=entry.context["frame_uid"],
                flow_id=entry.flow_id,
                step_id=entry.guard_step_id,
                event_type="rf_tx_guard",
                decision="passed",
                message=(
                    "APRS-IS to RF TX Safety Rule passed final duplicate, rate, target, encapsulation and packet-size checks "
                    f"| normalized_packet_hash={entry.packet_hash[:16]}"
                ),
            )
            metadata = dict(entry.context.get("metadata") or {})
            success, detail = enqueue_digi_tx_job(
                interface_name=target_name,
                line=tx_line,
                trigger=APRSIS_TO_RF_ORIGIN,
                flow_id=entry.flow_id,
                frame_uid=str(entry.context.get("frame_uid") or ""),
                metadata={
                    "origin": APRSIS_TO_RF_ORIGIN,
                    "aprsis_interface_id": metadata.get("aprsis_interface_id"),
                    "target_interface_id": int(target_row["id"]),
                    "normalized_packet_hash": entry.packet_hash,
                },
            )
            if not success:
                reason = str(detail or "target_unavailable")
                record_aprsis_rf_stat(entry.flow_id, "tx_failed")
                log_digi_flow_event(
                    frame_uid=entry.context["frame_uid"],
                    flow_id=entry.flow_id,
                    step_id=entry.target_step_id,
                    event_type="output_action",
                    decision="drop",
                    message=f"Failed to queue APRS-IS to RF. reason={reason}",
                )
                log_event(
                    "DEBUG",
                    "aprsis_rf",
                    f"DROP reason={reason} flow_id={entry.flow_id} line={str(entry.context.get('raw_payload') or '')}",
                )
                self._log_pipeline_finished(entry.context, decision="drop")
                return
            seen.queued_at = now
            self._aprsis_rf_seen.move_to_end(entry.packet_hash)
            record_aprsis_rf_stat(entry.flow_id, "queued_to_rf")
            entry.context["current_line"] = tx_line
            route_authorization = str(entry.context.get("aprsis_route_authorization") or "")
            delivery_result = dict(entry.context.get("aprsis_message_delivery_result") or {})
            if route_authorization == "message":
                mark_pending_sender_position(
                    flow_id=entry.flow_id,
                    sender_key=str(delivery_result.get("sender") or entry.source_callsign),
                )
            elif route_authorization == "associated_position":
                clear_pending_sender_position(
                    flow_id=entry.flow_id,
                    sender_key=str(delivery_result.get("sender") or entry.source_callsign),
                )
            log_digi_flow_event(
                frame_uid=entry.context["frame_uid"],
                flow_id=entry.flow_id,
                step_id=entry.target_step_id,
                event_type="output_action",
                decision="tx",
                message=f"Queued APRS-IS to RF through existing outbound queue. {detail} | line={tx_line}",
            )
            self._log_pipeline_finished(entry.context, decision="tx")
        finally:
            self._aprsis_rf_pending.pop(pending_key, None)

    def _finish_aprsis_rf_pending_drop(
        self,
        entry: _AprsisRfPendingEntry,
        *,
        reason_code: str,
        stat_counter: str,
    ) -> None:
        self._drop_aprsis_rf(
            entry.context,
            step_id=entry.guard_step_id,
            reason_code=reason_code,
            stat_counter=stat_counter,
            event_type="rf_tx_guard",
        )
        self._log_pipeline_finished(entry.context, decision="drop")

    def _consume_aprsis_rf_rate_limit(
        self,
        *,
        flow_id: int,
        source_callsign: str,
        recipient_callsign: str,
        route_class: str,
        config: dict[str, int],
        now: float,
    ) -> str | None:
        flow_rate = float(config["flow_rate_per_minute"])
        flow_burst = float(config["flow_burst"])
        source_rate = float(config["source_rate_per_minute"])
        source_burst = float(config["source_burst"])
        normalized_route = (
            "message"
            if route_class in {"message", "associated_position"}
            else "allow_rule"
        )
        flow_bucket = self._refill_token_bucket(
            self._aprsis_rf_flow_buckets,
            (flow_id, normalized_route),
            rate_per_minute=flow_rate,
            burst=flow_burst,
            now=now,
        )
        source_key = (flow_id, normalized_route, source_callsign)
        source_bucket = self._refill_token_bucket(
            self._aprsis_rf_source_buckets,
            source_key,
            rate_per_minute=source_rate,
            burst=source_burst,
            now=now,
        )
        if flow_bucket.tokens < 1.0:
            return "rate_limit_flow"
        if source_bucket.tokens < 1.0:
            return "rate_limit_source"
        recipient_bucket: _TokenBucket | None = None
        if normalized_route == "message" and recipient_callsign:
            recipient_bucket = self._refill_token_bucket(
                self._aprsis_rf_recipient_buckets,
                (flow_id, normalized_route, recipient_callsign),
                rate_per_minute=source_rate,
                burst=source_burst,
                now=now,
            )
            if recipient_bucket.tokens < 1.0:
                return "rate_limit_recipient"
        flow_bucket.tokens -= 1.0
        source_bucket.tokens -= 1.0
        if recipient_bucket is not None:
            recipient_bucket.tokens -= 1.0
        return None

    @staticmethod
    def _refill_token_bucket(
        buckets: dict[Any, _TokenBucket],
        key: Any,
        *,
        rate_per_minute: float,
        burst: float,
        now: float,
    ) -> _TokenBucket:
        bucket = buckets.get(key)
        if bucket is None:
            bucket = _TokenBucket(tokens=burst, updated_at=now)
            buckets[key] = bucket
            return bucket
        elapsed = max(0.0, now - bucket.updated_at)
        bucket.tokens = min(burst, bucket.tokens + elapsed * (rate_per_minute / 60.0))
        bucket.updated_at = now
        return bucket

    def _prune_aprsis_rf_state(self, now: float) -> None:
        for packet_hash, entry in list(self._aprsis_rf_seen.items()):
            timestamps = [value for value in (entry.is_seen_at, entry.rf_seen_at, entry.queued_at) if value is not None]
            if not timestamps or now - max(timestamps) > 300.0:
                self._aprsis_rf_seen.pop(packet_hash, None)
        while len(self._aprsis_rf_seen) > 4096:
            self._aprsis_rf_seen.popitem(last=False)
        if len(self._aprsis_rf_source_buckets) > 4096:
            oldest = sorted(self._aprsis_rf_source_buckets.items(), key=lambda item: item[1].updated_at)
            for key, _bucket in oldest[: len(oldest) - 4096]:
                self._aprsis_rf_source_buckets.pop(key, None)
        if len(self._aprsis_rf_recipient_buckets) > 4096:
            oldest = sorted(self._aprsis_rf_recipient_buckets.items(), key=lambda item: item[1].updated_at)
            for key, _bucket in oldest[: len(oldest) - 4096]:
                self._aprsis_rf_recipient_buckets.pop(key, None)

    async def _execute_tx_aprsis(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        flow_id = int(context["flow"]["id"])
        step_id = int(step["id"])
        now_monotonic = time.monotonic()
        frame_age_ms = _monotonic_delta_ms(
            context.get("rx_received_monotonic")
            if isinstance(context.get("rx_received_monotonic"), (int, float))
            else context.get("enqueue_monotonic"),
            now_monotonic,
        )
        max_frame_age_ms = self._aprsis_tx_max_frame_age_seconds * 1000.0
        if frame_age_ms is None or frame_age_ms > max_frame_age_ms:
            age_label = "unknown" if frame_age_ms is None else f"{frame_age_ms:.0f} ms"
            message = _t(
                "APRS-IS TX dropped stale frame before transport write "
                f"(age={age_label}, limit={max_frame_age_ms:.0f} ms)."
            )
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="output_action",
                decision="drop",
                message=message,
            )
            record_aprsis_tx_result(sent=False, frame_line=str(context.get("current_line") or ""))
            return {"decision": "drop"}
        parsed = context.get("parsed")
        if parsed is None:
            message = _t("APRS-IS TX rejected frame because TNC2 parsing failed.")
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="output_action",
                decision="drop",
                message=message,
            )
            record_aprsis_tx_result(sent=False, frame_line=str(context.get("current_line") or ""))
            return {"decision": "drop"}

        local_igate = _local_station_identity()
        if not local_igate:
            message = _t("APRS-IS TX rejected frame because local station identity is not configured.")
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="output_action",
                decision="drop",
                message=message,
            )
            record_aprsis_tx_result(sent=False, frame_line=str(context.get("current_line") or ""))
            return {"decision": "drop"}

        source_kind = str(context.get("source_kind") or "")
        q_construct = ""
        q_reason = "client_originated"
        if source_kind == LOCAL_TX_SOURCE_KIND:
            tx_line = _build_aprsis_uplink_line(
                parsed,
                local_igate=local_igate,
                client_originated=True,
            )
        else:
            consumed_hops = len(
                _consumed_path_hops(_split_path_tokens(str(parsed.get("path") or "")))
            )
            if bool(parsed.get("is_third_party")):
                return_capable = False
                q_reason = "third_party_or_translated_source"
            else:
                return_capable, q_reason = message_return_capable_for_rf_source(
                    str(context.get("source_ref") or ""),
                    consumed_hops=consumed_hops,
                )
            q_construct = "qAR" if return_capable else "qAO"
            tx_line = _build_aprsis_uplink_line(
                parsed,
                local_igate=local_igate,
                q_construct=q_construct,
            )
        if not tx_line:
            message = _t("APRS-IS TX rejected frame because APRS-IS uplink formatting failed.")
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="output_action",
                decision="drop",
                message=message,
            )
            record_aprsis_tx_result(sent=False, frame_line=str(context.get("current_line") or ""))
            return {"decision": "drop"}

        if self._aprsis_client is None:
            message = _t("APRS-IS TX rejected frame because APRS-IS uplink runtime is unavailable.")
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=flow_id,
                step_id=step_id,
                event_type="output_action",
                decision="drop",
                message=message,
            )
            record_aprsis_tx_result(sent=False, frame_line=str(context.get("current_line") or ""))
            return {"decision": "drop"}

        rx_to_igate_enqueue_ms = _monotonic_delta_ms(
            context.get("rx_received_monotonic"),
            context.get("enqueue_monotonic"),
        )
        igate_queue_wait_ms = _monotonic_delta_ms(
            context.get("enqueue_monotonic"),
            now_monotonic,
        )
        tx_telemetry = {
            "frame_uid": str(context.get("frame_uid") or ""),
            "rx_received_monotonic": context.get("rx_received_monotonic"),
            "enqueue_monotonic": context.get("enqueue_monotonic"),
            "rx_to_igate_enqueue_ms": rx_to_igate_enqueue_ms,
            "igate_queue_wait_ms": igate_queue_wait_ms,
        }
        if isinstance(self._aprsis_client, AprsisClientService):
            success, detail = await self._aprsis_client.send_tnc2_line(tx_line, telemetry=tx_telemetry)
        else:
            success, detail = await self._aprsis_client.send_tnc2_line(tx_line)
        decision = "tx" if success else "drop"
        message = detail or ("APRS-IS TX sent." if success else "APRS-IS TX dropped.")
        uplink_identity = (
            "TCPIP* client-originated"
            if source_kind == LOCAL_TX_SOURCE_KIND
            else f"{q_construct} ({q_reason})"
        )
        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=step_id,
            event_type="output_action",
            decision=decision,
            message=f"{message} | uplink={uplink_identity} | line={tx_line}",
        )
        if success and source_kind == LOCAL_TX_SOURCE_KIND:
            persist_outbound_frame(
                source="APRS-IS",
                line=tx_line,
                source_kind=APRSIS_SOURCE_KIND,
            )
        record_aprsis_tx_result(sent=success, frame_line=tx_line)
        return {"decision": decision}

    def _execute_tx_stub(self, context: dict[str, Any], step: dict[str, Any], *, target_label: str) -> dict[str, str]:
        config = dict(step.get("config") or {})
        if str(step["step_type"]) == "tx_rf":
            target = str(config.get("rf_target") or "").strip()
        else:
            target = str(config.get("aprsis_target") or "").strip()
        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=int(context["flow"]["id"]),
            step_id=int(step["id"]),
            event_type="output_action",
            decision="tx",
            message=f"would transmit to target {target_label}:{target or '-'} | line={context['current_line']}",
        )
        return {"decision": "tx"}

    def _apply_updated_path(self, context: dict[str, Any], updated_path: str) -> None:
        parsed = dict(context.get("parsed") or {})
        parsed["path"] = updated_path
        context["parsed"] = parsed
        context["current_line"] = _build_tnc2_line(parsed)

    def _build_frame(
        self,
        *,
        source_kind: str,
        source_ref: str,
        raw_payload: str,
        frame_uid: str | None,
        created_at: str | None,
        enqueue_monotonic: float,
        rx_received_monotonic: float | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        timestamp = created_at or utc_now()
        line = str(raw_payload or "").rstrip("\r\n")
        return {
            "frame_uid": frame_uid or uuid.uuid4().hex,
            "source_kind": str(source_kind or "").strip(),
            "source_ref": str(source_ref or "").strip(),
            "raw_payload": line,
            "parsed": parse_tnc2_frame(line) if line else None,
            "metadata": _normalize_frame_metadata(metadata),
            "created_at": timestamp,
            "enqueue_monotonic": enqueue_monotonic,
            "rx_received_monotonic": rx_received_monotonic,
        }


def _normalize_frame_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in metadata.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        normalized[key_text] = value
    return normalized


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _split_path_tokens(path: str) -> list[str]:
    return [item.strip().upper() for item in path.split(",") if item.strip()]


def _receiver_source_ref_matches(flow_source_ref: str, runtime_source_ref: str) -> bool:
    return not _receiver_source_ref_aliases(flow_source_ref).isdisjoint(_receiver_source_ref_aliases(runtime_source_ref))


def _receiver_source_ref_aliases(value: str) -> set[str]:
    normalized = str(value or "").strip().casefold()
    if not normalized:
        return set()
    aliases = {normalized}
    if normalized.startswith("tnc@") and len(normalized) > 4:
        aliases.add(normalized[4:].strip())
    elif normalized:
        aliases.add(f"tnc@{normalized}")
    return {alias for alias in aliases if alias}


def _find_matching_path_spec(token: str, specs: list[str]) -> str | None:
    normalized_token = token.strip().upper().rstrip("*")
    for spec in specs:
        normalized_spec = spec.strip().upper().rstrip("*")
        if normalized_token == normalized_spec:
            return normalized_spec
    return None


def _find_matching_callsign_pattern(callsign: str, patterns: list[str]) -> str | None:
    normalized_callsign = callsign.strip().upper()
    for pattern in patterns:
        normalized_pattern = pattern.strip().upper()
        if _callsign_matches_pattern(normalized_callsign, normalized_pattern):
            return normalized_pattern
    return None


def _consumed_path_hops(path_tokens: list[str]) -> list[str]:
    return [token.rstrip("*") for token in path_tokens if token.endswith("*") and token.rstrip("*")]


def _find_matching_digi_pattern(consumed_hops: list[str], patterns: list[str]) -> tuple[str | None, str | None]:
    for hop in consumed_hops:
        matched_pattern = _find_matching_callsign_pattern(hop, patterns)
        if matched_pattern is not None:
            return matched_pattern, hop
    return None, None


def _find_blocked_strict_path_token(path_tokens: list[str]) -> str | None:
    for token in path_tokens:
        normalized = token.strip().upper().rstrip("*")
        if normalized in {"NOGATE", "RFONLY"}:
            return normalized
        if normalized in {"TCPIP", "TCPXX"} or normalized.startswith("TCPIP") or normalized.startswith("TCPXX"):
            return normalized
    return None


def _find_q_construct_path_token(path_tokens: list[str]) -> str | None:
    for token in path_tokens:
        normalized = token.strip().upper().rstrip("*")
        if len(normalized) == 3 and normalized.startswith("Q") and normalized[1:].isalpha():
            return normalized
    return None


def _find_blocked_strict_token(parsed: dict[str, Any]) -> dict[str, str] | None:
    outer_path = str(parsed.get("path") or "").strip().upper()
    outer_blocked = _find_blocked_strict_path_token(_split_path_tokens(outer_path))
    if outer_blocked is not None:
        return {"token": outer_blocked, "scope": "outer path", "path": outer_path}

    if not bool(parsed.get("is_third_party")):
        return None
    if not bool(parsed.get("third_party_inner_valid")):
        return {"token": "THIRD_PARTY_INVALID", "scope": "third-party payload", "path": outer_path}

    aprs_data = dict(parsed.get("aprs_data") or {})
    inner_path = str(aprs_data.get("inner_path") or "").strip().upper()
    inner_blocked = _find_blocked_strict_path_token(_split_path_tokens(inner_path))
    if inner_blocked is not None:
        return {"token": inner_blocked, "scope": "third-party inner path", "path": inner_path}
    return None


def _strict_reject_reason_key(blocked_token: str | None) -> str:
    normalized = str(blocked_token or "").strip().upper()
    if normalized == "THIRD_PARTY_INVALID":
        return APRSIS_STRICT_REASON_MALFORMED_THIRD_PARTY
    if normalized in {"NOGATE", "RFONLY"}:
        return APRSIS_STRICT_REASON_BLOCKED_NOGATE_RFONLY
    if normalized.startswith("TCPIP") or normalized.startswith("TCPXX"):
        return APRSIS_STRICT_REASON_BLOCKED_TCPIP_TCPXX
    return APRSIS_STRICT_REASON_OTHER


def _local_tx_strict_reject_reason(context: dict[str, Any], parsed: dict[str, Any]) -> tuple[str, str] | None:
    source_kind = str(context.get("source_kind") or "").strip()
    if source_kind != LOCAL_TX_SOURCE_KIND:
        return None

    metadata = dict(context.get("metadata") or {})
    origin = str(metadata.get("origin") or "").strip().lower()
    local_generated = _metadata_flag(metadata.get("local_generated"))
    if origin != "local_generated" or not local_generated:
        return (
            _t("Strict filter rejected Local TX frame because it is not marked as local-generated APRSBox traffic."),
            APRSIS_STRICT_REASON_OTHER,
        )

    if bool(parsed.get("is_third_party")):
        return (
            _t("Strict filter rejected Local TX frame because third-party encapsulation is not allowed for APRS-IS uplink."),
            APRSIS_STRICT_REASON_OTHER,
        )

    input_path = str(parsed.get("path") or "").strip().upper()
    blocked_q = _find_q_construct_path_token(_split_path_tokens(input_path))
    if blocked_q is not None:
        return (
            _tf(
                "Strict filter rejected Local TX frame because path contains q construct token {blocked_token}. Input path: {input_path}",
                {"blocked_token": blocked_q, "input_path": input_path or "-"},
            ),
            APRSIS_STRICT_REASON_OTHER,
        )
    return None


def _metadata_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _callsign_matches_pattern(callsign: str, pattern: str) -> bool:
    if not callsign or not pattern:
        return False
    if "*" not in pattern:
        return callsign == pattern
    regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    return re.match(regex, callsign) is not None


def _parse_rate_limit_seconds_text(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.casefold().endswith("s"):
        text = text[:-1].strip()
    if not text:
        return None
    try:
        seconds = int(text)
    except ValueError:
        return None
    if seconds < 5 or seconds > 300 or seconds % 5 != 0:
        return None
    return seconds


def _rate_limit_rules_from_config(config: dict[str, Any]) -> list[dict[str, Any]]:
    rules = config.get("rate_limit_rules")
    if isinstance(rules, list) and rules:
        normalized_rules: list[dict[str, Any]] = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            pattern = str(rule.get("source_callsign_pattern") or "").strip().upper()
            seconds = _parse_rate_limit_seconds_text(rule.get("rate_limit_seconds") or rule.get("seconds") or rule.get("limit"))
            if pattern and seconds:
                normalized_rules.append(
                    {
                        "source_callsign_pattern": pattern,
                        "rate_limit_seconds": seconds,
                    }
                )
        if normalized_rules:
            return normalized_rules

    legacy_pattern = str(config.get("source_callsign_pattern") or "").strip().upper()
    legacy_seconds = _parse_rate_limit_seconds_text(config.get("rate_limit_seconds") or config.get("packets_per_minute"))
    if legacy_pattern and legacy_seconds:
        return [{"source_callsign_pattern": legacy_pattern, "rate_limit_seconds": legacy_seconds}]
    return []


def _rate_limit_pattern_matches_source(pattern: str, source_callsign: str) -> bool:
    normalized_pattern = str(pattern or "").strip().upper()
    normalized_callsign = str(source_callsign or "").strip().upper()
    if not normalized_pattern or not normalized_callsign:
        return False
    if "*" in normalized_pattern:
        return _callsign_matches_pattern(normalized_callsign, normalized_pattern)
    pattern_base, pattern_ssid = split_callsign_ssid(normalized_pattern)
    source_base, source_ssid = split_callsign_ssid(normalized_callsign)
    if pattern_ssid:
        return normalized_callsign == normalized_pattern
    return source_base == pattern_base


def _rate_limit_rule_sort_key(rule: dict[str, Any]) -> tuple[int, int, int, int]:
    pattern = str(rule.get("source_callsign_pattern") or "").strip().upper()
    has_wildcard = 1 if "*" in pattern else 0
    _, ssid = split_callsign_ssid(pattern)
    specificity = len(pattern.replace("*", ""))
    return (0 if has_wildcard else 1, 1 if ssid else 0, specificity, 0)


def _find_rate_limit_rule(source_callsign: str, rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    matches: list[tuple[tuple[int, int, int, int], int, dict[str, Any]]] = []
    for index, rule in enumerate(rules):
        pattern = str(rule.get("source_callsign_pattern") or "").strip().upper()
        if not pattern:
            continue
        if _rate_limit_pattern_matches_source(pattern, source_callsign):
            matches.append((_rate_limit_rule_sort_key(rule), -index, rule))
    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0][2]


def _rewrite_trace_path(path_tokens: list[str], token_index: int, local_identity: str) -> list[str]:
    updated_tokens = list(path_tokens)
    token = updated_tokens[token_index].rstrip("*")
    match = _N_N_PATH_RE.fullmatch(token)
    updated_tokens[token_index] = f"{local_identity.upper()}*"
    if match is None:
        return updated_tokens

    alias = str(match.group("alias"))
    width = int(match.group("width"))
    remaining = int(match.group("remaining"))
    if remaining > 1:
        updated_tokens.insert(token_index + 1, f"{alias}{width}-{remaining - 1}")
    return updated_tokens


def _rewrite_no_trace_path(path_tokens: list[str], token_index: int) -> list[str]:
    updated_tokens = list(path_tokens)
    token = updated_tokens[token_index].rstrip("*")
    match = _N_N_PATH_RE.fullmatch(token)
    if match is None:
        updated_tokens[token_index] = f"{token}*"
        return updated_tokens

    alias = str(match.group("alias"))
    width = int(match.group("width"))
    remaining = int(match.group("remaining"))
    if remaining > 1:
        updated_tokens[token_index] = f"{alias}{width}-{remaining - 1}"
        return updated_tokens
    updated_tokens[token_index] = f"{alias}{width}*"
    return updated_tokens


def _build_tnc2_line(parsed: dict[str, Any]) -> str:
    header = f"{str(parsed.get('source') or '').strip()}>{str(parsed.get('destination') or '').strip()}"
    path = str(parsed.get("path") or "").strip()
    if path:
        header = f"{header},{path}"
    return f"{header}:{str(parsed.get('info') or '')}"


def _build_aprsis_uplink_line(
    parsed: dict[str, Any],
    *,
    local_igate: str,
    q_construct: str = "qAO",
    client_originated: bool = False,
) -> str:
    source = str(parsed.get("source") or "").strip()
    destination = str(parsed.get("destination") or "").strip()
    path = str(parsed.get("path") or "").strip()
    info = str(parsed.get("info") or "")
    if not source or not destination:
        return ""

    if client_originated:
        return f"{source}>{destination},TCPIP*:{info}"

    normalized_q = str(q_construct or "").strip()
    if normalized_q not in {"qAR", "qAO"}:
        return ""

    if bool(parsed.get("is_third_party")):
        if not bool(parsed.get("third_party_inner_valid")):
            return ""
        aprs_data = dict(parsed.get("aprs_data") or {})
        inner_source = str(aprs_data.get("inner_source_key") or "").strip()
        inner_destination = str(aprs_data.get("inner_destination") or "").strip()
        inner_path = str(aprs_data.get("inner_path") or "").strip()
        inner_info = str(aprs_data.get("inner_info") or "")
        outer_source = str(aprs_data.get("outer_source") or source).strip()
        outer_path = str(aprs_data.get("outer_path") or path).strip()
        if not inner_source or not inner_destination:
            return ""
        source = inner_source
        destination = inner_destination
        info = inner_info
        merged_path_tokens = [token for token in _split_path_tokens_keep_case(inner_path) if token]
        if outer_source:
            merged_path_tokens.append(outer_source)
        merged_path_tokens.extend(token for token in _split_path_tokens_keep_case(outer_path) if token)
    else:
        merged_path_tokens = [token for token in _split_path_tokens_keep_case(path) if token]

    merged_path_tokens.extend([normalized_q, local_igate])
    merged_path = ",".join(merged_path_tokens)
    header = f"{source}>{destination}"
    if merged_path:
        header = f"{header},{merged_path}"
    return f"{header}:{info}"


def _split_path_tokens_keep_case(path: str) -> list[str]:
    return [item.strip() for item in str(path or "").split(",") if item.strip()]


def _local_station_identity() -> str:
    station_settings = get_station_settings()
    return _build_source_key(station_settings.get("callsign"), station_settings.get("ssid"))


def _local_station_identities() -> dict[str, str]:
    station_settings = get_station_settings()
    identities: dict[str, str] = {}
    my_identity = _build_source_key(station_settings.get("callsign"), station_settings.get("ssid"))
    if my_identity:
        identities[my_identity] = _LOCAL_IDENTITY_MY

    wx_row = fetch_one("SELECT enabled, callsign, ssid FROM wx_config WHERE id = 1")
    if not wx_row:
        return identities

    wx_enabled = int(wx_row["enabled"] or 0) == 1
    raw_wx_callsign = str(wx_row["callsign"] or "").strip().upper()
    raw_wx_ssid = str(wx_row["ssid"] or "").strip()
    wx_has_explicit_identity = bool(raw_wx_callsign or raw_wx_ssid)
    if not wx_enabled and not wx_has_explicit_identity:
        return identities

    wx_callsign = raw_wx_callsign or str(station_settings.get("callsign") or "").strip().upper()
    wx_identity = _build_source_key(wx_callsign, raw_wx_ssid)
    if wx_identity:
        identities.setdefault(wx_identity, _LOCAL_IDENTITY_WX)
    return identities


def _find_consumed_local_identity(path_tokens: list[str], local_identities: dict[str, str]) -> tuple[str, str] | None:
    if not local_identities:
        return None
    for token in path_tokens:
        if not token.endswith("*"):
            continue
        consumed_hop = _canonical_callsign_identity(token.rstrip("*"))
        if not consumed_hop:
            continue
        owner = local_identities.get(consumed_hop)
        if owner:
            return consumed_hop, owner
    return None


def _build_source_key(callsign: Any, ssid: Any) -> str:
    callsign_text = str(callsign or "").strip().upper()
    ssid_text = str(ssid or "").strip()
    if ssid_text == "0":
        ssid_text = ""
    if not callsign_text:
        return ""
    return f"{callsign_text}-{ssid_text}" if ssid_text else callsign_text


def _canonical_callsign_identity(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if not normalized:
        return ""
    base, separator, suffix = normalized.partition("-")
    base = base.strip().upper()
    if not base:
        return ""
    if not separator:
        return base
    normalized_ssid = suffix.strip()
    if normalized_ssid in {"", "0"}:
        return base
    return f"{base}-{normalized_ssid}"


def _parse_coordinate(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _distance_filter_zones(config: dict[str, Any]) -> list[dict[str, float]]:
    raw_zones = config.get("zones")
    if not isinstance(raw_zones, list):
        return []
    normalized: list[dict[str, float]] = []
    for zone in raw_zones:
        if not isinstance(zone, dict):
            continue
        latitude = _parse_coordinate(zone.get("latitude"))
        longitude = _parse_coordinate(zone.get("longitude"))
        radius_km = _parse_coordinate(zone.get("radius_km"))
        if latitude is None or longitude is None or radius_km is None:
            continue
        if latitude < -90.0 or latitude > 90.0:
            continue
        if longitude < -180.0 or longitude > 180.0:
            continue
        if radius_km <= 0.0:
            continue
        normalized.append({"latitude": latitude, "longitude": longitude, "radius_km": radius_km})
    return normalized


def _parsed_aprs_position(parsed: dict[str, Any] | None) -> tuple[float, float] | None:
    aprs_data = dict((parsed or {}).get("aprs_data") or {})
    latitude = _parse_coordinate(aprs_data.get("latitude"))
    longitude = _parse_coordinate(aprs_data.get("longitude"))
    if latitude is None or longitude is None:
        return None
    if latitude < -90.0 or latitude > 90.0:
        return None
    if longitude < -180.0 or longitude > 180.0:
        return None
    return latitude, longitude


def _distance_km_between_points(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    earth_radius_km = 6371.0
    phi_1 = math.radians(latitude_a)
    phi_2 = math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a)
    delta_lambda = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0) ** 2
    )
    arc = 2.0 * math.atan2(math.sqrt(haversine), math.sqrt(1.0 - haversine))
    return earth_radius_km * arc


def _format_distance_km(value: float) -> str:
    if value < 1:
        return f"{value:.3f}".rstrip("0").rstrip(".")
    if value < 10:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _parsed_aprs_packet_type(parsed: dict[str, Any] | None) -> str:
    aprs_data = dict((parsed or {}).get("aprs_data") or {})
    return str(aprs_data.get("frame_type") or "").strip().upper()


def _parsed_aprs_symbol(parsed: dict[str, Any] | None) -> str:
    aprs_data = dict((parsed or {}).get("aprs_data") or {})
    return str(aprs_data.get("symbol") or "").strip().upper()


def _parsed_aprs_packet_group(parsed: dict[str, Any] | None) -> str:
    aprs_data = dict((parsed or {}).get("aprs_data") or {})
    return str(aprs_data.get("packet_group") or "").strip().casefold()


def _parsed_aprs_packet_type_code(parsed: dict[str, Any] | None) -> str:
    aprs_data = dict((parsed or {}).get("aprs_data") or {})
    return str(aprs_data.get("packet_type_code") or "").strip().casefold()


def _find_matching_packet_type_selector(parsed: dict[str, Any] | None, selectors: list[str]) -> str | None:
    packet_group = _parsed_aprs_packet_group(parsed)
    packet_type_code = _parsed_aprs_packet_type_code(parsed)
    frame_type = _parsed_aprs_packet_type(parsed)
    for selector in selectors:
        normalized = str(selector or "").strip()
        if not normalized:
            continue
        if packet_group and normalized.casefold() == packet_group:
            return normalized
        if packet_type_code and normalized.casefold() == packet_type_code:
            return normalized
        if frame_type and normalized.upper() == frame_type:
            return normalized
    return None


def _packet_type_filter_inspected_label(*, packet_group: str, packet_type_code: str) -> str:
    if packet_group and packet_type_code:
        return f"group {packet_group} (type {packet_type_code})"
    if packet_group:
        return f"group {packet_group}"
    if packet_type_code:
        return f"type {packet_type_code}"
    return "unknown"
