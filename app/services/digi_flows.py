from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.db import fetch_all, fetch_one, get_connection, log_event, utc_now
from app.i18n import get_app_language, get_format_translator, get_translator
from app.services.mqtt_url import RX_CAPABLE_MODEM_TYPES, TX_CAPABLE_MODEM_TYPES

LOCAL_TX_SOURCE_KIND = "receiver_local_tx"
LOCAL_TX_SOURCE_REF = "local_tx"
SOURCE_STEP_TYPES = ("receiver_rf", LOCAL_TX_SOURCE_KIND)
FILTER_STEP_TYPES = (
    "filter_path",
    "filter_strict",
    "filter_dupe",
    "filter_direct_only",
    "filter_digi",
    "filter_callsign",
    "filter_packet_type",
    "filter_icon",
    "filter_distance",
    "filter_rate_limit",
    "filter_rate_limit_per_callsign",
)
TARGET_STEP_TYPES = ("tx_rf", "tx_aprsis", "action_drop", "action_log")
LOCAL_TX_ALLOWED_TARGET_KINDS = {"tx_aprsis", "action_log"}
APRSIS_ALLOWED_SOURCE_KINDS = {"receiver_rf", LOCAL_TX_SOURCE_KIND}
DIGI_FLOW_EXECUTION_RETENTION_LIMIT = 200
PACKET_TYPE_FILTER_GROUPS = (
    "position",
    "object",
    "item",
    "message",
    "status",
    "weather",
    "telemetry",
    "query",
)
PACKET_TYPE_FILTER_LEGACY_CODES = {"M", "S", "O", "W"}
DUPLICATE_FILTER_WINDOW_SECONDS = (2, 3, 4, 5, 6, 7)
DUPLICATE_FILTER_DEFAULT_WINDOW_SEC = 5
RATE_LIMIT_SECONDS_DEFAULT = 60
_RATE_LIMIT_RULE_LINE_RE = re.compile(r"^(?P<pattern>.+?)\s*(?:-\s*|\s+)(?P<limit>\S+)$")
DISTANCE_FILTER_MAX_ZONES = 3
ALL_STEP_TYPES = SOURCE_STEP_TYPES + FILTER_STEP_TYPES + TARGET_STEP_TYPES
RUNTIME_IMPLEMENTED_STEP_TYPES = {
    "receiver_rf",
    LOCAL_TX_SOURCE_KIND,
    "filter_dupe",
    "filter_path",
    "filter_strict",
    "filter_direct_only",
    "filter_digi",
    "filter_callsign",
    "filter_packet_type",
    "filter_icon",
    "filter_distance",
    "filter_rate_limit",
    "tx_rf",
    "tx_aprsis",
    "action_drop",
    "action_log",
}
RUNTIME_STUB_STEP_TYPES: set[str] = set()

STEP_TYPE_META: dict[str, dict[str, Any]] = {
    "receiver_rf": {
        "category": "source",
        "label": "Receiver RF",
        "badge": "Source",
        "description": "Receives packets from an RF input identifier.",
        "config_fields": (
            {"name": "rf_port", "label": "RF Port / Radio", "type": "text", "required": True},
        ),
    },
    "receiver_aprsis": {
        "category": "source",
        "label": "Receiver APRS-IS",
        "badge": "Source",
        "description": "Receives packets from an APRS-IS input identifier.",
        "config_fields": (
            {"name": "aprsis_source", "label": "APRS-IS Source", "type": "text", "required": True},
        ),
    },
    LOCAL_TX_SOURCE_KIND: {
        "category": "source",
        "label": "Local TX",
        "badge": "Source",
        "description": (
            "Local TX includes only frames generated locally by APRSBox, such as beacons, status packets, weather, "
            "objects, items, bulletins and messages. It does not include RF-received or digipeated frames."
        ),
        "config_fields": (
            {"name": "local_tx_source", "label": "Local TX Source", "type": "text", "required": True},
        ),
    },
    "filter_dupe": {
        "category": "filter",
        "label": "Duplicate Filter (viscous-delay)",
        "badge": "Filter",
        "description": (
            "Opens a short listening window after receiving a frame. During this time it checks whether "
            "the same frame was already repeated by another digipeater. If yes, the frame is dropped. "
            "If not, it moves to the next step after the window expires. This filter can be used only once "
            "and must be the first step in the flow."
        ),
        "config_fields": (
            {
                "name": "window_sec",
                "label": "Listening window",
                "type": "select",
                "required": True,
                "options": tuple(str(item) for item in DUPLICATE_FILTER_WINDOW_SECONDS),
            },
        ),
    },
    "filter_path": {
        "category": "filter",
        "label": "Path rule and DIGI guard",
        "badge": "Rule",
        "description": (
            "This mandatory block handles the DIGI path and blocks frames that should not be repeated: messages and "
            "queries addressed to local stations, third-party frames, and frames already repeated by this station."
        ),
        "editor_help_lines": (
            "messages/queries addressed to My station",
            "messages/queries addressed to WX station",
            "third-party frames",
            "frames already repeated by this station",
        ),
        "config_fields": (
            {"name": "mode", "label": "Mode", "type": "select", "required": True, "options": ("allow",)},
            {
                "name": "trace_paths",
                "label": "Paths (TRACE / traced)",
                "type": "textarea",
                "required": False,
                "help_lines": (
                    "One path alias or explicit hop per line.",
                    "TRACE example:",
                    "WIDE1-1",
                    "WIDE2-1",
                    "WIDE2-2",
                ),
            },
            {
                "name": "no_trace_paths",
                "label": "Paths (NO TRACE / not traced)",
                "type": "textarea",
                "required": False,
                "help_text": (
                    "One path alias or explicit hop per line. Matching hops are consumed without inserting the local "
                    "digi callsign. Good practice: include your own callsign-SSID from My settings."
                ),
            },
        ),
    },
    "filter_strict": {
        "category": "filter",
        "label": "Strict Filter",
        "badge": "Rule",
        "description": "Rejects TCPIP/TCPXX, NOGATE/RFONLY and invalid third-party packets",
        "editor_help_lines": (
            "This system guard rejects packets containing TCPIP, TCPXX, NOGATE or RFONLY in the outer path.",
            "For third-party packets, the inner header/path is validated and rejected when malformed.",
            "Valid third-party packets are inspected for blocked tokens in the inner path as well.",
        ),
        "config_fields": (),
    },
    "filter_direct_only": {
        "category": "filter",
        "label": "Direct Only",
        "badge": "Filter",
        "description": "Passes only packets heard direct, without any consumed digipeater hop in the path.",
        "editor_help_lines": (
            "This filter passes only packets heard direct from RF.",
            "If the path already contains any consumed hop marked with *, the packet is rejected.",
            "Use it when the flow should ignore packets already repeated by any digi.",
        ),
        "config_fields": (),
    },
    "filter_digi": {
        "category": "filter",
        "label": "DIGI Filter",
        "badge": "Filter",
        "description": "Allows or denies packets repeated by specific digi callsigns.",
        "editor_help_lines": (
            "Only already consumed hops are inspected, which means only path elements marked with * are checked.",
            "Patterns support * wildcard, for example SR5ABC, SR5BCD*, SR5* or *.",
            "allow passes packets only when at least one consumed hop matches.",
            "deny rejects packets when any consumed hop matches.",
        ),
        "config_fields": (
            {"name": "mode", "label": "Mode", "type": "select", "required": True, "options": ("allow", "deny")},
            {
                "name": "digis",
                "label": "DIGI Callsigns (one per line)",
                "type": "textarea",
                "required": False,
                "placeholder": "SR5ABC\nSR5BCD*\nSR5*\n*",
                "help_text": "Match against consumed digi hops only. Wildcard * is supported.",
            },
        ),
    },
    "filter_callsign": {
        "category": "filter",
        "label": "Callsign Filter",
        "badge": "Filter",
        "description": "Stores callsign allow or deny rules.",
        "editor_help_lines": (
            "This filter matches the source callsign of the packet.",
            "Patterns support * wildcard, for example SQ9MDD, SQ9MDD* or SQ*.",
            "allow passes only matching source callsigns.",
            "deny rejects matching source callsigns.",
        ),
        "config_fields": (
            {"name": "mode", "label": "Mode", "type": "select", "required": True, "options": ("allow", "deny")},
            {
                "name": "callsigns",
                "label": "Callsigns (one per line)",
                "type": "textarea",
                "required": False,
                "placeholder": "SQ9MDD\nSQ9MDD*\nSQ*",
                "help_text": "Match against the source callsign. Wildcard * is supported.",
            },
        ),
    },
    "filter_packet_type": {
        "category": "filter",
        "label": "Packet Type Filter",
        "badge": "Filter",
        "description": "Allows or denies the 8 main APRS packet groups used in DIGI flows.",
        "config_fields": (
            {"name": "mode", "label": "Mode", "type": "select", "required": True, "options": ("allow", "deny")},
            {
                "name": "packet_types",
                "label": "Packet Groups To Match (one per line)",
                "type": "textarea",
                "required": False,
                "placeholder": "position\nobject\nitem\nmessage\nstatus\nweather\ntelemetry\nquery",
                "help_lines": (
                    "Wpisuj jedna wartosc na linie:",
                    "**Przyklad**: position - wszystkie ramki z pozycja (takze timestamped, compressed i Mic-E).",
                    "object - obiekty APRS (;).",
                    "item - itemy APRS (zaczynajace sie od ')').",
                    "message - wiadomosci APRS, ACK/REJ, bulletin i announcement.",
                    "status - ramki status (>...).",
                    "weather - tylko ramki weather-only (_...).",
                    "Uwaga: pozycja z danymi pogody nadal liczy sie jako position, nie weather.",
                    "telemetry - T# oraz definicje PARM/UNIT/EQNS/BITS.",
                    "query - zapytania APRS zaczynajace sie od ?.",
                ),
                "help_text": "Zgodnosc wsteczna: nadal dzialaja kody M, S, O, W.",
            },
        ),
    },
    "filter_icon": {
        "category": "filter",
        "label": "Icon Filter",
        "badge": "Filter",
        "description": "Allows or denies selected APRS symbols such as /> or \\l.",
        "config_fields": (
            {"name": "mode", "label": "Mode", "type": "select", "required": True, "options": ("allow", "deny")},
            {
                "name": "icons",
                "label": "Icons (one per line)",
                "type": "textarea",
                "required": False,
                "placeholder": "/>\n\\l",
                "help_text": "Use APRS symbol values in table+code form, exactly as decoded by APRSBox, for example /> or \\l.",
            },
        ),
    },
    "filter_distance": {
        "category": "filter",
        "label": "Distance Filter",
        "badge": "Filter",
        "description": "Allows packets only when decoded position is inside at least one configured zone.",
        "editor_help_lines": (
            "This filter checks only packets where APRS position can be decoded from the current frame.",
            "The packet passes when it falls inside at least one configured zone.",
            "Packets without decoded position are not dropped by this filter.",
            "Distance zones are evaluated with OR logic (any matching zone passes).",
            "This filter can be used only once in a flow.",
        ),
        "config_fields": (
            {
                "name": "zones",
                "label": "Distance zones",
                "type": "distance_zones",
                "required": True,
                "help_text": "Define 1 to 3 center+radius zones. Radius below 1 km supports 0.1 km steps.",
            },
        ),
    },
    "filter_rate_limit": {
        "category": "filter",
        "label": "Rate Limit Filter",
        "badge": "Filter",
        "description": "Blocks matching source callsigns until their configured per-line limits have elapsed since the last passed frame.",
        "editor_help_lines": (
            "Enter one rule per line in the format CALL_OR_PATTERN - LIMIT.",
            "LIMIT accepts 30, 30s or 30S and must be between 5 and 300 seconds in 5-second steps.",
            "Wildcard * is supported; use it anywhere in the pattern, for example SQ* - 30s.",
        ),
        "config_fields": (
            {
                "name": "rate_limit_rules_text",
                "label": "Source callsign limits (one per line)",
                "type": "textarea",
                "required": True,
                "placeholder": "SQ9MDD-7 - 30s\nSQ2IDB* - 10s\nSP5XYZ - 60s\n* - 20s",
                "help_text": "Format: CALL_OR_PATTERN - LIMIT. LIMIT can be written as 30, 30s or 30S.",
            },
        ),
    },
    "filter_rate_limit_per_callsign": {
        "category": "filter",
        "label": "Rate Limit Per Callsign",
        "badge": "Filter",
        "description": "Stores a packet rate limit applied separately for each callsign.",
        "config_fields": (
            {"name": "packets_per_minute", "label": "Packets / Minute", "type": "number", "required": True},
        ),
    },
    "tx_rf": {
        "category": "target",
        "label": "TX RF",
        "badge": "Target",
        "description": "Sends packets to an RF output identifier.",
        "config_fields": (
            {"name": "rf_target", "label": "RF Target", "type": "text", "required": True},
        ),
    },
    "tx_aprsis": {
        "category": "target",
        "label": "TX APRS-IS",
        "badge": "Target",
        "description": "Sends packets to an APRS-IS output identifier.",
        "config_fields": (
            {"name": "aprsis_target", "label": "APRS-IS Target", "type": "text", "required": True},
        ),
    },
    "action_drop": {
        "category": "target",
        "label": "Action Drop",
        "badge": "Target",
        "description": "Drops the packet at the end of the flow.",
        "config_fields": (
            {"name": "note", "label": "Note", "type": "text", "required": False},
        ),
    },
    "action_log": {
        "category": "target",
        "label": "Black Hole",
        "badge": "Target",
        "description": "Logs the packet at the end of the flow.",
        "config_fields": (
            {"name": "log_tag", "label": "Log Tag", "type": "text", "required": False},
            {"name": "note", "label": "Note", "type": "text", "required": False},
        ),
    },
}

