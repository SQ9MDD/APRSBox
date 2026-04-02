from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any

from app.db import log_event, utc_now
from app.services.content import get_station_settings, parse_tnc2_frame
from app.services.digi_flows import list_enabled_digi_flows, log_digi_flow_event

_N_N_PATH_RE = re.compile(r"^(?P<alias>[A-Z0-9]+)(?P<width>\d+)-(?P<remaining>\d+)$")


class DigiFlowRuntimeService:
    def __init__(self, *, poll_interval: float = 0.5) -> None:
        self._poll_interval = poll_interval
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="aprsbox-digi-flow-runtime")

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

    async def wait_until_idle(self) -> None:
        await self._queue.join()

    def enqueue_tnc2_frame(
        self,
        *,
        source_kind: str,
        source_ref: str,
        raw_payload: str,
        frame_uid: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        frame = self._build_frame(
            source_kind=source_kind,
            source_ref=source_ref,
            raw_payload=raw_payload,
            frame_uid=frame_uid,
            created_at=created_at,
        )
        self._queue.put_nowait(frame)
        return {
            "frame_uid": frame["frame_uid"],
            "created_at": frame["created_at"],
            "queue_depth": self._queue.qsize(),
            "parsed": bool(frame["parsed"]),
        }

    def enqueue_rx_tnc2_frame(self, line: str, *, source_ref: str) -> None:
        if not list_enabled_digi_flows(source_kind="receiver_rf", source_ref=source_ref):
            return
        self.enqueue_tnc2_frame(
            source_kind="receiver_rf",
            source_ref=source_ref,
            raw_payload=line,
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
        flows = list_enabled_digi_flows(
            source_kind=str(frame["source_kind"]),
            source_ref=str(frame["source_ref"]),
        )
        if not flows:
            return

        for flow in flows:
            flow_id = int(flow["id"])
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
                "source_kind": str(frame["source_kind"]),
                "source_ref": str(frame["source_ref"]),
                "raw_payload": str(frame["raw_payload"]),
                "current_line": str(frame["raw_payload"]),
                "parsed": dict(frame["parsed"]) if frame["parsed"] else None,
            }
            await self._execute_flow(context)

    async def _execute_flow(self, context: dict[str, Any]) -> None:
        flow = context["flow"]
        flow_id = int(flow["id"])
        last_decision = "continue"

        for step in flow.get("steps") or []:
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
            result = self._execute_step(context, step)
            last_decision = str(result["decision"])
            if last_decision != "continue":
                log_digi_flow_event(
                    frame_uid=context["frame_uid"],
                    flow_id=flow_id,
                    step_id=None,
                    event_type="pipeline_finished",
                    decision=last_decision,
                    message=f"Flow finished with decision {last_decision}.",
                )
                return

        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=None,
            event_type="pipeline_finished",
            decision=last_decision,
            message=f"Flow finished with decision {last_decision}.",
        )

    def _execute_step(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        step_type = str(step["step_type"])
        if step_type in {"receiver_rf", "receiver_aprsis"}:
            log_digi_flow_event(
                frame_uid=context["frame_uid"],
                flow_id=int(context["flow"]["id"]),
                step_id=int(step["id"]),
                event_type="source_step",
                decision="continue",
                message=f"Source step confirmed for {context['source_kind']}:{context['source_ref']}.",
            )
            return {"decision": "continue"}
        if step_type == "filter_callsign":
            return self._execute_callsign_filter(context, step)
        if step_type == "filter_path":
            return self._execute_path_rule(context, step)
        if step_type == "action_log":
            return self._execute_log_only(context, step)
        if step_type == "action_drop":
            return self._execute_drop(context, step)
        if step_type == "tx_rf":
            return self._execute_tx_stub(context, step, target_label="RF")
        if step_type == "tx_aprsis":
            return self._execute_tx_stub(context, step, target_label="APRS-IS")

        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=int(context["flow"]["id"]),
            step_id=int(step["id"]),
            event_type="step_stub",
            decision="continue",
            message=f"Step type {step_type} is not implemented in ETAP 2 and was skipped.",
        )
        return {"decision": "continue"}

    def _execute_callsign_filter(self, context: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        parsed = context.get("parsed") or {}
        callsign = str(parsed.get("source") or "").strip().upper()
        config = dict(step.get("config") or {})
        mode = str(config.get("mode") or "allow").strip().lower() or "allow"
        configured = [str(item).strip().upper() for item in config.get("callsigns") or [] if str(item).strip()]

        if not callsign:
            decision = "drop"
            message = "Callsign filter rejected frame because source callsign could not be parsed."
        elif mode == "allow":
            passed = callsign in configured
            decision = "continue" if passed else "drop"
            if configured:
                message = (
                    f"Callsign filter ({mode}) inspected {callsign}: "
                    f"{'passed' if passed else 'rejected'} because it is "
                    f"{'present' if passed else 'absent'} in the allow list."
                )
            else:
                message = f"Callsign filter ({mode}) inspected {callsign}: rejected because the allow list is empty."
        else:
            blocked = callsign in configured
            decision = "drop" if blocked else "continue"
            if configured:
                message = (
                    f"Callsign filter ({mode}) inspected {callsign}: "
                    f"{'rejected' if blocked else 'passed'} because it is "
                    f"{'present' if blocked else 'absent'} in the deny list."
                )
            else:
                message = f"Callsign filter ({mode}) inspected {callsign}: passed because the deny list is empty."

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
                message="Path rule rejected frame because TNC2 parsing failed.",
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
                message="Path rule rejected frame because the packet has no remaining path.",
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
                message=f"Path rule rejected frame because the input path {input_path or '-'} is already fully consumed.",
            )
            return {"decision": "drop"}

        candidate = path_tokens[first_unconsumed_index]
        config = dict(step.get("config") or {})
        trace_specs = [str(item).strip().upper() for item in config.get("trace_paths") or [] if str(item).strip()]
        no_trace_specs = [str(item).strip().upper() for item in config.get("no_trace_paths") or [] if str(item).strip()]
        matched_trace = _find_matching_path_spec(candidate, trace_specs)
        matched_no_trace = _find_matching_path_spec(candidate, no_trace_specs)

        if matched_trace:
            local_identity = _local_station_identity()
            if not local_identity:
                log_digi_flow_event(
                    frame_uid=context["frame_uid"],
                    flow_id=flow_id,
                    step_id=step_id,
                    event_type="path_rule",
                    decision="rejected",
                    message=f"Path rule matched TRACE {matched_trace} but local station callsign is not configured.",
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
                message=f"TRACE matched {matched_trace}. Path {input_path or '-'} -> {updated_path or '-'}.",
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
                message=f"NO_TRACE matched {matched_no_trace}. Path {input_path or '-'} -> {updated_path or '-'}.",
            )
            return {"decision": "continue"}

        log_digi_flow_event(
            frame_uid=context["frame_uid"],
            flow_id=flow_id,
            step_id=step_id,
            event_type="path_rule",
            decision="rejected",
            message=f"Path rule rejected frame because first remaining path {candidate} matched neither TRACE nor NO_TRACE. Input path: {input_path or '-'}",
        )
        return {"decision": "drop"}

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
    ) -> dict[str, Any]:
        timestamp = created_at or utc_now()
        line = str(raw_payload or "").strip()
        return {
            "frame_uid": frame_uid or uuid.uuid4().hex,
            "source_kind": str(source_kind or "").strip(),
            "source_ref": str(source_ref or "").strip(),
            "raw_payload": line,
            "parsed": parse_tnc2_frame(line) if line else None,
            "created_at": timestamp,
        }


