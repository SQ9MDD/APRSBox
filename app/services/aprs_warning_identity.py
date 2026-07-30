from __future__ import annotations

import hashlib
import json
import re
from typing import Any


_APRS_MESSAGE_ID_RE = re.compile(r"^[A-Za-z0-9]{1,5}$", re.ASCII)
_ALERT_PART_RE = re.compile(r"^(?P<number>[1-9][0-9]*)/(?P<total>[1-9][0-9]*)$", re.ASCII)
_SEVERITY_SUFFIX_RE = re.compile(r"(?P<severity>[0-9]+)$", re.ASCII)


def normalize_warning_area_codes(values: Any) -> list[str]:
    if values is None:
        return []
    candidates = values if isinstance(values, (list, tuple, set)) else [values]
    normalized: list[str] = []
    seen: set[str] = set()
    for value in candidates:
        text = str(value).strip()
        if not text:
            continue
        comparison_key = text.casefold()
        if comparison_key in seen:
            continue
        seen.add(comparison_key)
        normalized.append(text)
    return normalized


def parse_aprs_group_warning_content(raw_content: Any) -> dict[str, Any]:
    raw_text = str(raw_content or "")
    content_without_message_id = raw_text
    message_id = ""
    if "{" in raw_text:
        possible_content, possible_message_id = raw_text.rsplit("{", 1)
        candidate = possible_message_id.strip()
        content_without_message_id = possible_content
        if _APRS_MESSAGE_ID_RE.fullmatch(candidate):
            message_id = candidate

    fields = [field.strip() for field in content_without_message_id.split(",")]
    expiry = fields[0] if fields else ""
    event_code = fields[1] if len(fields) > 1 else ""
    logical_alert_id = ""
    part_number: int | None = None
    parts_total: int | None = None
    area_field_offset = 2
    if len(fields) > 3 and fields[2].startswith("@"):
        possible_logical_alert_id = fields[2][1:].strip()
        part_match = _ALERT_PART_RE.fullmatch(fields[3])
        if possible_logical_alert_id and part_match is not None:
            possible_part_number = int(part_match.group("number"))
            possible_parts_total = int(part_match.group("total"))
            if possible_part_number <= possible_parts_total:
                logical_alert_id = possible_logical_alert_id.upper()
                part_number = possible_part_number
                parts_total = possible_parts_total
                area_field_offset = 4
    area_codes = normalize_warning_area_codes(
        fields[area_field_offset:] if len(fields) > area_field_offset else []
    )
    severity_match = _SEVERITY_SUFFIX_RE.search(event_code)
    return {
        "expiry": expiry,
        "event_code": event_code,
        "severity_level": (
            int(severity_match.group("severity"))
            if severity_match is not None
            else None
        ),
        "logical_alert_id": logical_alert_id,
        "part_number": part_number,
        "parts_total": parts_total,
        "area_code": area_codes[0] if area_codes else "",
        "area_codes": area_codes,
        "message_id": message_id,
    }


def build_aprs_alert_identity_key(
    *,
    source_callsign: Any,
    alarm_group: Any = None,
    logical_alert_id: Any = None,
    message_id: Any = None,
    raw_content: Any = "",
) -> str:
    source = str(source_callsign or "").strip().upper()
    group = str(alarm_group or "").strip().upper()
    logical_id = str(logical_alert_id or "").strip().upper().removeprefix("@")
    normalized_message_id = str(message_id or "").strip().upper()
    if group:
        if logical_id:
            parts = ["aprs-group-logical", source, group, logical_id]
        elif normalized_message_id:
            parts = ["aprs-group-message", source, group, normalized_message_id]
        else:
            content_digest = hashlib.sha256(
                str(raw_content or "").encode("utf-8", errors="replace")
            ).hexdigest()
            parts = ["aprs-group-content", source, group, content_digest]
    else:
        parts = ["aprs-emergency", source]
    return json.dumps(parts, ensure_ascii=True, separators=(",", ":"))


def build_aprs_alert_part_identity_key(
    *,
    source_callsign: Any,
    alarm_group: Any,
    message_id: Any = None,
    raw_content: Any = "",
) -> str:
    source = str(source_callsign or "").strip().upper()
    group = str(alarm_group or "").strip().upper()
    normalized_message_id = str(message_id or "").strip().upper()
    if normalized_message_id:
        parts = ["aprs-group-part", source, group, normalized_message_id]
    else:
        content_digest = hashlib.sha256(
            str(raw_content or "").encode("utf-8", errors="replace")
        ).hexdigest()
        parts = ["aprs-group-part-content", source, group, content_digest]
    return json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