LEGACY_DEFAULT_STEP_TITLES = {
    "filter_path": {"Path Filter", "Path Rule", "Reguła ścieżki"},
    "filter_dupe": {"Duplicate Filter"},
}

STEP_TYPE_TO_REF_FIELD = {
    "receiver_rf": "rf_port",
    "receiver_aprsis": "aprsis_source",
    LOCAL_TX_SOURCE_KIND: "local_tx_source",
    "tx_rf": "rf_target",
    "tx_aprsis": "aprsis_target",
    "action_drop": "note",
    "action_log": "log_tag",
}
FLOW_LIST_ORDER_BY = "sort_order ASC, updated_at DESC, id DESC"


def _t(message: object) -> str:
    return get_translator(get_app_language())(message)


def _tf(message: object, params: dict[str, object] | None = None) -> str:
    return get_format_translator(get_app_language())(message, params)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _runtime_status(step_type: str) -> str:
    if step_type in RUNTIME_IMPLEMENTED_STEP_TYPES:
        return "implemented"
    if step_type in RUNTIME_STUB_STEP_TYPES:
        return "stub"
    return "config_only"


def _runtime_status_label(step_type: str) -> str:
    status = _runtime_status(step_type)
    if status == "implemented":
        return _t("Runtime")
    if status == "stub":
        return _t("Stub")
    return _t("Config only")


def _step_category(step_type: str) -> str:
    meta = STEP_TYPE_META.get(step_type)
    if not meta:
        raise ValueError(_tf("Unsupported flow step type: {step_type}.", {"step_type": step_type}))
    return str(meta["category"])


def _normalize_enabled(value: Any) -> int:
    return 1 if bool(value) else 0


def _normalize_number(value: Any, *, label: str, minimum: int = 0) -> int:
    text = _normalize_text(value)
    if not text:
        raise ValueError(_tf("{label} is required.", {"label": _t(label)}))
    try:
        parsed = int(text)
    except ValueError as exc:
        raise ValueError(_tf("{label} must be a whole number.", {"label": _t(label)})) from exc
    if parsed < minimum:
        raise ValueError(_tf("{label} must be at least {minimum}.", {"label": _t(label), "minimum": minimum}))
    return parsed


def _normalize_decimal(value: Any, *, label: str) -> float:
    text = _normalize_text(value)
    if not text:
        raise ValueError(_tf("{label} is required.", {"label": _t(label)}))
    try:
        parsed = float(text)
    except ValueError as exc:
        raise ValueError(_tf("{label} must be a number.", {"label": _t(label)})) from exc
    if not math.isfinite(parsed):
        raise ValueError(_tf("{label} must be a finite number.", {"label": _t(label)}))
    return parsed


def _normalize_distance_filter_zones(raw_zones: Any) -> list[dict[str, float]]:
    if not isinstance(raw_zones, list):
        raise ValueError(_t("Distance filter requires at least one zone."))
    if not raw_zones:
        raise ValueError(_t("Distance filter requires at least one zone."))
    if len(raw_zones) > DISTANCE_FILTER_MAX_ZONES:
        raise ValueError(_tf("Distance filter supports at most {count} zones.", {"count": DISTANCE_FILTER_MAX_ZONES}))

    normalized_zones: list[dict[str, float]] = []
    for index, raw_zone in enumerate(raw_zones, start=1):
        if not isinstance(raw_zone, dict):
            raise ValueError(_tf("Distance zone #{index} is invalid.", {"index": index}))
        latitude_text = _normalize_text(raw_zone.get("latitude"))
        longitude_text = _normalize_text(raw_zone.get("longitude"))
        radius_text = _normalize_text(raw_zone.get("radius_km"))
        any_value_present = bool(latitude_text or longitude_text or radius_text)
        if not any_value_present:
            raise ValueError(_tf("Distance zone #{index} cannot be empty.", {"index": index}))
        if not (latitude_text and longitude_text and radius_text):
            raise ValueError(
                _tf(
                    "Distance zone #{index} requires latitude, longitude and radius.",
                    {"index": index},
                )
            )

        latitude = _normalize_decimal(latitude_text, label="Latitude")
        longitude = _normalize_decimal(longitude_text, label="Longitude")
        radius_km = _normalize_decimal(radius_text, label="Radius km")
        if latitude < -90.0 or latitude > 90.0:
            raise ValueError(_tf("Distance zone #{index} latitude must be between -90 and 90.", {"index": index}))
        if longitude < -180.0 or longitude > 180.0:
            raise ValueError(_tf("Distance zone #{index} longitude must be between -180 and 180.", {"index": index}))
        if radius_km <= 0.0:
            raise ValueError(_tf("Distance zone #{index} radius must be greater than 0 km.", {"index": index}))
        if radius_km < 1.0:
            distance_100m_units = radius_km * 10.0
            if abs(distance_100m_units - round(distance_100m_units)) > 1e-9:
                raise ValueError(_tf("Distance zone #{index} radius below 1 km must use 0.1 km steps.", {"index": index}))
        normalized_zones.append(
            {
                "latitude": round(latitude, 5),
                "longitude": round(longitude, 5),
                "radius_km": round(radius_km, 3),
            }
        )

    if not normalized_zones:
        raise ValueError(_t("Distance filter requires at least one zone."))
    return normalized_zones