def _split_path_tokens(path: str) -> list[str]:
    return [item.strip().upper() for item in path.split(",") if item.strip()]


def _find_matching_path_spec(token: str, specs: list[str]) -> str | None:
    normalized_token = token.strip().upper().rstrip("*")
    for spec in specs:
        normalized_spec = spec.strip().upper().rstrip("*")
        if normalized_token == normalized_spec:
            return normalized_spec
        family_match = _N_N_PATH_RE.fullmatch(normalized_token)
        if "-" not in normalized_spec and family_match and str(family_match.group("alias")) == normalized_spec:
            return normalized_spec
    return None


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
    updated_tokens[token_index] = f"{token}*"
    if match is None:
        return updated_tokens

    alias = str(match.group("alias"))
    width = int(match.group("width"))
    remaining = int(match.group("remaining"))
    if remaining > 1:
        updated_tokens.insert(token_index + 1, f"{alias}{width}-{remaining - 1}")
    return updated_tokens


def _build_tnc2_line(parsed: dict[str, Any]) -> str:
    header = f"{str(parsed.get('source') or '').strip()}>{str(parsed.get('destination') or '').strip()}"
    path = str(parsed.get("path") or "").strip()
    if path:
        header = f"{header},{path}"
    return f"{header}:{str(parsed.get('info') or '')}"


def _local_station_identity() -> str:
    station_settings = get_station_settings()
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    if not callsign:
        return ""
    ssid = str(station_settings.get("ssid") or "").strip()
    return f"{callsign}-{ssid}" if ssid else callsign
