from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
from datetime import datetime, timezone
from typing import Any


_APRS_MESSAGE_ID_RE = re.compile(r"^[A-Za-z0-9]{1,5}$", re.ASCII)
_ALERT_PART_RE = re.compile(r"^(?P<number>[1-9][0-9]*)/(?P<total>[1-9][0-9]*)$", re.ASCII)
_SEVERITY_SUFFIX_RE = re.compile(r"(?P<severity>[0-9]+)$", re.ASCII)
_APRS_EXPIRY_RE = re.compile(
    r"^(?P<day>0[1-9]|[12][0-9]|3[01])"
    r"(?P<hour>[01][0-9]|2[0-3])"
    r"(?P<minute>[0-5][0-9])z$",
    re.IGNORECASE | re.ASCII,
)
_CAWF_ALERT_ID_RE = re.compile(r"^[A-F0-9]{4}$", re.ASCII)
_CAWF_MESSAGE_ID_RE = re.compile(r"^[A-F0-9]{5}$", re.ASCII)
_CAWF_EVENT_CODE_RE = re.compile(r"^[A-Z][A-Z0-9-]{1,15}$", re.ASCII)
_CAWF_AREA_CODE_RE = re.compile(r"^[A-Z0-9-]{1,8}$", re.ASCII)
_CAWF_AREA_PREFIX_RE = re.compile(r"^(?P<area>[A-Z0-9-]{1,8})(?:\s+|$)", re.ASCII)

CAWF_MAX_MESSAGE_LENGTH = 67
CAWF_MAX_PARTS = 9
CAWF_COMMENT_SEPARATOR = "|"
CAWF_CANCEL_EVENT_CODE = "CANCEL"
CAWF_EVENT_FAMILIES: tuple[tuple[str, str], ...] = (
    ("TSTORM", "Thunderstorm"),
    ("WIND", "Wind / gale"),
    ("RAIN", "Rain"),
    ("FLOOD", "Flood / surge"),
    ("FFLOOD", "Flash flood"),
    ("SNOW", "Snow / blizzard"),
    ("ICE", "Ice"),
    ("HEAT", "Heat"),
    ("COLD", "Cold / frost / ice"),
    ("FOG", "Fog / mist"),
    ("COASTAL", "Coastal hazard"),
    ("AVALANC", "Avalanche"),
    ("FIRE", "Wildfire / fire"),
    ("DUST", "Dust / sand"),
    ("OTHER", "Other / unknown"),
)


def format_aprs_expiry(value: datetime) -> str:
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).strftime("%d%H%Mz")


def generate_cawf_alert_id() -> str:
    return secrets.token_hex(2).upper()


def generate_cawf_message_id() -> str:
    return secrets.token_hex(3).upper()[:5]