def _normalize_step_id(value: Any) -> int | None:
    text = _normalize_text(value)
    if not text:
        return None
    try:
        parsed = int(text)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _normalize_multiline_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    lines = []
    for raw_line in str(value or "").splitlines():
        item = raw_line.strip()
        if item:
            lines.append(item)
    return lines


def _normalize_rate_limit_seconds(value: Any, *, line_number: int | None = None) -> int:
    text = _normalize_text(value)
    if not text:
        label = _tf("Rate limit line #{line_number}", {"line_number": line_number}) if line_number is not None else _t("Rate limit seconds")
        raise ValueError(_tf("{label} is required.", {"label": label}))
    folded = text.casefold()
    if folded.endswith("s"):
        text = text[:-1].strip()
    if not text:
        label = _tf("Rate limit line #{line_number}", {"line_number": line_number}) if line_number is not None else _t("Rate limit seconds")
        raise ValueError(_tf("{label} is invalid.", {"label": label}))
    seconds = _normalize_number(text, label="Rate limit seconds", minimum=5)
    if seconds > 300 or seconds % 5 != 0:
        raise ValueError(
            _t("Rate limit seconds must be between 5 and 300 in 5-second steps.")
        )
    return seconds


def _parse_rate_limit_rule_line(raw_line: str, *, line_number: int) -> dict[str, Any]:
    line = str(raw_line or "").strip()
    if not line or line.startswith("#"):
        return {}
    match = _RATE_LIMIT_RULE_LINE_RE.fullmatch(line)
    if match is None:
        raise ValueError(_tf("Rate limit line #{line_number} is invalid: expected CALL_OR_PATTERN - LIMIT.", {"line_number": line_number}))
    pattern = _normalize_text(match.group("pattern"))
    if not pattern:
        raise ValueError(_tf("Rate limit line #{line_number} is invalid: pattern is required.", {"line_number": line_number}))
    try:
        rate_limit_seconds = _normalize_rate_limit_seconds(match.group("limit"), line_number=line_number)
    except ValueError as exc:
        raise ValueError(
            _tf(
                "Rate limit line #{line_number} is invalid: {reason}.",
                {"line_number": line_number, "reason": str(exc)},
            )
        ) from exc
    return {
        "source_callsign_pattern": pattern.upper(),
        "rate_limit_seconds": rate_limit_seconds,
    }


