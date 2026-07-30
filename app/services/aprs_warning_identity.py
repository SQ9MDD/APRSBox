from __future__ import annotations

import hashlib
import json
import re
from typing import Any


_APRS_MESSAGE_ID_RE = re.compile(r"^[A-Za-z0-9]{1,5}$", re.ASCII)


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
    area_codes = normalize_warning_area_codes(fields[2:] if len(fields) > 2 else [])
    return {
        "expiry": expiry,
        "event_code": event_code,
        "area_code": area_codes[0] if area_codes else "",
        "area_codes": area_codes,
        "message_id": message_id,
    }


def build_aprs_alert_identity_key(
    *,
    source_callsign: Any,
    alarm_group: Any = None,
    message_id: Any = None,
    raw_content: Any = "",
) -> str:
    source = str(source_callsign or "").strip().upper()
    group = str(alarm_group or "").strip().upper()
    normalized_message_id = str(message_id or "").strip()
    if group:
        if normalized_message_id:
            parts = ["aprs-group-message", source, group, normalized_message_id]
        else:
            content_digest = hashlib.sha256(
                str(raw_content or "").encode("utf-8", errors="replace")
            ).hexdigest()
            parts = ["aprs-group-content", source, group, content_digest]
    else:
        parts = ["aprs-emergency", source]
    return json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
