from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from app.db import fetch_one, get_connection, utc_now
from app.services.mqtt_url import TX_CAPABLE_MODEM_TYPES


APRSIS_FLOW_SOURCE_KIND = "receiver_aprsis"
RF_GUARD_STEP_TYPE = "filter_rf_guard"
MESSAGE_DELIVERY_STEP_TYPE = "filter_aprsis_message_delivery"
RF_TX_GUARD_STEP_TYPE = "filter_rf_tx_guard"
ALLOW_RULES_STEP_TYPE = "filter_allow_rules"

RF_GUARD_DEFAULTS: dict[str, int] = {
    "viscous_delay_sec": 5,
    "flow_rate_per_minute": 6,
    "flow_burst": 3,
    "source_rate_per_minute": 2,
    "source_burst": 2,
    "duplicate_window_sec": 30,
}
RF_GUARD_LIMITS: dict[str, tuple[int, int]] = {
    "viscous_delay_sec": (1, 30),
    "flow_rate_per_minute": (1, 60),
    "flow_burst": (1, 20),
    "source_rate_per_minute": (1, 30),
    "source_burst": (1, 10),
    "duplicate_window_sec": (5, 300),
}

DEFAULT_DENY_CONFIG_FIELDS = frozenset({"callsigns", "radius_km"})
DEFAULT_DENY_CALLSIGN_LIMIT = 50
MESSAGE_DELIVERY_DEFAULTS: dict[str, Any] = {
    "rf_sources": [],
    "heard_window_minutes": 60,
    "max_consumed_hops": 0,
}
MESSAGE_DELIVERY_CONFIG_FIELDS = frozenset(MESSAGE_DELIVERY_DEFAULTS)
APRSIS_RF_STAT_COUNTERS = frozenset(
    {
        "received_from_aprsis",
        "matched_message_rule",
        "matched_associated_position",
        "matched_allow_rule",
        "dropped_no_allow_rule",
        "dropped_recipient_not_local",
        "dropped_recipient_seen_internet",
        "dropped_sender_heard_rf",
        "dropped_safety_guard",
        "dropped_duplicate",
        "cancelled_during_viscous_delay",
        "dropped_rate_limit",
        "dropped_oversize",
        "queued_to_rf",
        "transmitted_to_rf",
        "tx_failed",
    }
)

_AX25_ADDRESS_RE = re.compile(r"^[A-Z0-9]{1,6}(?:-(?:[0-9]|1[0-5]))?$")
_Q_TOKEN_RE = re.compile(r"^q[A-Za-z]{2}$")
_KNOWN_Q_CONSTRUCTS = frozenset({"qAC", "qAX", "qAU", "qAo", "qAO", "qAS", "qAr", "qAR", "qAZ", "qAI"})
_UNSAFE_PATH_MARKERS = frozenset({"NOGATE", "RFONLY", "TCPXX"})