def _normalize_rate_limit_rules(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        normalized_rules: list[dict[str, Any]] = []
        for index, item in enumerate(value, start=1):
            if isinstance(item, dict):
                pattern = _normalize_text(item.get("source_callsign_pattern") or item.get("pattern"))
                if not pattern:
                    raise ValueError(_tf("Rate limit line #{line_number} is invalid: pattern is required.", {"line_number": index}))
                try:
                    seconds = _normalize_rate_limit_seconds(item.get("rate_limit_seconds") or item.get("seconds") or item.get("limit"), line_number=index)
                except ValueError as exc:
                    raise ValueError(
                        _tf(
                            "Rate limit line #{line_number} is invalid: {reason}.",
                            {"line_number": index, "reason": str(exc)},
                        )
                    ) from exc
                normalized_rules.append({"source_callsign_pattern": pattern.upper(), "rate_limit_seconds": seconds})
                continue
            if isinstance(item, str):
                parsed = _parse_rate_limit_rule_line(item, line_number=index)
                if parsed:
                    normalized_rules.append(parsed)
                continue
            raise ValueError(_tf("Rate limit line #{line_number} is invalid.", {"line_number": index}))
        if not normalized_rules:
            raise ValueError(_t("Rate limit filter requires at least one rule."))
        return normalized_rules

    normalized_rules = []
    for line_number, raw_line in enumerate(str(value or "").splitlines(), start=1):
        parsed = _parse_rate_limit_rule_line(raw_line, line_number=line_number)
        if parsed:
            normalized_rules.append(parsed)
    if not normalized_rules:
        raise ValueError(_t("Rate limit filter requires at least one rule."))
    return normalized_rules


def _normalize_packet_type_filter_value(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    folded = normalized.casefold()
    if folded in PACKET_TYPE_FILTER_GROUPS:
        return folded
    upper = normalized.upper()
    if upper in PACKET_TYPE_FILTER_LEGACY_CODES:
        return upper
    return normalized


def _packet_type_filter_value_label(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    folded = normalized.casefold()
    if folded == "position":
        return "position"
    if folded == "object":
        return "object"
    if folded == "item":
        return "item"
    if folded == "message":
        return "message"
    if folded == "status":
        return "status"
    if folded == "weather":
        return "weather"
    if folded == "telemetry":
        return "telemetry"
    if folded == "query":
        return "query"
    upper = normalized.upper()
    if upper == "M":
        return _t("legacy M (mobile position)")
    if upper == "S":
        return _t("legacy S (stationary position)")
    if upper == "O":
        return _t("legacy O (object)")
    if upper == "W":
        return _t("legacy W (weather-only)")
    return normalized


def _flow_requires_path_rule(target_kind: str) -> bool:
    return target_kind == "tx_rf"


def _has_enabled_step_type(steps: list[dict[str, Any]], step_type: str) -> bool:
    return any(step["step_type"] == step_type and int(step.get("enabled") or 0) == 1 for step in steps[1:-1])


def _has_enabled_path_rule(steps: list[dict[str, Any]]) -> bool:
    return _has_enabled_step_type(steps, "filter_path")


def _has_enabled_aprsis_strict_guard(steps: list[dict[str, Any]]) -> bool:
    middle_steps = list(steps[1:-1])
    if len(middle_steps) != 1:
        return False
    strict_step = middle_steps[0]
    return strict_step.get("step_type") == "filter_strict" and int(strict_step.get("enabled") or 0) == 1


def _normalize_tx_rf_flow_step_order(steps: list[dict[str, Any]]) -> None:
    if len(steps) < 2:
        return
    source_step = steps[0]
    target_step = steps[-1]
    middle_steps = list(steps[1:-1])
    viscous_delay_steps = [step for step in middle_steps if step["step_type"] == "filter_dupe"]
    rate_limit_steps = [step for step in middle_steps if step["step_type"] == "filter_rate_limit"]
    other_steps = [
        step
        for step in middle_steps
        if step["step_type"] not in {"filter_dupe", "filter_rate_limit", "filter_path"}
    ]
    path_steps = [step for step in middle_steps if step["step_type"] == "filter_path"]
    steps[:] = [source_step, *viscous_delay_steps, *other_steps, *rate_limit_steps, *path_steps, target_step]
    _reindex_steps(steps)


def _reindex_steps(steps: list[dict[str, Any]]) -> None:
    for index, step in enumerate(steps, start=1):
        step["step_order"] = index


def _default_step_title(step_type: str) -> str:
    return str(STEP_TYPE_META[step_type]["label"])


def _normalize_step_title(step_type: str, raw_title: Any) -> str:
    title = _normalize_text(raw_title)
    default_title = _default_step_title(step_type)
    if not title:
        return default_title
    if title in LEGACY_DEFAULT_STEP_TITLES.get(step_type, set()):
        return default_title
    return title


def _default_step_config(step_type: str, ref_value: str = "") -> dict[str, Any]:
    if step_type == "receiver_rf":
        return {"rf_port": ref_value}
    if step_type == "receiver_aprsis":
        return {"aprsis_source": ref_value}
    if step_type == LOCAL_TX_SOURCE_KIND:
        return {"local_tx_source": ref_value or LOCAL_TX_SOURCE_REF}
    if step_type == "filter_dupe":
        return {"window_sec": DUPLICATE_FILTER_DEFAULT_WINDOW_SEC}
    if step_type == "filter_direct_only":
        return {}
    if step_type == "filter_digi":
        return {"mode": "allow", "digis": []}
    if step_type == "filter_path":
        return {"mode": "allow", "trace_paths": [], "no_trace_paths": []}
    if step_type == "filter_strict":
        return {}
    if step_type == "filter_callsign":
        return {"mode": "allow", "callsigns": []}
    if step_type == "filter_packet_type":
        return {"mode": "allow", "packet_types": []}
    if step_type == "filter_icon":
        return {"mode": "allow", "icons": []}
    if step_type == "filter_distance":
        return {"zones": [{"latitude": "", "longitude": "", "radius_km": ""}]}
    if step_type == "filter_rate_limit":
        return {"rate_limit_rules_text": "* - 60s"}
    if step_type == "filter_rate_limit_per_callsign":
        return {"packets_per_minute": 30}
    if step_type == "tx_rf":
        return {"rf_target": ref_value}
    if step_type == "tx_aprsis":
        return {"aprsis_target": ref_value or "aprsis"}
    if step_type == "action_drop":
        return {"note": ""}
    if step_type == "action_log":
        return {"log_tag": "", "note": ""}
    raise ValueError(_tf("Unsupported flow step type: {step_type}.", {"step_type": step_type}))


def _normalize_step_config(step_type: str, raw_config: dict[str, Any]) -> dict[str, Any]:
    config = dict(raw_config or {})
    if step_type == "receiver_rf":
        value = _normalize_text(config.get("rf_port"))
        if not value:
            raise ValueError(_t("Receiver RF step requires an RF Port / Radio value."))
        return {"rf_port": value}
    if step_type == "receiver_aprsis":
        value = _normalize_text(config.get("aprsis_source"))
        if not value:
            raise ValueError(_t("Receiver APRS-IS step requires an APRS-IS Source value."))
        return {"aprsis_source": value}
    if step_type == LOCAL_TX_SOURCE_KIND:
        value = _normalize_text(config.get("local_tx_source")) or LOCAL_TX_SOURCE_REF
        return {"local_tx_source": value}
    if step_type == "filter_dupe":
        window_sec = _normalize_number(config.get("window_sec"), label="Listening window", minimum=2)
        if window_sec not in DUPLICATE_FILTER_WINDOW_SECONDS:
            raise ValueError(
                _tf(
                    "Listening window must be one of: {values}.",
                    {"values": ", ".join(f"{item} s" for item in DUPLICATE_FILTER_WINDOW_SECONDS)},
                )
            )
        return {"window_sec": window_sec}
    if step_type == "filter_path":
        mode = _normalize_text(config.get("mode")).lower() or "allow"
        if mode != "allow":
            raise ValueError(_t("Path filter mode must be allow."))
        legacy_paths = _normalize_multiline_list(config.get("paths"))
        trace_paths = _normalize_multiline_list(config.get("trace_paths")) or legacy_paths
        no_trace_paths = _normalize_multiline_list(config.get("no_trace_paths"))
        return {"mode": mode, "trace_paths": trace_paths, "no_trace_paths": no_trace_paths}
    if step_type == "filter_strict":
        return {}
    if step_type == "filter_direct_only":
        return {}
    if step_type == "filter_digi":
        mode = _normalize_text(config.get("mode")).lower() or "allow"
        if mode not in {"allow", "deny"}:
            raise ValueError(_t("DIGI filter mode must be allow or deny."))
        return {"mode": mode, "digis": _normalize_multiline_list(config.get("digis"))}
    if step_type == "filter_callsign":
        mode = _normalize_text(config.get("mode")).lower() or "allow"
        if mode not in {"allow", "deny"}:
            raise ValueError(_t("Callsign filter mode must be allow or deny."))
        return {"mode": mode, "callsigns": _normalize_multiline_list(config.get("callsigns"))}
    if step_type == "filter_packet_type":
        mode = _normalize_text(config.get("mode")).lower() or "allow"
        if mode not in {"allow", "deny"}:
            raise ValueError(_t("Packet type filter mode must be allow or deny."))
        return {
            "mode": mode,
            "packet_types": [
                normalized
                for normalized in (
                    _normalize_packet_type_filter_value(item)
                    for item in _normalize_multiline_list(config.get("packet_types"))
                )
                if normalized
            ],
        }
    if step_type == "filter_icon":
        mode = _normalize_text(config.get("mode")).lower() or "allow"
        if mode not in {"allow", "deny"}:
            raise ValueError(_t("Icon filter mode must be allow or deny."))
        return {"mode": mode, "icons": _normalize_multiline_list(config.get("icons"))}
    if step_type == "filter_distance":
        return {"zones": _normalize_distance_filter_zones(config.get("zones"))}
    if step_type == "filter_rate_limit":
        raw_rules = config.get("rate_limit_rules_text")
        if raw_rules is None or not _normalize_text(raw_rules):
            if config.get("rate_limit_rules"):
                raw_rules = config.get("rate_limit_rules")
            else:
                raw_pattern = _normalize_text(config.get("source_callsign_pattern")) or "*"
                raw_seconds = config.get("rate_limit_seconds")
                if raw_seconds is None or not _normalize_text(raw_seconds):
                    raw_seconds = config.get("packets_per_minute")
                raw_rules = f"{raw_pattern} - {raw_seconds or RATE_LIMIT_SECONDS_DEFAULT}s"
        return {"rate_limit_rules": _normalize_rate_limit_rules(raw_rules)}
    if step_type == "filter_rate_limit_per_callsign":
        return {"packets_per_minute": _normalize_number(config.get("packets_per_minute"), label="Packets per minute", minimum=1)}
    if step_type == "tx_rf":
        value = _normalize_text(config.get("rf_target"))
        if not value:
            raise ValueError(_t("TX RF step requires an RF Target value."))
        return {"rf_target": value}
    if step_type == "tx_aprsis":
        return {"aprsis_target": _normalize_text(config.get("aprsis_target")) or "aprsis"}
    if step_type == "action_drop":
        return {"note": _normalize_text(config.get("note"))}
    if step_type == "action_log":
        return {"log_tag": _normalize_text(config.get("log_tag")), "note": _normalize_text(config.get("note"))}
    raise ValueError(_tf("Unsupported flow step type: {step_type}.", {"step_type": step_type}))


def _step_ref_value(step_type: str, config: dict[str, Any]) -> str:
    field_name = STEP_TYPE_TO_REF_FIELD.get(step_type, "")
    if not field_name:
        return ""
    value = config.get(field_name, "")
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip())
    return _normalize_text(value)


def _step_summary(step_type: str, config: dict[str, Any]) -> str:
    if step_type == "receiver_rf":
        return f"RF port: {_normalize_text(config.get('rf_port')) or '-'}"
    if step_type == "receiver_aprsis":
        return f"APRS-IS source: {_normalize_text(config.get('aprsis_source')) or '-'}"
    if step_type == LOCAL_TX_SOURCE_KIND:
        return _t("Locally generated APRSBox TX frames")
    if step_type == "filter_dupe":
        return f"Window: {config.get('window_sec', '-')!s} sec"
    if step_type == "filter_digi":
        digis = config.get("digis") or []
        return f"Mode: {config.get('mode', 'allow')}, digis: {len(digis)}"
    if step_type == "filter_path":
        trace_paths = config.get("trace_paths") or []
        no_trace_paths = config.get("no_trace_paths") or []
        return f"Allow only, paths: {len(trace_paths) + len(no_trace_paths)}"
    if step_type == "filter_strict":
        return _t("Rejects TCPIP/TCPXX, NOGATE/RFONLY and invalid third-party packets")
    if step_type == "filter_direct_only":
        return _t("Passes only direct packets")
    if step_type == "filter_callsign":
        callsigns = config.get("callsigns") or []
        return f"Mode: {config.get('mode', 'allow')}, callsigns: {len(callsigns)}"
    if step_type == "filter_packet_type":
        packet_types = config.get("packet_types") or []
        labels = [_packet_type_filter_value_label(item) for item in packet_types if _packet_type_filter_value_label(item)]
        if not labels:
            return f"Mode: {config.get('mode', 'allow')}, packet groups: none"
        return f"Mode: {config.get('mode', 'allow')}, packet groups: {', '.join(labels)}"
    if step_type == "filter_icon":
        icons = config.get("icons") or []
        return f"Mode: {config.get('mode', 'allow')}, icons: {', '.join(icons) if icons else 'none'}"
    if step_type == "filter_distance":
        zones = config.get("zones") or []
        return _tf("Distance zones: {count}.", {"count": len(zones)})
    if step_type == "filter_rate_limit":
        rules = config.get("rate_limit_rules")
        if isinstance(rules, list) and rules:
            rule_count = len(rules)
        else:
            text = str(config.get("rate_limit_rules_text") or "").strip()
            rule_count = len([line for line in text.splitlines() if line.strip() and not line.strip().startswith("#")])
        return f"Rules: {rule_count or '-'}"
    if step_type == "filter_rate_limit_per_callsign":
        return f"Per callsign: {config.get('packets_per_minute', '-')!s} pkt/min"
    if step_type == "tx_rf":
        return f"RF target: {_normalize_text(config.get('rf_target')) or '-'}"
    if step_type == "tx_aprsis":
        return _t("APRS-IS uplink")
    if step_type == "action_drop":
        note = _normalize_text(config.get("note"))
        return note or "Drop packet"
    if step_type == "action_log":
        log_tag = _normalize_text(config.get("log_tag"))
        note = _normalize_text(config.get("note"))
        parts = [part for part in (f"Tag: {log_tag}" if log_tag else "", note) if part]
        return " | ".join(parts) if parts else "Log packet"
    return ""


def get_digi_flow_type_meta() -> dict[str, dict[str, Any]]:
    return {
        step_type: {
            "category": meta["category"],
            "label": _t(meta["label"]),
            "badge": _t(meta["badge"]),
            "description": _t(meta["description"]),
            **({"editor_help_lines": [_t(line) for line in meta["editor_help_lines"]]} if meta.get("editor_help_lines") else {}),
            "runtime_status": _runtime_status(step_type),
            "runtime_label": _runtime_status_label(step_type),
            "config_fields": [
                {
                    **dict(field),
                    "label": _t(field["label"]),
                    **({"placeholder": _t(field["placeholder"])} if field.get("placeholder") else {}),
                    **({"help_text": _t(field["help_text"])} if field.get("help_text") else {}),
                    **({"help_lines": [_t(line) for line in field["help_lines"]]} if field.get("help_lines") else {}),
                }
                for field in meta["config_fields"]
            ],
        }
        for step_type, meta in STEP_TYPE_META.items()
    }


def get_digi_flow_reference_options() -> dict[str, list[str]]:
    source_type_filter = ", ".join(f"'{item}'" for item in RX_CAPABLE_MODEM_TYPES)
    target_type_filter = ", ".join(f"'{item}'" for item in TX_CAPABLE_MODEM_TYPES)
    source_rows = fetch_all(
        f"""
        SELECT name FROM modems
        WHERE modem_type IN ({source_type_filter})
        ORDER BY name COLLATE NOCASE ASC, id ASC
        """
    )
    target_rows = fetch_all(
        f"""
        SELECT name FROM modems
        WHERE modem_type IN ({target_type_filter})
        ORDER BY name COLLATE NOCASE ASC, id ASC
        """
    )
    return {
        "receiver_rf": [str(row["name"]) for row in source_rows if row["name"]],
        LOCAL_TX_SOURCE_KIND: [LOCAL_TX_SOURCE_REF],
        "tx_rf": [str(row["name"]) for row in target_rows if row["name"]],
        "tx_aprsis": ["aprsis"],
        "action_drop": ["drop"],
        "action_log": ["log-only"],
    }


def get_digi_flow_endpoint_options(
    *,
    selected_source_selector: str | None = None,
    selected_target_selector: str | None = None,
    current_flow_id: int | None = None,
) -> dict[str, Any]:
    source_type_filter = ", ".join(f"'{item}'" for item in RX_CAPABLE_MODEM_TYPES)
    target_type_filter = ", ".join(f"'{item}'" for item in TX_CAPABLE_MODEM_TYPES)
    source_rows = fetch_all(
        f"""
        SELECT name FROM modems
        WHERE modem_type IN ({source_type_filter})
        ORDER BY name COLLATE NOCASE ASC, id ASC
        """
    )
    target_rows = fetch_all(
        f"""
        SELECT name FROM modems
        WHERE modem_type IN ({target_type_filter})
        ORDER BY name COLLATE NOCASE ASC, id ASC
        """
    )
    source_options = [
        {"value": f"receiver_rf::{row['name']}", "label": str(row["name"]), "kind": "receiver_rf", "ref": str(row["name"])}
        for row in source_rows
        if row["name"]
    ]
    source_options.append(
        {
            "value": f"{LOCAL_TX_SOURCE_KIND}::{LOCAL_TX_SOURCE_REF}",
            "label": _t("Local TX"),
            "kind": LOCAL_TX_SOURCE_KIND,
            "ref": LOCAL_TX_SOURCE_REF,
        }
    )
    target_options = [
        {"value": f"tx_rf::{row['name']}", "label": str(row["name"]), "kind": "tx_rf", "ref": str(row["name"])}
        for row in target_rows
        if row["name"]
    ]
    target_options.append(
        {
            "value": "tx_aprsis::aprsis",
            "label": _t("APRS-IS uplink"),
            "kind": "tx_aprsis",
            "ref": "aprsis",
        }
    )
    if str(selected_target_selector or "").strip() == "action_drop::drop":
        target_options.append({"value": "action_drop::drop", "label": _t("Drop"), "kind": "action_drop", "ref": "drop"})
    target_options.append({"value": "action_log::log-only", "label": _t("Black Hole"), "kind": "action_log", "ref": "log-only"})
    target_by_source_kind = {
        "receiver_rf": list(target_options),
        LOCAL_TX_SOURCE_KIND: [
            option for option in target_options if str(option.get("kind") or "").strip() in LOCAL_TX_ALLOWED_TARGET_KINDS
        ],
    }
    _ = selected_source_selector
    _ = current_flow_id
    return {"source": source_options, "target": target_options, "target_by_source_kind": target_by_source_kind}


def _serialize_step_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    step = dict(row)
    try:
        config = json.loads(step.get("config_json") or "{}")
    except json.JSONDecodeError:
        config = {}
    step_type = _normalize_text(step.get("step_type"))
    step["config"] = config
    step["step_category"] = _step_category(step_type)
    step["step_label"] = STEP_TYPE_META[step_type]["label"]
    step["step_badge"] = STEP_TYPE_META[step_type]["badge"]
    step["config_summary"] = _step_summary(step_type, config)
    return step


def _serialize_flow_row(row: sqlite3.Row | dict[str, Any], steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    flow = dict(row)
    flow["enabled"] = int(flow.get("enabled") or 0)
    flow["sort_order"] = int(flow.get("sort_order") or 0)
    if steps is None:
        steps = get_digi_flow_steps(int(flow["id"]))
    flow["steps"] = steps
    flow["step_count"] = len(steps)
    flow["source_display"] = _flow_endpoint_display(flow.get("source_kind"), flow.get("source_ref"))
    flow["target_display"] = _flow_endpoint_display(flow.get("target_kind"), flow.get("target_ref"))
    return flow


def _flow_endpoint_display(kind: Any, ref: Any) -> str:
    normalized_kind = _normalize_text(kind)
    normalized_ref = _normalize_text(ref)
    if normalized_kind == LOCAL_TX_SOURCE_KIND and normalized_ref == LOCAL_TX_SOURCE_REF:
        return _t("Local TX")
    if normalized_kind == "tx_aprsis":
        return _t("APRS-IS uplink")
    if normalized_kind == "action_log" and normalized_ref == "log-only":
        return _t("Black Hole")
    if normalized_kind == "action_drop" and normalized_ref == "drop":
        return _t("Drop")
    if normalized_ref:
        return normalized_ref
    return normalized_kind or normalized_ref or "-"


def list_digi_flows() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT id, name, description, source_kind, source_ref, target_kind, target_ref, enabled, sort_order, created_at, updated_at
        FROM digi_flows
        ORDER BY sort_order ASC, updated_at DESC, id DESC
        """
    )
    return [_serialize_flow_row(row, steps=get_digi_flow_steps(int(row["id"]))) for row in rows]


def list_enabled_digi_flows(*, source_kind: str | None = None, source_ref: str | None = None) -> list[dict[str, Any]]:
    query = """
        SELECT id, name, description, source_kind, source_ref, target_kind, target_ref, enabled, sort_order, created_at, updated_at
        FROM digi_flows
        WHERE enabled = 1
    """
    params: list[Any] = []
    if source_kind is not None:
        query += " AND source_kind = ?"
        params.append(source_kind)
    if source_ref is not None:
        query += " AND source_ref = ?"
        params.append(source_ref)
    query += " ORDER BY updated_at DESC, id DESC"
    rows = fetch_all(query, tuple(params))
    return [_serialize_flow_row(row, steps=get_digi_flow_steps(int(row["id"]))) for row in rows]


def has_enabled_local_tx_aprsis_flow() -> bool:
    row = fetch_one(
        """
        SELECT 1
        FROM digi_flows
        WHERE enabled = 1
          AND source_kind = ?
          AND source_ref = ?
          AND target_kind = 'tx_aprsis'
        LIMIT 1
        """,
        (LOCAL_TX_SOURCE_KIND, LOCAL_TX_SOURCE_REF),
    )
    return row is not None


def get_digi_flow_steps(flow_id: int) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT id, flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
        FROM digi_flow_steps
        WHERE flow_id = ?
        ORDER BY step_order ASC, id ASC
        """,
        (flow_id,),
    )
    return [_serialize_step_row(row) for row in rows]


def get_digi_flow(flow_id: int) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT id, name, description, source_kind, source_ref, target_kind, target_ref, enabled, sort_order, created_at, updated_at
        FROM digi_flows
        WHERE id = ?
        """,
        (flow_id,),
    )
    if row is None:
        return None
    return _serialize_flow_row(row)


def build_digi_flow_editor_payload(flow: dict[str, Any] | None = None) -> dict[str, Any]:
    if flow:
        return {
            "name": flow.get("name", ""),
            "description": flow.get("description", ""),
            "source_selector": f"{flow.get('source_kind')}::{flow.get('source_ref')}",
            "target_selector": f"{flow.get('target_kind')}::{flow.get('target_ref')}",
            "source_kind": flow.get("source_kind", "receiver_rf"),
            "source_ref": flow.get("source_ref", ""),
            "target_kind": flow.get("target_kind", "tx_rf"),
            "target_ref": flow.get("target_ref", ""),
            "enabled": int(flow.get("enabled") or 0),
            "steps": [
                {
                    "id": step.get("id"),
                    "step_type": step.get("step_type"),
                    "title": step.get("title"),
                    "enabled": int(step.get("enabled") or 0),
                    "config": dict(step.get("config") or {}),
                }
                for step in flow.get("steps", [])
            ],
        }
    return {
        "name": "",
        "description": "",
        "source_selector": "",
        "target_selector": "action_log::log-only",
        "source_kind": "receiver_rf",
        "source_ref": "",
        "target_kind": "action_log",
        "target_ref": "log-only",
        "enabled": 1,
        "steps": [
            {
                "step_type": "receiver_rf",
                "title": _default_step_title("receiver_rf"),
                "enabled": 1,
                "config": _default_step_config("receiver_rf"),
            },
            {
                "step_type": "action_log",
                "title": _default_step_title("action_log"),
                "enabled": 1,
                "config": _default_step_config("action_log", "log-only"),
            },
        ],
    }


def normalize_digi_flow_payload(payload: dict[str, Any], *, existing_flow_id: int | None = None) -> dict[str, Any]:
    name = _normalize_text(payload.get("name"))
    if not name:
        raise ValueError(_t("Flow name is required."))
    description = _normalize_text(payload.get("description"))
    source_kind = _normalize_text(payload.get("source_kind"))
    target_kind = _normalize_text(payload.get("target_kind"))
    if source_kind not in SOURCE_STEP_TYPES:
        raise ValueError(_t("Flow source must be one of the supported source step types."))
    if target_kind not in TARGET_STEP_TYPES:
        raise ValueError(_t("Flow target must be one of the supported target step types."))
    source_ref = _normalize_text(payload.get("source_ref"))
    target_ref = _normalize_text(payload.get("target_ref"))
    if source_kind == LOCAL_TX_SOURCE_KIND and not source_ref:
        source_ref = LOCAL_TX_SOURCE_REF
    if target_kind == "tx_aprsis" and not target_ref:
        target_ref = "aprsis"
    if not source_ref:
        raise ValueError(_t("Flow source reference is required."))
    if source_kind == LOCAL_TX_SOURCE_KIND and target_kind not in LOCAL_TX_ALLOWED_TARGET_KINDS:
        raise ValueError(_t("Local TX source can target only APRS-IS uplink or Black Hole."))
    if target_kind in {"tx_rf", "tx_aprsis"} and not target_ref:
        raise ValueError(_t("Flow target reference is required."))

    raw_steps = payload.get("steps") or []
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError(_t("Flow must contain at least one source step and one target step."))

    normalized_steps: list[dict[str, Any]] = []
    source_count = 0
    target_count = 0
    for index, raw_step in enumerate(raw_steps, start=1):
        if not isinstance(raw_step, dict):
            raise ValueError(_t("Invalid flow step payload."))
        step_type = _normalize_text(raw_step.get("step_type"))
        if step_type not in ALL_STEP_TYPES:
            raise ValueError(_tf("Unsupported flow step type: {step_type}.", {"step_type": step_type}))
        category = _step_category(step_type)
        if category == "source":
            source_count += 1
        elif category == "target":
            target_count += 1

        config = _normalize_step_config(step_type, dict(raw_step.get("config") or {}))
        title = _normalize_step_title(step_type, raw_step.get("title"))
        normalized_steps.append(
            {
                "id": _normalize_step_id(raw_step.get("id")),
                "step_order": index,
                "step_type": step_type,
                "title": title,
                "enabled": _normalize_enabled(raw_step.get("enabled", 1)),
                "config": config,
            }
        )

    if source_count != 1:
        raise ValueError(_t("Flow must contain exactly one source step."))
    if target_count != 1:
        raise ValueError(_t("Flow must contain exactly one target step."))

    first_step = normalized_steps[0]
    last_step = normalized_steps[-1]
    if _step_category(first_step["step_type"]) != "source":
        raise ValueError(_t("First flow step must be a source step."))
    if _step_category(last_step["step_type"]) != "target":
        raise ValueError(_t("Last flow step must be a target step."))
    for middle_step in normalized_steps[1:-1]:
        if _step_category(middle_step["step_type"]) != "filter":
            raise ValueError(_t("All middle flow steps must be filter steps."))
    duplicate_filter_positions = [index for index, step in enumerate(normalized_steps) if step["step_type"] == "filter_dupe"]
    if len(duplicate_filter_positions) > 1:
        raise ValueError(_t("Duplicate filter (viscous-delay) can be used only once in a flow."))
    rate_limit_positions = [index for index, step in enumerate(normalized_steps) if step["step_type"] == "filter_rate_limit"]
    if len(rate_limit_positions) > 1:
        raise ValueError(_t("Rate limit filter can be used only once in a flow."))
    distance_filter_count = sum(1 for step in normalized_steps if step["step_type"] == "filter_distance")
    if distance_filter_count > 1:
        raise ValueError(_t("Distance filter can be used only once in a flow."))
    has_strict_filter = any(step["step_type"] == "filter_strict" for step in normalized_steps[1:-1])
    if target_kind != "tx_aprsis" and has_strict_filter:
        raise ValueError(_t("Strict APRS-IS guard can be used only in APRS-IS target flows."))
    has_rate_limit = any(step["step_type"] == "filter_rate_limit" for step in normalized_steps[1:-1])
    if target_kind != "tx_rf" and has_rate_limit:
        raise ValueError(_t("Rate limit filter can be used only in RF TX target flows."))
    if target_kind == "tx_rf":
        _normalize_tx_rf_flow_step_order(normalized_steps)
    elif duplicate_filter_positions and duplicate_filter_positions[0] != 1:
        raise ValueError(_t("Duplicate filter (viscous-delay) must be the first filter step in the flow."))
    if target_kind == "tx_aprsis":
        if source_kind not in APRSIS_ALLOWED_SOURCE_KINDS:
            raise ValueError(_t("APRS-IS target flow must use Receiver RF or Local TX as source."))
        disallowed_filter_steps = [step for step in normalized_steps[1:-1] if step["step_type"] != "filter_strict"]
        if disallowed_filter_steps:
            raise ValueError(_t("APRS-IS target flow cannot include user-defined filters or rules in this step."))
        strict_steps = [step for step in normalized_steps[1:-1] if step["step_type"] == "filter_strict"]
        if len(strict_steps) > 1:
            raise ValueError(_t("APRS-IS target flow can contain only one system Strict APRS-IS guard step."))
        if not strict_steps:
            normalized_steps.insert(
                1,
                {
                    "id": None,
                    "step_order": 0,
                    "step_type": "filter_strict",
                    "title": _default_step_title("filter_strict"),
                    "enabled": 1,
                    "config": {},
                },
            )
        strict_step = next(step for step in normalized_steps[1:-1] if step["step_type"] == "filter_strict")
        strict_step["enabled"] = 1
        strict_step["config"] = {}
        strict_index = normalized_steps.index(strict_step)
        if strict_index != 1:
            normalized_steps.pop(strict_index)
            normalized_steps.insert(1, strict_step)
        _reindex_steps(normalized_steps)
    first_ref = _step_ref_value(first_step["step_type"], first_step["config"])
    last_ref = _step_ref_value(last_step["step_type"], last_step["config"])
    if source_kind != first_step["step_type"] or source_ref != first_ref:
        raise ValueError(_t("Flow source must match the first step type and reference."))
    if target_kind != last_step["step_type"] or target_ref != last_ref:
        raise ValueError(_t("Flow target must match the last step type and reference."))
    if _flow_requires_path_rule(target_kind) and not _has_enabled_path_rule(normalized_steps):
        raise ValueError(_t("Flow with an RF TX target must include at least one enabled Path rule and DIGI guard step."))

    return {
        "name": name,
        "description": description,
        "source_kind": source_kind,
        "source_ref": source_ref,
        "target_kind": target_kind,
        "target_ref": target_ref,
        "enabled": _normalize_enabled(payload.get("enabled", 0)),
        "steps": normalized_steps,
    }


def _step_signature(step: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(step.get("step_type") or ""),
        str(step.get("title") or ""),
        json.dumps(step.get("config") or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
    )


def _preserve_existing_step_ids(existing_steps: list[dict[str, Any]], normalized_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    available_by_id = {int(step["id"]): dict(step) for step in existing_steps}
    available_ids = set(available_by_id)
    available_by_signature: dict[tuple[str, str, str], list[int]] = {}
    for step in existing_steps:
        step_id = int(step["id"])
        available_by_signature.setdefault(_step_signature(step), []).append(step_id)

    preserved_steps: list[dict[str, Any]] = []
    for step in normalized_steps:
        normalized_step = dict(step)
        requested_id = _normalize_step_id(normalized_step.get("id"))
        resolved_id: int | None = None
        if requested_id is not None and requested_id in available_ids:
            existing = available_by_id[requested_id]
            if str(existing.get("step_type") or "") == str(normalized_step.get("step_type") or ""):
                resolved_id = requested_id
        if resolved_id is None:
            signature = _step_signature(normalized_step)
            candidates = available_by_signature.get(signature, [])
            while candidates:
                candidate_id = candidates.pop(0)
                if candidate_id in available_ids:
                    resolved_id = candidate_id
                    break
        if resolved_id is not None:
            available_ids.discard(resolved_id)
        normalized_step["id"] = resolved_id
        preserved_steps.append(normalized_step)
    return preserved_steps


def _disable_other_enabled_flows_for_route_pair(
    connection: sqlite3.Connection,
    *,
    source_kind: str,
    source_ref: str,
    target_kind: str,
    target_ref: str,
    keep_flow_id: int,
    updated_at: str,
) -> None:
    connection.execute(
        """
        UPDATE digi_flows
        SET enabled = 0,
            updated_at = ?
        WHERE source_kind = ?
          AND source_ref = ?
          AND target_kind = ?
          AND target_ref = ?
          AND id <> ?
          AND enabled = 1
        """,
        (updated_at, source_kind, source_ref, target_kind, target_ref, keep_flow_id),
    )


def create_digi_flow(payload: dict[str, Any]) -> int:
    normalized = normalize_digi_flow_payload(payload)
    timestamp = utc_now()
    with get_connection() as connection:
        sort_order_row = connection.execute("SELECT COALESCE(MIN(sort_order), 0) - 1 AS next_sort_order FROM digi_flows").fetchone()
        sort_order = int(sort_order_row["next_sort_order"]) if sort_order_row is not None else 0
        cursor = connection.execute(
            """
            INSERT INTO digi_flows (
                name, description, source_kind, source_ref, target_kind, target_ref, enabled, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["name"],
                normalized["description"],
                normalized["source_kind"],
                normalized["source_ref"],
                normalized["target_kind"],
                normalized["target_ref"],
                normalized["enabled"],
                sort_order,
                timestamp,
                timestamp,
            ),
        )
        flow_id = int(cursor.lastrowid)
        for step in normalized["steps"]:
            connection.execute(
                """
                INSERT INTO digi_flow_steps (
                    flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    flow_id,
                    step["step_order"],
                    step["step_type"],
                    step["title"],
                    step["enabled"],
                    json.dumps(step["config"], separators=(",", ":"), ensure_ascii=True),
                    timestamp,
                    timestamp,
                ),
            )
        if int(normalized["enabled"]) == 1:
            _disable_other_enabled_flows_for_route_pair(
                connection,
                source_kind=str(normalized["source_kind"]),
                source_ref=str(normalized["source_ref"]),
                target_kind=str(normalized["target_kind"]),
                target_ref=str(normalized["target_ref"]),
                keep_flow_id=flow_id,
                updated_at=timestamp,
            )
    log_event("INFO", "config", f"Created DIGI Flow #{flow_id}")
    return flow_id


def update_digi_flow(flow_id: int, payload: dict[str, Any]) -> None:
    if get_digi_flow(flow_id) is None:
        raise ValueError(_t("DIGI Flow not found."))
    normalized = normalize_digi_flow_payload(payload, existing_flow_id=flow_id)
    existing_steps = get_digi_flow_steps(flow_id)
    normalized["steps"] = _preserve_existing_step_ids(existing_steps, list(normalized["steps"]))
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE digi_flows
            SET name = ?,
                description = ?,
                source_kind = ?,
                source_ref = ?,
                target_kind = ?,
                target_ref = ?,
                enabled = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                normalized["name"],
                normalized["description"],
                normalized["source_kind"],
                normalized["source_ref"],
                normalized["target_kind"],
                normalized["target_ref"],
                normalized["enabled"],
                timestamp,
                flow_id,
            ),
        )
        connection.execute(
            """
            UPDATE digi_flow_steps
            SET step_order = -id,
                updated_at = ?
            WHERE flow_id = ?
            """,
            (timestamp, flow_id),
        )
        retained_step_ids: set[int] = set()
        for step in normalized["steps"]:
            step_id = _normalize_step_id(step.get("id"))
            config_json = json.dumps(step["config"], separators=(",", ":"), ensure_ascii=True)
            if step_id is not None:
                connection.execute(
                    """
                    UPDATE digi_flow_steps
                    SET step_order = ?,
                        step_type = ?,
                        title = ?,
                        enabled = ?,
                        config_json = ?,
                        updated_at = ?
                    WHERE id = ?
                      AND flow_id = ?
                    """,
                    (
                        step["step_order"],
                        step["step_type"],
                        step["title"],
                        step["enabled"],
                        config_json,
                        timestamp,
                        step_id,
                        flow_id,
                    ),
                )
                retained_step_ids.add(step_id)
                continue
            cursor = connection.execute(
                """
                INSERT INTO digi_flow_steps (
                    flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    flow_id,
                    step["step_order"],
                    step["step_type"],
                    step["title"],
                    step["enabled"],
                    config_json,
                    timestamp,
                    timestamp,
                ),
            )
            retained_step_ids.add(int(cursor.lastrowid))
        stale_step_ids = [int(step["id"]) for step in existing_steps if int(step["id"]) not in retained_step_ids]
        if stale_step_ids:
            placeholders = ", ".join("?" for _ in stale_step_ids)
            connection.execute(
                f"DELETE FROM digi_flow_steps WHERE flow_id = ? AND id IN ({placeholders})",
                (flow_id, *stale_step_ids),
            )
        if int(normalized["enabled"]) == 1:
            _disable_other_enabled_flows_for_route_pair(
                connection,
                source_kind=str(normalized["source_kind"]),
                source_ref=str(normalized["source_ref"]),
                target_kind=str(normalized["target_kind"]),
                target_ref=str(normalized["target_ref"]),
                keep_flow_id=flow_id,
                updated_at=timestamp,
            )
    log_event("INFO", "config", f"Updated DIGI Flow #{flow_id}")


def delete_digi_flow(flow_id: int) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM digi_flows WHERE id = ?", (flow_id,))
    log_event("INFO", "config", f"Deleted DIGI Flow #{flow_id}")


def set_digi_flow_enabled(flow_id: int, enabled: bool) -> None:
    timestamp = utc_now()
    if enabled:
        flow = get_digi_flow(flow_id)
        if flow is None:
            raise ValueError(_t("DIGI Flow not found."))
        source_kind = str(flow.get("source_kind") or "")
        target_kind = str(flow.get("target_kind") or "")
        flow_steps = list(flow.get("steps") or [])
        if source_kind == LOCAL_TX_SOURCE_KIND and target_kind not in LOCAL_TX_ALLOWED_TARGET_KINDS:
            raise ValueError(_t("Local TX source can target only APRS-IS uplink or Black Hole."))
        if _flow_requires_path_rule(target_kind) and not _has_enabled_path_rule(flow_steps):
            raise ValueError(_t("DIGI Flow with an RF TX target cannot be enabled without an enabled Path rule and DIGI guard step."))
        if target_kind == "tx_aprsis" and source_kind not in APRSIS_ALLOWED_SOURCE_KINDS:
            raise ValueError(_t("APRS-IS target flow must use Receiver RF or Local TX as source."))
        if target_kind == "tx_aprsis" and not _has_enabled_aprsis_strict_guard(flow_steps):
            raise ValueError(_t("DIGI Flow with an APRS-IS target cannot be enabled without a mandatory enabled Strict APRS-IS guard step."))
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE digi_flows
                SET enabled = 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (timestamp, flow_id),
            )
            _disable_other_enabled_flows_for_route_pair(
                connection,
                source_kind=source_kind,
                source_ref=str(flow.get("source_ref") or ""),
                target_kind=target_kind,
                target_ref=str(flow.get("target_ref") or ""),
                keep_flow_id=flow_id,
                updated_at=timestamp,
            )
    else:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE digi_flows
                SET enabled = 0,
                    updated_at = ?
                WHERE id = ?
                """,
                (timestamp, flow_id),
            )
    log_event("INFO", "config", f"Set DIGI Flow #{flow_id} enabled={1 if enabled else 0}")


def safe_create_digi_flow(payload: dict[str, Any]) -> tuple[int | None, str | None]:
    try:
        return create_digi_flow(payload), None
    except ValueError as exc:
        return None, str(exc)
    except sqlite3.IntegrityError as exc:
        message = str(exc).strip()
        return None, _tf("Failed to save DIGI Flow: {message}.", {"message": message or _t("database integrity error")})


def safe_update_digi_flow(flow_id: int, payload: dict[str, Any]) -> str | None:
    try:
        update_digi_flow(flow_id, payload)
    except ValueError as exc:
        return str(exc)
    except sqlite3.IntegrityError as exc:
        message = str(exc).strip()
        return _tf("Failed to update DIGI Flow: {message}.", {"message": message or _t("database integrity error")})
    return None


def move_digi_flow(flow_id: int, direction: str) -> None:
    normalized_direction = _normalize_text(direction).lower()
    if normalized_direction not in {"up", "down"}:
        raise ValueError(_t("Invalid move direction."))
    with get_connection() as connection:
        rows = connection.execute(f"SELECT id FROM digi_flows ORDER BY {FLOW_LIST_ORDER_BY}").fetchall()
        ordered_ids = [int(row["id"]) for row in rows]
        if not ordered_ids:
            raise ValueError(_t("DIGI Flow not found."))
        if flow_id not in ordered_ids:
            raise ValueError(_t("DIGI Flow not found."))
        index = ordered_ids.index(flow_id)
        swap_index = index - 1 if normalized_direction == "up" else index + 1
        if swap_index < 0 or swap_index >= len(ordered_ids):
            return
        ordered_ids[index], ordered_ids[swap_index] = ordered_ids[swap_index], ordered_ids[index]
        for sort_order, current_flow_id in enumerate(ordered_ids, start=1):
            connection.execute(
                """
                UPDATE digi_flows
                SET sort_order = ?
                WHERE id = ?
                """,
                (sort_order, current_flow_id),
            )
    log_event("INFO", "config", f"Moved DIGI Flow #{flow_id} {normalized_direction}")


def safe_move_digi_flow(flow_id: int, direction: str) -> str | None:
    try:
        move_digi_flow(flow_id, direction)
    except ValueError as exc:
        return str(exc)
    return None


def log_digi_flow_event(
    *,
    frame_uid: str,
    flow_id: int,
    step_id: int | None,
    event_type: str,
    message: str,
    decision: str | None = None,
    created_at: str | None = None,
) -> None:
    timestamp = created_at or utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO digi_flow_event_log(frame_uid, flow_id, step_id, event_type, decision, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (frame_uid, flow_id, step_id, event_type, decision, message, timestamp),
        )
        if event_type == "pipeline_finished":
            _prune_digi_flow_event_log(connection, flow_id=flow_id)


def _prune_digi_flow_event_log(
    connection: sqlite3.Connection,
    *,
    flow_id: int,
    keep_execution_limit: int | None = None,
) -> None:
    if keep_execution_limit is None:
        keep_execution_limit = DIGI_FLOW_EXECUTION_RETENTION_LIMIT
    if keep_execution_limit < 1:
        return
    connection.execute(
        """
        DELETE FROM digi_flow_event_log
        WHERE flow_id = ?
          AND frame_uid NOT IN (
              SELECT frame_uid
              FROM (
                  SELECT frame_uid, MAX(id) AS latest_event_id
                  FROM digi_flow_event_log
                  WHERE flow_id = ?
                  GROUP BY frame_uid
                  ORDER BY latest_event_id DESC
                  LIMIT ?
              )
          )
        """,
        (flow_id, flow_id, keep_execution_limit),
    )


def get_digi_flow_event_log(flow_id: int, *, limit: int = 200) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT
            l.id,
            l.frame_uid,
            l.flow_id,
            l.step_id,
            l.event_type,
            l.decision,
            l.message,
            l.created_at,
            f.name AS flow_name,
            f.source_kind,
            f.source_ref,
            s.title AS step_title,
            s.step_type
        FROM digi_flow_event_log l
        JOIN digi_flows f ON f.id = l.flow_id
        LEFT JOIN digi_flow_steps s ON s.id = l.step_id
        WHERE l.flow_id = ?
        ORDER BY l.created_at DESC, l.id DESC
        LIMIT ?
        """,
        (flow_id, limit),
    )
    return [dict(row) for row in rows]


