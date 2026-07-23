from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from app.db import fetch_one, get_connection, utc_now
from app.services.mqtt_url import TX_CAPABLE_MODEM_TYPES


APRSIS_FLOW_SOURCE_KIND = "receiver_aprsis"
RF_GUARD_STEP_TYPE = "filter_rf_guard"
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

ALLOW_RULE_FIELDS = (
    "packet_type",
    "source_callsign",
    "destination",
    "addressee",
    "object_name",
    "icon",
    "center_latitude",
    "center_longitude",
    "radius_km",
)
APRSIS_RF_STAT_COUNTERS = frozenset(
    {
        "received_from_aprsis",
        "matched_allow_rule",
        "dropped_no_allow_rule",
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


def normalize_allow_rules(raw_rules: Any) -> list[dict[str, str]]:
    if raw_rules is None or raw_rules == "":
        return []
    if not isinstance(raw_rules, list):
        raise ValueError("Inclusive allow rules must be a list.")
    if len(raw_rules) > 50:
        raise ValueError("Inclusive allow rules are limited to 50 rules per flow.")

    normalized: list[dict[str, str]] = []
    for rule_index, raw_rule in enumerate(raw_rules, start=1):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"Allow rule {rule_index} must be an object.")
        unknown_fields = {str(key) for key in raw_rule} - set(ALLOW_RULE_FIELDS)
        if unknown_fields:
            unknown = ", ".join(sorted(unknown_fields))
            raise ValueError(f"Allow rule {rule_index} contains unsupported fields: {unknown}.")
        rule: dict[str, str] = {}
        for field in ALLOW_RULE_FIELDS:
            value = str(raw_rule.get(field) or "").strip()
            if not value:
                continue
            if len(value) > 80:
                raise ValueError(f"Allow rule {rule_index} field {field} is too long.")
            rule[field] = value
        distance_fields = ("center_latitude", "center_longitude", "radius_km")
        configured_distance_fields = [field for field in distance_fields if rule.get(field)]
        if configured_distance_fields and len(configured_distance_fields) != len(distance_fields):
            raise ValueError(
                f"Allow rule {rule_index} distance condition requires center_latitude, center_longitude and radius_km."
            )
        if configured_distance_fields:
            latitude = _finite_float(rule["center_latitude"], label=f"Allow rule {rule_index} center latitude")
            longitude = _finite_float(rule["center_longitude"], label=f"Allow rule {rule_index} center longitude")
            radius_km = _finite_float(rule["radius_km"], label=f"Allow rule {rule_index} radius")
            if latitude < -90.0 or latitude > 90.0:
                raise ValueError(f"Allow rule {rule_index} center latitude must be between -90 and 90.")
            if longitude < -180.0 or longitude > 180.0:
                raise ValueError(f"Allow rule {rule_index} center longitude must be between -180 and 180.")
            if radius_km <= 0.0 or radius_km > 1000.0:
                raise ValueError(f"Allow rule {rule_index} radius must be greater than 0 and at most 1000 km.")
        # Empty cards created and then abandoned in the browser do not become
        # implicit match-all rules.  An empty rules list is the safe, valid
        # default-deny configuration.
        if rule:
            normalized.append(rule)
    return normalized


def match_allow_rules(parsed: dict[str, Any] | None, rules: list[dict[str, str]]) -> int | None:
    if not parsed or not rules:
        return None
    aprs_data = dict(parsed.get("aprs_data") or {})
    packet_values = {
        str(aprs_data.get("packet_group") or "").strip().casefold(),
        str(aprs_data.get("packet_type_code") or "").strip().casefold(),
    }
    values = {
        "source_callsign": str(parsed.get("logical_source_key") or parsed.get("source") or "").strip().upper(),
        "destination": str(parsed.get("logical_destination") or parsed.get("destination") or "").strip().upper(),
        "addressee": str(aprs_data.get("addressee") or "").strip().upper(),
        "object_name": str(parsed.get("entity_name") or aprs_data.get("entity_name") or "").strip().upper(),
        "icon": str(aprs_data.get("symbol") or "").strip().upper(),
    }
    for index, rule in enumerate(rules, start=1):
        configured_rule = {
            str(field): str(expected).strip()
            for field, expected in rule.items()
            if str(expected).strip()
        }
        if not configured_rule:
            continue
        distance_fields = {"center_latitude", "center_longitude", "radius_km"}
        configured_distance_fields = distance_fields.intersection(configured_rule)
        if configured_distance_fields and configured_distance_fields != distance_fields:
            continue
        matches = True
        for field, expected in configured_rule.items():
            if field == "packet_type":
                if str(expected).strip().casefold() not in packet_values:
                    matches = False
                    break
                continue
            if field in {"center_latitude", "center_longitude", "radius_km"}:
                if field != "center_latitude":
                    continue
                position = _parsed_position(aprs_data)
                if position is None:
                    matches = False
                    break
                distance_km = _distance_km(
                    position[0],
                    position[1],
                    float(rule["center_latitude"]),
                    float(rule["center_longitude"]),
                )
                if distance_km > float(rule["radius_km"]):
                    matches = False
                    break
                continue
            actual = values.get(field, "")
            if not _wildcard_match(actual, str(expected).strip().upper()):
                matches = False
                break
        if matches:
            return index
    return None


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
        SELECT received_from_aprsis, matched_allow_rule, dropped_no_allow_rule,
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


def _wildcard_match(actual: str, expected: str) -> bool:
    if not actual or not expected:
        return False
    pattern = "^" + re.escape(expected).replace(r"\*", ".*") + "$"
    return re.fullmatch(pattern, actual, flags=re.IGNORECASE) is not None


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