def normalize_rf_guard_config(raw_config: Any) -> dict[str, int]:
    config = dict(raw_config) if isinstance(raw_config, dict) else {}
    normalized: dict[str, int] = {}
    for key, default in RF_GUARD_DEFAULTS.items():
        raw_value = config.get(key, default)
        try:
            value = int(str(raw_value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"RF Guard {key} must be an integer.") from exc
        minimum, maximum = RF_GUARD_LIMITS[key]
        if value < minimum or value > maximum:
            raise ValueError(f"RF Guard {key} must be between {minimum} and {maximum}.")
        normalized[key] = value
    return normalized


def normalize_default_deny_config(raw_config: Any) -> dict[str, Any]:
    if raw_config is None or raw_config == "":
        config: dict[str, Any] = {}
    elif isinstance(raw_config, dict):
        config = dict(raw_config)
    else:
        raise ValueError("APRS-IS default-deny filter config must be an object.")

    unknown_fields = {str(key) for key in config} - DEFAULT_DENY_CONFIG_FIELDS
    if unknown_fields:
        unknown = ", ".join(sorted(unknown_fields))
        raise ValueError(f"APRS-IS default-deny filter contains unsupported fields: {unknown}.")

    raw_callsigns = config.get("callsigns")
    if raw_callsigns is None or raw_callsigns == "":
        callsign_values: list[Any] = []
    elif isinstance(raw_callsigns, str):
        callsign_values = raw_callsigns.splitlines()
    elif isinstance(raw_callsigns, (list, tuple)):
        callsign_values = list(raw_callsigns)
    else:
        raise ValueError("APRS-IS default-deny callsigns must be a list or multiline text.")

    callsigns: list[str] = []
    seen: set[str] = set()
    for raw_callsign in callsign_values:
        callsign = str(raw_callsign or "").strip().upper()
        if not callsign or callsign in seen:
            continue
        if not _AX25_ADDRESS_RE.fullmatch(callsign):
            raise ValueError(
                f"APRS-IS default-deny callsign {callsign!r} must be an exact AX.25 callsign with optional SSID 0-15."
            )
        seen.add(callsign)
        callsigns.append(callsign)
    if len(callsigns) > DEFAULT_DENY_CALLSIGN_LIMIT:
        raise ValueError(
            f"APRS-IS default-deny callsigns are limited to {DEFAULT_DENY_CALLSIGN_LIMIT} entries per flow."
        )

    radius_text = str(config.get("radius_km") or "").strip()
    if bool(callsigns) != bool(radius_text):
        raise ValueError("APRS-IS default-deny filter requires both callsigns and radius_km, or neither.")
    if radius_text:
        radius_km = _finite_float(radius_text, label="APRS-IS default-deny radius")
        if radius_km <= 0.0 or radius_km > 1000.0:
            raise ValueError("APRS-IS default-deny radius must be greater than 0 and at most 1000 km.")

    return {
        "callsigns": callsigns,
        "radius_km": radius_text,
    }


def normalize_message_delivery_config(raw_config: Any) -> dict[str, Any]:
    if raw_config is None or raw_config == "":
        config: dict[str, Any] = {}
    elif isinstance(raw_config, dict):
        config = dict(raw_config)
    else:
        raise ValueError("APRS-IS message delivery config must be an object.")

    unknown_fields = {str(key) for key in config} - MESSAGE_DELIVERY_CONFIG_FIELDS
    if unknown_fields:
        unknown = ", ".join(sorted(unknown_fields))
        raise ValueError(f"APRS-IS message delivery config contains unsupported fields: {unknown}.")

    raw_sources = config.get("rf_sources")
    if raw_sources is None or raw_sources == "":
        source_values: list[Any] = []
    elif isinstance(raw_sources, str):
        source_values = raw_sources.splitlines()
    elif isinstance(raw_sources, (list, tuple)):
        source_values = list(raw_sources)
    else:
        raise ValueError("APRS-IS message delivery RF sources must be a list or multiline text.")

    rf_sources: list[str] = []
    seen_sources: set[str] = set()
    for raw_source in source_values:
        source = str(raw_source or "").strip()
        if not source or source in seen_sources:
            continue
        if len(source) > 100 or any(ord(char) < 32 for char in source):
            raise ValueError("APRS-IS message delivery RF source contains invalid characters.")
        seen_sources.add(source)
        rf_sources.append(source)
    if len(rf_sources) > 16:
        raise ValueError("APRS-IS message delivery is limited to 16 RF sources per flow.")

    try:
        heard_window_minutes = int(
            str(config.get("heard_window_minutes", MESSAGE_DELIVERY_DEFAULTS["heard_window_minutes"])).strip()
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("APRS-IS message delivery heard window must be an integer.") from exc
    if heard_window_minutes < 5 or heard_window_minutes > 60:
        raise ValueError("APRS-IS message delivery heard window must be between 5 and 60 minutes.")

    try:
        max_consumed_hops = int(
            str(config.get("max_consumed_hops", MESSAGE_DELIVERY_DEFAULTS["max_consumed_hops"])).strip()
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("APRS-IS message delivery maximum consumed hops must be an integer.") from exc
    if max_consumed_hops < 0 or max_consumed_hops > 2:
        raise ValueError("APRS-IS message delivery maximum consumed hops must be between 0 and 2.")

    return {
        "rf_sources": rf_sources,
        "heard_window_minutes": heard_window_minutes,
        "max_consumed_hops": max_consumed_hops,
    }


def matches_default_deny_filter(
    parsed: dict[str, Any] | None,
    config: dict[str, Any],
    station_settings: dict[str, Any] | None,
) -> bool:
    if not parsed:
        return False
    try:
        normalized = normalize_default_deny_config(config)
    except ValueError:
        return False

    callsigns = set(normalized["callsigns"])
    radius_text = str(normalized["radius_km"] or "").strip()
    if not callsigns or not radius_text:
        return False

    source = str(parsed.get("logical_source_key") or parsed.get("source") or "").strip().upper()
    if source not in callsigns:
        return False

    aprs_data = dict(parsed.get("aprs_data") or {})
    packet_position = _parsed_position(aprs_data)
    station_position = _station_position(station_settings)
    if packet_position is None or station_position is None:
        return False

    distance_km = _distance_km(
        packet_position[0],
        packet_position[1],
        station_position[0],
        station_position[1],
    )
    return distance_km <= float(radius_text)


def logical_packet_hash(parsed: dict[str, Any] | None) -> str:
    if not parsed:
        return ""
    source = str(parsed.get("logical_source_key") or parsed.get("source") or "").strip().upper()
    destination = str(parsed.get("logical_destination") or parsed.get("destination") or "").strip().upper()
    payload = str(parsed.get("logical_info") if parsed.get("logical_info") is not None else parsed.get("info") or "")
    if not source or not destination:
        return ""
    canonical = f"{source}\x1f{destination}\x1f{payload}".encode("latin-1", errors="replace")
    return hashlib.sha256(canonical).hexdigest()


def extract_q_construct(parsed: dict[str, Any] | None) -> str | None:
    if not parsed:
        return None
    tokens = _path_tokens(str(parsed.get("path") or ""), keep_used_marker=False)
    for token in tokens:
        if _Q_TOKEN_RE.fullmatch(token):
            return token
    return None


def aprsis_rf_guard_reject_reason(parsed: dict[str, Any] | None) -> str | None:
    if not parsed:
        return "invalid_aprs"
    source = str(parsed.get("source") or "").strip().upper()
    destination = str(parsed.get("destination") or "").strip().upper()
    aprs_data = dict(parsed.get("aprs_data") or {})
    if not _AX25_ADDRESS_RE.fullmatch(source) or not _AX25_ADDRESS_RE.fullmatch(destination) or not aprs_data:
        return "invalid_aprs"

    if bool(parsed.get("is_third_party")):
        inner_info = str(aprs_data.get("inner_info") or "")
        if inner_info.startswith("}"):
            return "recursive_third_party"
        if not bool(parsed.get("third_party_inner_valid")):
            return "invalid_third_party"
        # A packet already wrapped for RF must never be wrapped and gated a
        # second time.  Correct APRS-IS-to-RF input is the original packet.
        return "invalid_third_party"

    raw_tokens = _path_tokens(str(parsed.get("path") or ""), keep_used_marker=True)
    normalized_tokens = [token.rstrip("*").upper() for token in raw_tokens]
    for marker in _UNSAFE_PATH_MARKERS:
        if marker in normalized_tokens:
            return {
                "NOGATE": "blocked_nogate",
                "RFONLY": "blocked_rfonly",
                "TCPXX": "blocked_tcpxx",
            }[marker]

    q_indexes: list[int] = []
    for index, token in enumerate(raw_tokens):
        bare = token.rstrip("*")
        if not _Q_TOKEN_RE.fullmatch(bare):
            if bare.casefold().startswith("q") and len(bare) == 3:
                return "invalid_q_construct"
            continue
        if bare not in _KNOWN_Q_CONSTRUCTS or bare == "qAZ" or token.endswith("*"):
            return "invalid_q_construct"
        q_indexes.append(index)
    if len(q_indexes) > 1:
        return "invalid_q_construct"
    if q_indexes:
        q_index = q_indexes[0]
        if q_index >= len(raw_tokens) - 1:
            return "invalid_q_construct"
        if raw_tokens[q_index] == "qAC":
            before_q = [token.upper() for token in raw_tokens[:q_index]]
            if before_q != ["TCPIP*"]:
                return "invalid_q_construct"
        for token in raw_tokens[q_index + 1 :]:
            if not token or len(token) > 16 or any(ord(char) < 33 or ord(char) > 126 for char in token):
                return "invalid_q_construct"
    elif "I" in normalized_tokens:
        return "invalid_q_construct"
    return None


def validate_aprsis_rf_target(target_name: Any, *, require_active: bool = True) -> tuple[dict[str, Any] | None, str | None]:
    name = str(target_name or "").strip()
    if not name:
        return None, "target_unavailable"
    row = fetch_one(
        """
        SELECT id, name, modem_type, band, device_path, enabled, tx_blocked
        FROM modems
        WHERE name = ?
        ORDER BY id ASC
        LIMIT 1
        """,
        (name,),
    )
    if row is None:
        return None, "target_unavailable"
    target = dict(row)
    modem_type = str(target.get("modem_type") or "").strip().upper()
    if modem_type == "OPENWEBRX_MQTT":
        return None, "target_rx_only"
    if modem_type not in TX_CAPABLE_MODEM_TYPES:
        return None, "invalid_target_type"
    if require_active and int(target.get("enabled") or 0) != 1:
        return None, "target_unavailable"
    if require_active and int(target.get("tx_blocked") or 0) == 1:
        return None, "target_rx_only"
    return target, None


def validate_aprsis_source(source_name: Any) -> dict[str, Any] | None:
    name = str(source_name or "").strip()
    if not name:
        return None
    row = fetch_one(
        """
        SELECT id, name, modem_type, enabled
        FROM modems
        WHERE name = ? AND UPPER(modem_type) = 'APRSIS'
        ORDER BY id ASC
        LIMIT 1
        """,
        (name,),
    )
    return dict(row) if row is not None else None


def normalize_outbound_rf_path(raw_path: Any) -> str:
    tokens = [token.strip().upper() for token in str(raw_path or "").split(",") if token.strip()]
    if len(tokens) > 8:
        raise ValueError("Outbound RF path cannot contain more than eight addresses.")
    for token in tokens:
        if token.endswith("*") or not _AX25_ADDRESS_RE.fullmatch(token):
            raise ValueError(f"Outbound RF path contains an invalid address: {token}.")
    return ",".join(tokens)


def record_aprsis_rf_stat(flow_id: int, counter: str, *, amount: int = 1) -> None:
    normalized_counter = str(counter or "").strip()
    if normalized_counter not in APRSIS_RF_STAT_COUNTERS:
        raise ValueError(f"Unsupported APRS-IS to RF statistics counter: {normalized_counter}.")
    increment = max(0, int(amount))
    if increment == 0:
        return
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO aprsis_rf_stats (flow_id, updated_at)
            VALUES (?, ?)
            ON CONFLICT(flow_id) DO NOTHING
            """,
            (int(flow_id), timestamp),
        )
        connection.execute(
            f"UPDATE aprsis_rf_stats SET {normalized_counter} = {normalized_counter} + ?, updated_at = ? WHERE flow_id = ?",
            (increment, timestamp, int(flow_id)),
        )


def get_aprsis_rf_stats(flow_id: int) -> dict[str, int]:
    row = fetch_one(
        """
        SELECT received_from_aprsis, matched_message_rule, matched_associated_position,
               matched_allow_rule, dropped_no_allow_rule,
               dropped_recipient_not_local, dropped_recipient_seen_internet,
               dropped_sender_heard_rf,
               dropped_safety_guard, dropped_duplicate, cancelled_during_viscous_delay,
               dropped_rate_limit, dropped_oversize, queued_to_rf, transmitted_to_rf, tx_failed
        FROM aprsis_rf_stats
        WHERE flow_id = ?
        """,
        (int(flow_id),),
    )
    if row is None:
        return {counter: 0 for counter in sorted(APRSIS_RF_STAT_COUNTERS)}
    return {counter: int(row[counter] or 0) for counter in APRSIS_RF_STAT_COUNTERS}


def _path_tokens(path: str, *, keep_used_marker: bool) -> list[str]:
    tokens = [item.strip() for item in str(path or "").split(",") if item.strip()]
    if keep_used_marker:
        return tokens
    return [token.rstrip("*") for token in tokens]


def _finite_float(value: Any, *, label: str) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number.") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{label} must be a finite number.")
    return parsed


def _parsed_position(aprs_data: dict[str, Any]) -> tuple[float, float] | None:
    try:
        latitude = float(str(aprs_data.get("latitude") or "").strip())
        longitude = float(str(aprs_data.get("longitude") or "").strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return None
    if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
        return None
    return latitude, longitude


def _station_position(station_settings: dict[str, Any] | None) -> tuple[float, float] | None:
    settings = station_settings or {}
    try:
        latitude = float(str(settings.get("latitude") or "").strip())
        longitude = float(str(settings.get("longitude") or "").strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return None
    if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
        return None
    return latitude, longitude


def _distance_km(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    earth_radius_km = 6371.0
    phi_1 = math.radians(latitude_a)
    phi_2 = math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a)
    delta_lambda = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0) ** 2
    )
    return earth_radius_km * 2.0 * math.atan2(math.sqrt(haversine), math.sqrt(1.0 - haversine))