def get_digi_flow_execution_summaries(flow_id: int, *, execution_limit: int = 20, event_limit: int = 600) -> list[dict[str, Any]]:
    flow = get_digi_flow(flow_id)
    if flow is None:
        return []

    events = get_digi_flow_event_log(flow_id, limit=event_limit)
    if not events:
        return []

    grouped: list[dict[str, Any]] = []
    grouped_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for row in events:
        key = (str(row["frame_uid"]), int(row["flow_id"]))
        if key not in grouped_by_key:
            grouped_by_key[key] = {"frame_uid": key[0], "flow_id": key[1], "events": []}
            grouped.append(grouped_by_key[key])
        grouped_by_key[key]["events"].append(dict(row))

    summaries: list[dict[str, Any]] = []
    for group in grouped[:execution_limit]:
        summary = _build_execution_summary(flow, list(group["events"]))
        if summary is not None:
            summaries.append(summary)
    return summaries


def _build_execution_summary(flow: dict[str, Any], events_desc: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not events_desc:
        return None

    events = sorted(events_desc, key=lambda item: (str(item["created_at"]), int(item["id"])))
    steps = [dict(step) for step in flow.get("steps") or []]
    step_state_by_id: dict[int, dict[str, Any]] = {}
    for index, step in enumerate(steps, start=1):
        step_id = int(step["id"])
        step_state_by_id[step_id] = {
            "step_id": step_id,
            "number": index,
            "title": str(step.get("title") or step.get("step_label") or step.get("step_type") or f"Step {index}"),
            "step_type": str(step.get("step_type") or ""),
            "status": "not_reached",
            "description": _t("Step not reached."),
        }

    raw_packet = ""
    processed_packet = ""
    source_display = ""
    final_decision = ""
    final_message = ""
    output_action_decision = ""
    unresolved_step_reference = False
    for event in events:
        source_display = f"{event.get('source_kind') or ''}:{event.get('source_ref') or ''}".strip(":") or source_display
        if not raw_packet:
            raw_packet = _extract_line_from_message(str(event.get("message") or ""))
        line_value = _extract_line_from_message(str(event.get("message") or ""))
        if line_value:
            processed_packet = line_value
        event_type = str(event.get("event_type") or "")
        decision = str(event.get("decision") or "")
        message = str(event.get("message") or "").strip()
        step_id = event.get("step_id")
        if step_id not in {None, ""} and int(step_id) not in step_state_by_id:
            unresolved_step_reference = True

        step_state = _resolve_execution_step_state(flow=flow, steps=steps, step_state_by_id=step_state_by_id, step_id=step_id, event=event)
        if step_state is not None:
            if event_type == "source_step":
                step_state["status"] = "passed"
                step_state["description"] = _t("Source matched and packet entered the flow.")
            elif event_type in {
                "filter_callsign",
                "filter_digi",
                "filter_dupe",
                "filter_rate_limit",
                "direct_only",
                "path_rule",
                "strict_filter",
                "filter_packet_type",
                "filter_icon",
                "filter_distance",
            }:
                step_state["status"] = "rejected" if decision == "rejected" else "passed"
                step_state["description"] = message
            elif event_type == "output_action":
                step_state["status"] = "executed"
                step_state["description"] = _strip_line_suffix(message)
                output_action_decision = decision or output_action_decision
            elif event_type == "step_stub":
                step_state["status"] = "executed"
                step_state["description"] = message
            elif event_type == "step_skipped":
                step_state["status"] = "not_reached"
                step_state["description"] = _t("Step disabled.")

        if event_type == "pipeline_finished":
            final_decision = decision
            final_message = message

    final_result = _execution_final_result(final_decision=final_decision, output_action_decision=output_action_decision, steps=step_state_by_id)
    final_step = _execution_final_step(step_state_by_id, final_result=final_result)
    timestamp = str(events[0].get("created_at") or "")
    flow_changed_after_execution = _execution_predates_flow_update(timestamp, str(flow.get("updated_at") or ""))
    layout_changed = flow_changed_after_execution and (
        unresolved_step_reference or _execution_has_reached_gap(step_state_by_id)
    )
    return {
        "frame_uid": str(events[0]["frame_uid"]),
        "flow_id": int(flow["id"]),
        "flow_name": str(flow.get("name") or ""),
        "created_at": timestamp,
        "display_created_at": _format_execution_time_utc(timestamp),
        "final_result": final_result,
        "final_message": final_message,
        "final_step_number": final_step.get("number"),
        "final_step_title": final_step.get("title"),
        "raw_packet": raw_packet or "-",
        "processed_packet": processed_packet or raw_packet or "-",
        "source_display": source_display or "-",
        "layout_changed": layout_changed,
        "layout_note": (
            _t("This packet was processed before the current flow layout was saved. Historical step mapping may be partial.")
            if layout_changed
            else ""
        ),
        "step_count": len(steps),
        "step_path": " -> ".join(str(index) for index in range(1, len(steps) + 1)),
        "steps": [step_state_by_id[int(step["id"])] for step in steps],
    }


def _execution_final_result(
    *,
    final_decision: str,
    output_action_decision: str,
    steps: dict[int, dict[str, Any]],
) -> str:
    if final_decision == "log_only" or output_action_decision == "log_only":
        return "LOGGED"
    if final_decision == "tx" or output_action_decision == "tx":
        return "TX"
    if output_action_decision == "drop":
        return "DROPPED"
    if final_decision == "drop" or any(step["status"] == "rejected" for step in steps.values()):
        return "REJECTED"
    return "RUNNING"


def _execution_final_step(steps: dict[int, dict[str, Any]], *, final_result: str) -> dict[str, Any]:
    reached_steps = [step for step in steps.values() if step["status"] != "not_reached"]
    if not reached_steps:
        return {}
    reached_steps.sort(key=lambda item: int(item["number"]))
    if final_result in {"REJECTED", "DROPPED", "LOGGED", "TX"}:
        return reached_steps[-1]
    return reached_steps[-1]


def _resolve_execution_step_state(
    *,
    flow: dict[str, Any],
    steps: list[dict[str, Any]],
    step_state_by_id: dict[int, dict[str, Any]],
    step_id: Any,
    event: dict[str, Any],
) -> dict[str, Any] | None:
    if step_id not in {None, ""}:
        resolved = step_state_by_id.get(int(step_id))
        if resolved is not None:
            return resolved

    hinted_step_type = _execution_event_step_type(flow=flow, event=event)
    if not hinted_step_type:
        return None

    matching_states = [
        step_state_by_id[int(step["id"])]
        for step in steps
        if str(step.get("step_type") or "") == hinted_step_type
    ]
    if not matching_states:
        return None

    unreached = next((state for state in matching_states if state["status"] == "not_reached"), None)
    return unreached or matching_states[-1]


def _execution_event_step_type(*, flow: dict[str, Any], event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or "")
    if event_type == "source_step":
        return str(flow.get("source_kind") or "")
    if event_type == "filter_callsign":
        return "filter_callsign"
    if event_type == "filter_dupe":
        return "filter_dupe"
    if event_type == "filter_rate_limit":
        return "filter_rate_limit"
    if event_type == "path_rule":
        return "filter_path"
    if event_type == "strict_filter":
        return "filter_strict"
    if event_type == "filter_packet_type":
        return "filter_packet_type"
    if event_type == "filter_icon":
        return "filter_icon"
    if event_type == "filter_distance":
        return "filter_distance"
    if event_type == "output_action":
        return str(flow.get("target_kind") or "")
    if event_type == "step_stub":
        message = str(event.get("message") or "").strip()
        marker = "Step type "
        if marker in message:
            step_type = message.split(marker, 1)[1].split(" ", 1)[0].strip().rstrip(".")
            return step_type
    return ""


def _extract_line_from_message(message: str) -> str:
    marker = "| line="
    if marker in message:
        return message.split(marker, 1)[1].strip()
    line_marker = "line="
    if line_marker in message:
        return message.split(line_marker, 1)[1].strip()
    return ""


def _strip_line_suffix(message: str) -> str:
    marker = " | line="
    if marker in message:
        return message.split(marker, 1)[0].strip()
    return message.strip()


def _format_execution_time_utc(value: str) -> str:
    if not value:
        return "-"
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).strftime("%Y.%m.%d %H:%M UTC")


def _execution_predates_flow_update(execution_created_at: str, flow_updated_at: str) -> bool:
    if not execution_created_at or not flow_updated_at:
        return False
    try:
        execution_ts = datetime.fromisoformat(execution_created_at.replace("Z", "+00:00"))
        flow_ts = datetime.fromisoformat(flow_updated_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if execution_ts.tzinfo is None:
        execution_ts = execution_ts.replace(tzinfo=timezone.utc)
    else:
        execution_ts = execution_ts.astimezone(timezone.utc)
    if flow_ts.tzinfo is None:
        flow_ts = flow_ts.replace(tzinfo=timezone.utc)
    else:
        flow_ts = flow_ts.astimezone(timezone.utc)
    return execution_ts <= flow_ts


def _execution_has_reached_gap(steps: dict[int, dict[str, Any]]) -> bool:
    ordered_steps = sorted(steps.values(), key=lambda item: int(item["number"]))
    for index, step in enumerate(ordered_steps):
        if step["status"] != "not_reached":
            continue
        if any(candidate["status"] != "not_reached" for candidate in ordered_steps[index + 1 :]):
            return True
    return False