def normalize_cawf_comment(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = " ".join(text.split())
    return text.replace(CAWF_COMMENT_SEPARATOR, "/").replace("{", "(")


def _validate_cawf_generation_fields(
    *,
    expiry: Any,
    event_code: Any,
    alert_id: Any,
    area_code: Any,
) -> tuple[str, str, str, str]:
    normalized_expiry = str(expiry or "").strip()
    normalized_event = str(event_code or "").strip().upper()
    normalized_alert_id = str(alert_id or "").strip().upper().removeprefix("@")
    normalized_area = str(area_code or "").strip().upper()
    if _APRS_EXPIRY_RE.fullmatch(normalized_expiry) is None:
        raise ValueError("Invalid CAWF expiry.")
    if _CAWF_EVENT_CODE_RE.fullmatch(normalized_event) is None:
        raise ValueError("Invalid CAWF event code.")
    if _CAWF_ALERT_ID_RE.fullmatch(normalized_alert_id) is None:
        raise ValueError("Invalid CAWF alert ID.")
    if _CAWF_AREA_CODE_RE.fullmatch(normalized_area) is None:
        raise ValueError("Invalid CAWF area code.")
    return normalized_expiry, normalized_event, normalized_alert_id, normalized_area


def _cawf_part_prefix(
    *,
    expiry: str,
    event_code: str,
    alert_id: str,
    part_number: int,
    parts_total: int,
    area_code: str,
) -> str:
    return (
        f"{expiry},{event_code},@{alert_id},"
        f"{part_number}/{parts_total},{area_code}"
    )


def _comment_capacities(
    *,
    expiry: str,
    event_code: str,
    alert_id: str,
    area_code: str,
    parts_total: int,
) -> list[int]:
    capacities: list[int] = []
    for part_number in range(1, parts_total + 1):
        prefix = _cawf_part_prefix(
            expiry=expiry,
            event_code=event_code,
            alert_id=alert_id,
            part_number=part_number,
            parts_total=parts_total,
            area_code=area_code,
        )
        capacities.append(
            CAWF_MAX_MESSAGE_LENGTH
            - len(prefix)
            - len(CAWF_COMMENT_SEPARATOR)
            - 1
            - 5
        )
    return capacities


def cawf_comment_capacity(
    *,
    expiry: Any,
    event_code: Any,
    alert_id: Any,
    area_code: Any,
) -> int:
    normalized = _validate_cawf_generation_fields(
        expiry=expiry,
        event_code=event_code,
        alert_id=alert_id,
        area_code=area_code,
    )
    return sum(
        max(0, capacity)
        for capacity in _comment_capacities(
            expiry=normalized[0],
            event_code=normalized[1],
            alert_id=normalized[2],
            area_code=normalized[3],
            parts_total=CAWF_MAX_PARTS,
        )
    )


def generate_aprs_group_warning_parts(
    *,
    expiry: Any,
    event_code: Any,
    alert_id: Any,
    area_code: Any,
    comment: Any = "",
    message_ids: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Generate all CAWF fragments using the receiver's canonical envelope."""

    normalized_expiry, normalized_event, normalized_alert_id, normalized_area = (
        _validate_cawf_generation_fields(
            expiry=expiry,
            event_code=event_code,
            alert_id=alert_id,
            area_code=area_code,
        )
    )
    normalized_comment = normalize_cawf_comment(comment)
    parts_total = 1
    if normalized_comment:
        for candidate_total in range(1, CAWF_MAX_PARTS + 1):
            capacities = _comment_capacities(
                expiry=normalized_expiry,
                event_code=normalized_event,
                alert_id=normalized_alert_id,
                area_code=normalized_area,
                parts_total=candidate_total,
            )
            if all(capacity > 0 for capacity in capacities) and sum(capacities) >= len(normalized_comment):
                parts_total = candidate_total
                break
        else:
            raise ValueError(
                f"CAWF comment exceeds the {CAWF_MAX_PARTS}-part protocol limit."
            )

    if message_ids is None:
        normalized_message_ids = []
        seen_message_ids: set[str] = set()
        while len(normalized_message_ids) < parts_total:
            candidate = generate_cawf_message_id()
            if candidate in seen_message_ids:
                continue
            seen_message_ids.add(candidate)
            normalized_message_ids.append(candidate)
    else:
        normalized_message_ids = [str(value or "").strip().upper() for value in message_ids]
        if len(normalized_message_ids) != parts_total:
            raise ValueError("CAWF message ID count does not match the fragment count.")
        if any(_CAWF_MESSAGE_ID_RE.fullmatch(value) is None for value in normalized_message_ids):
            raise ValueError("Invalid CAWF message ID.")

    capacities = _comment_capacities(
        expiry=normalized_expiry,
        event_code=normalized_event,
        alert_id=normalized_alert_id,
        area_code=normalized_area,
        parts_total=parts_total,
    )
    offset = 0
    result: list[dict[str, Any]] = []
    for index, capacity in enumerate(capacities, start=1):
        comment_fragment = normalized_comment[offset : offset + capacity]
        offset += len(comment_fragment)
        prefix = _cawf_part_prefix(
            expiry=normalized_expiry,
            event_code=normalized_event,
            alert_id=normalized_alert_id,
            part_number=index,
            parts_total=parts_total,
            area_code=normalized_area,
        )
        payload = prefix
        if normalized_comment:
            payload = f"{payload}{CAWF_COMMENT_SEPARATOR}{comment_fragment}"
        payload = f"{payload}{{{normalized_message_ids[index - 1]}"
        if len(payload) > CAWF_MAX_MESSAGE_LENGTH:
            raise ValueError("Generated CAWF fragment exceeds the APRS message limit.")
        result.append(
            {
                "part_number": index,
                "parts_total": parts_total,
                "message_id": normalized_message_ids[index - 1],
                "comment_fragment": comment_fragment,
                "payload": payload,
                "length": len(payload),
            }
        )
    return result


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


def _reference_datetime_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        reference = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        if text.endswith(("Z", "z")):
            text = f"{text[:-1]}+00:00"
        try:
            reference = datetime.fromisoformat(text)
        except ValueError:
            return None
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return reference.astimezone(timezone.utc)


def _shift_year_month(year: int, month: int, offset: int) -> tuple[int, int]:
    absolute_month = (year * 12) + (month - 1) + offset
    shifted_year, shifted_month_zero_based = divmod(absolute_month, 12)
    return shifted_year, shifted_month_zero_based + 1


def resolve_aprs_expiry_utc(
    expiry: Any,
    received_at: Any,
) -> datetime | None:
    """Resolve ``DDHHMMz`` to the closest valid UTC date around reception."""

    match = _APRS_EXPIRY_RE.fullmatch(str(expiry or "").strip())
    reference = _reference_datetime_utc(received_at)
    if match is None or reference is None:
        return None

    day = int(match.group("day"))
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    candidates: list[datetime] = []
    for month_offset in range(-2, 3):
        year, month = _shift_year_month(
            reference.year,
            reference.month,
            month_offset,
        )
        try:
            candidates.append(
                datetime(
                    year,
                    month,
                    day,
                    hour,
                    minute,
                    tzinfo=timezone.utc,
                )
            )
        except ValueError:
            continue
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda candidate: (
            abs((candidate - reference).total_seconds()),
            0 if candidate >= reference else 1,
            candidate,
        ),
    )


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

    envelope, separator, comment = content_without_message_id.partition(
        CAWF_COMMENT_SEPARATOR
    )
    fields = [field.strip() for field in envelope.split(",")]
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
    area_codes: list[str] = []
    legacy_comment_parts: list[str] = []
    legacy_comment_started = False
    for raw_area in fields[area_field_offset:]:
        candidate = str(raw_area or "").strip()
        if not legacy_comment_started and _CAWF_AREA_CODE_RE.fullmatch(candidate):
            area_codes.extend(normalize_warning_area_codes(candidate))
            continue
        prefix_match = (
            _CAWF_AREA_PREFIX_RE.match(candidate)
            if not legacy_comment_started
            else None
        )
        prefix_area = prefix_match.group("area") if prefix_match is not None else ""
        prefix_remainder = (
            candidate[prefix_match.end() :].strip()
            if prefix_match is not None
            else ""
        )
        # Current territorial profiles use numeric county/zone identifiers.
        # Only treat a whitespace suffix as a legacy comment after such an
        # identifier; otherwise a normal comment like "LOUD TEXT" would
        # incorrectly become an additional area.
        if prefix_match is not None and (
            not prefix_remainder or prefix_area.isdigit()
        ):
            area_codes.extend(normalize_warning_area_codes(prefix_area))
            if prefix_remainder:
                legacy_comment_parts.append(prefix_remainder)
                legacy_comment_started = True
        elif candidate:
            legacy_comment_parts.append(candidate)
            legacy_comment_started = True
    area_codes = normalize_warning_area_codes(area_codes)
    severity_match = _SEVERITY_SUFFIX_RE.search(event_code)
    result = {
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
    if separator:
        result["comment"] = comment
    elif legacy_comment_parts:
        result["comment"] = ",".join(legacy_comment_parts)
    if event_code.strip().upper() == CAWF_CANCEL_EVENT_CODE:
        result["is_cancel"] = True
    return result


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
