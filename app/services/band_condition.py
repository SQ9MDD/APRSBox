from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from statistics import median
from typing import Any

from app.db import fetch_all, fetch_one, get_connection, utc_now
from app.services.content import get_station_settings, parse_tnc2_frame
from app.services.traffic_source import STATISTICS_TRAFFIC_SQL_PREDICATE


MONITORED_BANDS = ("2m", "70cm")
BAND_CONDITION_HISTORY_DAYS = 370
BAND_CONDITION_STATION_HISTORY_DAYS = 35
BAND_CONDITION_BASELINE_DAYS = 28
BAND_CONDITION_MIN_MODEL_HOURS = 24
BAND_CONDITION_MIN_BASELINE_ROWS = 12
BAND_CONDITION_CURRENT_MIN_SEGMENTS = 3

CONDITION_LABELS = {
    0: "Severely degraded",
    1: "Degraded propagation",
    2: "Normal conditions",
    3: "Moderate opening",
    4: "Strong opening",
    5: "Very strong opening",
}

CONDITION_SUMMARIES = {
    0: "Usual fixed stations have largely disappeared despite continuing RF activity.",
    1: "Fewer usual fixed stations are audible, especially near the normal coverage edge.",
    2: "The audible fixed-station footprint is close to its learned normal range.",
    3: "More fixed stations or a wider footprint than usual are currently visible.",
    4: "Distant fixed stations provide clear evidence of a strong propagation opening.",
    5: "Many very distant fixed stations across several areas indicate a very strong opening.",
}

CONDITION_TONES = {
    0: "bad",
    1: "caution",
    2: "neutral",
    3: "noticeable",
    4: "good",
    5: "excellent",
}


def normalize_band(value: Any) -> str:
    return str(value or "").strip().lower()


def format_band_label(value: Any) -> str:
    normalized = normalize_band(value)
    if normalized == "2m":
        return "2m"
    if normalized == "70cm":
        return "70cm"
    return normalized.upper() if normalized else "—"


def monitored_band_options() -> list[dict[str, str]]:
    return [
        {"value": "", "label": "No band condition assessment"},
        {"value": "2m", "label": "2m — assess propagation"},
        {"value": "70cm", "label": "70cm — assess propagation"},
    ]


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _floor_to_hour(value: datetime) -> datetime:
    return _normalize_utc_datetime(value).replace(minute=0, second=0, microsecond=0)


def _parse_iso_datetime(value: Any) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _normalize_utc_datetime(parsed)


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


def _distance_km(
    latitude_a: float | None,
    longitude_a: float | None,
    latitude_b: float | None,
    longitude_b: float | None,
) -> float | None:
    if None in {latitude_a, longitude_a, latitude_b, longitude_b}:
        return None
    earth_radius_km = 6371.0
    phi_1 = math.radians(float(latitude_a))
    phi_2 = math.radians(float(latitude_b))
    delta_phi = math.radians(float(latitude_b) - float(latitude_a))
    delta_lambda = math.radians(float(longitude_b) - float(longitude_a))
    haversine = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0) ** 2
    )
    arc = 2.0 * math.atan2(math.sqrt(haversine), math.sqrt(max(0.0, 1.0 - haversine)))
    return round(earth_radius_km * arc, 1)


def _percentile(values: list[float], percentile: float) -> float | None:
    ordered = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, float(percentile))) * (len(ordered) - 1)
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return ordered[lower_index] + ((ordered[upper_index] - ordered[lower_index]) * fraction)


def _rounded(value: float | None, digits: int = 1) -> float | None:
    return round(float(value), digits) if value is not None else None


def _bit_count(value: Any) -> int:
    try:
        return int(value or 0).bit_count()
    except (TypeError, ValueError):
        return 0


def _geographic_cell(latitude: float | None, longitude: float | None) -> str:
    if latitude is None or longitude is None:
        return ""
    return f"{math.floor(latitude * 2.0) / 2.0:.1f}:{math.floor(longitude * 2.0) / 2.0:.1f}"


def _monitored_interfaces() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT id, name, band, updated_at
        FROM modems
        WHERE enabled = 1
          AND LOWER(TRIM(COALESCE(band, ''))) IN ('2m', '70cm')
          AND UPPER(TRIM(COALESCE(modem_type, ''))) <> 'APRSIS'
        ORDER BY id ASC
        """
    )
    return [dict(row) for row in rows]


def _path_is_direct(path: Any) -> bool:
    tokens = [token.strip() for token in str(path or "").split(",") if token.strip()]
    return not any(token.endswith("*") for token in tokens)


def aggregate_band_condition_bucket(
    *,
    bucket_start_utc: datetime,
    bucket_end_utc: datetime,
) -> dict[str, int]:
    """Aggregate one closed five-minute RF bucket into idempotent hourly station masks."""

    interfaces = _monitored_interfaces()
    interface_by_id = {int(item["id"]): item for item in interfaces}
    if not interface_by_id:
        return {"frames": 0, "stations": 0}

    placeholders = ", ".join("?" for _ in interface_by_id)
    frame_rows = fetch_all(
        f"""
        SELECT interface_id, line
        FROM traffic_frames
        WHERE created_at >= ?
          AND created_at < ?
          AND UPPER(COALESCE(direction, '')) = 'RX'
          AND UPPER(COALESCE(format, '')) = 'TNC2'
          AND interface_id IN ({placeholders})
          AND {STATISTICS_TRAFFIC_SQL_PREDICATE}
        ORDER BY id ASC
        """,
        (
            _normalize_utc_datetime(bucket_start_utc).isoformat(),
            _normalize_utc_datetime(bucket_end_utc).isoformat(),
            *interface_by_id.keys(),
        ),
    )
    parsed_frame_rows: list[dict[str, Any]] = []
    for row in frame_rows:
        parsed = parse_tnc2_frame(str(row["line"] or ""))
        if parsed is None:
            continue
        parsed_frame_rows.append(
            {
                "interface_id": row["interface_id"],
                "parsed": parsed,
            }
        )
    return aggregate_band_condition_parsed_bucket(
        bucket_start_utc=bucket_start_utc,
        parsed_frame_rows=parsed_frame_rows,
    )


def aggregate_band_condition_parsed_bucket(
    *,
    bucket_start_utc: datetime,
    parsed_frame_rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Store band observations already parsed by the shared five-minute aggregator."""

    interfaces = _monitored_interfaces()
    interface_by_id = {int(item["id"]): item for item in interfaces}
    if not interface_by_id or not parsed_frame_rows:
        return {"frames": 0, "stations": 0}

    station_settings = get_station_settings()
    receiver_latitude = _parse_coordinate(station_settings.get("latitude"))
    receiver_longitude = _parse_coordinate(station_settings.get("longitude"))
    hour_start = _floor_to_hour(bucket_start_utc)
    segment_index = max(0, min(11, int((_normalize_utc_datetime(bucket_start_utc).minute // 5))))
    segment_mask = 1 << segment_index
    grouped: dict[tuple[int, str], dict[str, Any]] = {}
    parsed_frames = 0

    for row in parsed_frame_rows:
        try:
            interface_id = int(row["interface_id"])
        except (TypeError, ValueError):
            continue
        interface = interface_by_id.get(interface_id)
        if interface is None:
            continue
        parsed_value = row.get("parsed")
        if not isinstance(parsed_value, dict):
            continue
        parsed = parsed_value
        if bool(parsed.get("is_third_party")) and not bool(parsed.get("third_party_inner_valid")):
            continue

        aprs_data = dict(parsed.get("aprs_data") or {})
        packet_group = str(aprs_data.get("packet_group") or "").strip().lower()
        if packet_group in {"object", "item"}:
            continue
        station_key = str(parsed.get("logical_source_key") or parsed.get("source_key") or "").strip().upper()
        if not station_key:
            continue

        parsed_frames += 1
        key = (interface_id, station_key)
        observation = grouped.setdefault(
            key,
            {
                "interface_id": interface_id,
                "interface_name": str(interface.get("name") or ""),
                "band": normalize_band(interface.get("band")),
                "station_key": station_key,
                "fixed_hint": 0,
                "mobile_hint": 0,
                "segment_mask": segment_mask,
                "direct_segment_mask": 0,
                "latitude": None,
                "longitude": None,
                "distance_km": None,
            },
        )
        classification = str(parsed.get("classification") or "").strip().lower()
        if classification == "mobile":
            observation["mobile_hint"] = 1
        elif classification == "fixed":
            observation["fixed_hint"] = 1

        if _path_is_direct(parsed.get("logical_path") or parsed.get("path")):
            observation["direct_segment_mask"] |= segment_mask
        latitude = _parse_coordinate(aprs_data.get("latitude"))
        longitude = _parse_coordinate(aprs_data.get("longitude"))
        if latitude is not None and longitude is not None:
            observation["latitude"] = latitude
            observation["longitude"] = longitude
            observation["distance_km"] = _distance_km(
                receiver_latitude,
                receiver_longitude,
                latitude,
                longitude,
            )

    if not grouped:
        return {"frames": parsed_frames, "stations": 0}

    timestamp = utc_now()
    with get_connection() as connection:
        for observation in grouped.values():
            connection.execute(
                """
                INSERT INTO band_condition_station_hours (
                    hour_start_utc, interface_id, interface_name, band, station_key,
                    segment_mask, direct_segment_mask, fixed_hint, mobile_hint,
                    latitude, longitude, distance_km, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(hour_start_utc, interface_id, band, station_key) DO UPDATE SET
                    interface_name = excluded.interface_name,
                    segment_mask = band_condition_station_hours.segment_mask | excluded.segment_mask,
                    direct_segment_mask = band_condition_station_hours.direct_segment_mask | excluded.direct_segment_mask,
                    fixed_hint = MAX(band_condition_station_hours.fixed_hint, excluded.fixed_hint),
                    mobile_hint = MAX(band_condition_station_hours.mobile_hint, excluded.mobile_hint),
                    latitude = COALESCE(excluded.latitude, band_condition_station_hours.latitude),
                    longitude = COALESCE(excluded.longitude, band_condition_station_hours.longitude),
                    distance_km = COALESCE(excluded.distance_km, band_condition_station_hours.distance_km),
                    updated_at = excluded.updated_at
                """,
                (
                    hour_start.isoformat(),
                    int(observation["interface_id"]),
                    str(observation["interface_name"]),
                    str(observation["band"]),
                    str(observation["station_key"]),
                    int(observation["segment_mask"]),
                    int(observation["direct_segment_mask"]),
                    int(observation["fixed_hint"]),
                    int(observation["mobile_hint"]),
                    observation["latitude"],
                    observation["longitude"],
                    observation["distance_km"],
                    timestamp,
                ),
            )
    return {"frames": parsed_frames, "stations": len(grouped)}


def _station_rows_for_hour(interface_id: int, band: str, hour_start: datetime) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT
            current.station_key,
            current.segment_mask,
            current.direct_segment_mask,
            current.fixed_hint,
            current.mobile_hint,
            COALESCE(current.latitude, profile.latitude) AS latitude,
            COALESCE(current.longitude, profile.longitude) AS longitude,
            COALESCE(current.distance_km, profile.distance_km) AS distance_km,
            COALESCE(profile.observed_hours, 0) AS historical_hours,
            COALESCE(profile.direct_hours, 0) AS historical_direct_hours,
            COALESCE(profile.fixed_hours, 0) AS historical_fixed_hours,
            COALESCE(profile.mobile_hours, 0) AS historical_mobile_hours
        FROM band_condition_station_hours AS current
        LEFT JOIN band_condition_station_profiles AS profile
          ON profile.interface_id = current.interface_id
         AND profile.band = current.band
         AND profile.station_key = current.station_key
        WHERE current.interface_id = ?
          AND current.band = ?
          AND current.hour_start_utc = ?
        ORDER BY current.station_key ASC
        """,
        (int(interface_id), normalize_band(band), _floor_to_hour(hour_start).isoformat()),
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        historical_mobile = int(item.get("historical_mobile_hours") or 0)
        historical_fixed = int(item.get("historical_fixed_hours") or 0)
        explicitly_mobile = bool(item.get("mobile_hint"))
        if explicitly_mobile or (historical_mobile > historical_fixed and historical_mobile >= 2):
            continue
        result.append(item)
    return result


def _baseline_rows(interface_id: int, band: str, hour_start: datetime) -> list[dict[str, Any]]:
    cutoff = _floor_to_hour(hour_start) - timedelta(days=BAND_CONDITION_BASELINE_DAYS)
    rows = fetch_all(
        """
        SELECT *
        FROM band_condition_hourly
        WHERE interface_id = ?
          AND band = ?
          AND hour_start_utc >= ?
          AND hour_start_utc < ?
          AND (condition_index IS NULL OR condition_index BETWEEN 1 AND 3)
        ORDER BY hour_start_utc ASC
        """,
        (
            int(interface_id),
            normalize_band(band),
            cutoff.isoformat(),
            _floor_to_hour(hour_start).isoformat(),
        ),
    )
    result = [dict(row) for row in rows]
    same_hour = [
        row
        for row in result
        if (_parse_iso_datetime(row.get("hour_start_utc")) or hour_start).hour == _floor_to_hour(hour_start).hour
    ]
    return same_hour if len(same_hour) >= 3 else result


def _history_summary(interface_id: int, band: str, hour_start: datetime) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT
            COUNT(*) AS history_hours,
            SUM(CASE WHEN fixed_station_count > 0 THEN 1 ELSE 0 END) AS data_hours,
            MIN(hour_start_utc) AS first_hour,
            MAX(hour_start_utc) AS last_hour
        FROM band_condition_hourly
        WHERE interface_id = ?
          AND band = ?
          AND hour_start_utc < ?
        """,
        (int(interface_id), normalize_band(band), _floor_to_hour(hour_start).isoformat()),
    )
    return (
        dict(row)
        if row is not None
        else {"history_hours": 0, "data_hours": 0, "first_hour": None, "last_hour": None}
    )


def _profile_summary(interface_id: int, band: str, hour_start: datetime) -> dict[str, int]:
    cutoff = _floor_to_hour(hour_start) - timedelta(days=BAND_CONDITION_STATION_HISTORY_DAYS)
    row = fetch_one(
        """
        SELECT
            COUNT(*) AS learned_station_count,
            SUM(CASE WHEN positioned_hours > 0 THEN 1 ELSE 0 END) AS learned_positioned_station_count,
            SUM(CASE WHEN observed_hours >= 2 THEN 1 ELSE 0 END) AS repeatable_station_count
        FROM band_condition_station_profiles
        WHERE interface_id = ?
          AND band = ?
          AND last_heard_at >= ?
          AND NOT (mobile_hours > fixed_hours AND mobile_hours >= 2)
        """,
        (int(interface_id), normalize_band(band), cutoff.isoformat()),
    )
    item = dict(row) if row is not None else {}
    return {
        "learned_station_count": int(item.get("learned_station_count") or 0),
        "learned_positioned_station_count": int(item.get("learned_positioned_station_count") or 0),
        "repeatable_station_count": int(item.get("repeatable_station_count") or 0),
    }


def _model_progress(interface_id: int, band: str, hour_start: datetime, *, model_ready: bool) -> dict[str, Any]:
    hour = _floor_to_hour(hour_start)
    history = _history_summary(interface_id, band, hour)
    profiles = _profile_summary(interface_id, band, hour)
    history_hours = int(history.get("history_hours") or 0)
    data_hours = int(history.get("data_hours") or 0)
    first_hour = _parse_iso_datetime(history.get("first_hour"))
    history_span_hours = (
        max(0.0, (hour - first_hour).total_seconds() / 3600.0)
        if first_hour is not None
        else 0.0
    )
    first_assessment_percent = int(
        round(min(1.0, history_span_hours / float(BAND_CONDITION_MIN_MODEL_HOURS)) * 100.0)
    )
    hours_to_first_assessment = max(
        0,
        int(math.ceil(BAND_CONDITION_MIN_MODEL_HOURS - history_span_hours)),
    )
    mature_hours = 30 * 24
    maturity_percent = int(round(min(1.0, history_span_hours / float(mature_hours)) * 100.0))
    days_to_mature = max(0, int(math.ceil((mature_hours - history_span_hours) / 24.0)))

    if not model_ready:
        stage_label = "Collecting data"
        stage_summary = (
            "The first assessment appears after 24 hours. At first it will intentionally have low confidence."
        )
    elif history_span_hours < 7 * 24:
        stage_label = "Initial assessment"
        stage_summary = "The assessment is available, but the first days can still noticeably change the learned norm."
    elif history_span_hours < mature_hours:
        stage_label = "Building confidence"
        stage_summary = "Each regular day improves the comparison with the usual fixed-station footprint."
    else:
        stage_label = "Mature baseline"
        stage_summary = (
            "At least 30 days have been collected; confidence still depends on regular traffic and known positions."
        )

    return {
        "history_hours": history_hours,
        "data_hours": data_hours,
        "history_days": round(history_span_hours / 24.0, 1),
        "learned_station_count": profiles["learned_station_count"],
        "learned_positioned_station_count": profiles["learned_positioned_station_count"],
        "repeatable_station_count": profiles["repeatable_station_count"],
        "first_assessment_percent": first_assessment_percent,
        "hours_to_first_assessment": hours_to_first_assessment,
        "maturity_percent": maturity_percent,
        "days_to_mature": days_to_mature,
        "model_stage_label": stage_label,
        "model_stage_summary": stage_summary,
    }


def _hour_rx_total(interface_id: int, hour_start: datetime) -> int:
    hour = _floor_to_hour(hour_start)
    row = fetch_one(
        """
        SELECT COALESCE(SUM(rx_total), 0) AS total
        FROM radio_activity_5m
        WHERE interface_id = ?
          AND bucket_start_utc >= ?
          AND bucket_start_utc < ?
        """,
        (int(interface_id), hour.isoformat(), (hour + timedelta(hours=1)).isoformat()),
    )
    return int((dict(row) if row is not None else {}).get("total") or 0)


def _score_condition(
    *,
    fixed_station_count: int,
    normal_station_count: float,
    current_p90_distance_km: float | None,
    normal_p90_distance_km: float | None,
    far_station_count: int,
    confirmed_far_station_count: int,
    very_far_station_count: int,
    confirmed_very_far_station_count: int,
    new_area_count: int,
    rx_total: int,
) -> int | None:
    if rx_total <= 0 and fixed_station_count <= 0:
        return None

    normal_count = max(0.0, float(normal_station_count))
    count_lift_threshold = normal_count + max(2.0, normal_count * 0.30)
    reach_ratio = 1.0
    if current_p90_distance_km is not None and normal_p90_distance_km and normal_p90_distance_km > 0:
        reach_ratio = current_p90_distance_km / normal_p90_distance_km

    if (
        very_far_station_count >= 3
        and (confirmed_very_far_station_count >= 2 or very_far_station_count >= 5)
        and new_area_count >= 2
        and fixed_station_count >= max(3, int(math.ceil(normal_count)))
        and reach_ratio >= 1.55
    ):
        return 5
    if (
        confirmed_very_far_station_count >= 1
        or very_far_station_count >= 2
        or confirmed_far_station_count >= 2
        or (far_station_count >= 1 and reach_ratio >= 1.60)
    ):
        return 4
    if fixed_station_count >= count_lift_threshold or far_station_count >= 1 or reach_ratio >= 1.20:
        return 3
    if normal_count > 0 and fixed_station_count <= max(0.0, normal_count * 0.25):
        return 0
    if normal_count > 1 and fixed_station_count < normal_count * 0.65:
        return 1
    return 2


def _confidence_score(
    *,
    history_hours: int,
    history_span_hours: float,
    baseline_rows: int,
    stable_station_count: int,
    positioned_ratio: float,
    current_segment_count: int,
    fixed_station_count: int,
) -> float:
    history_days = max(0.0, history_span_hours / 24.0)
    history_factor = min(1.0, math.log1p(history_days) / math.log1p(28.0))
    coverage_factor = min(1.0, history_hours / float(24 * 14))
    baseline_factor = min(1.0, baseline_rows / 14.0)
    station_factor = min(1.0, stable_station_count / 16.0)
    position_factor = max(0.0, min(1.0, positioned_ratio))
    current_factor = min(
        1.0,
        (min(1.0, current_segment_count / 6.0) * 0.55)
        + (min(1.0, fixed_station_count / 8.0) * 0.45),
    )
    score = (
        (history_factor * 0.32)
        + (coverage_factor * 0.18)
        + (baseline_factor * 0.16)
        + (station_factor * 0.14)
        + (position_factor * 0.10)
        + (current_factor * 0.10)
    )
    return max(0.0, min(0.97, score))


def _evaluate_hour(
    *,
    interface_id: int,
    interface_name: str,
    band: str,
    hour_start: datetime,
) -> dict[str, Any]:
    normalized_band = normalize_band(band)
    hour = _floor_to_hour(hour_start)
    station_rows = _station_rows_for_hour(interface_id, normalized_band, hour)
    distances = [
        float(row["distance_km"])
        for row in station_rows
        if row.get("distance_km") is not None and float(row["distance_km"]) >= 0
    ]
    fixed_station_count = len(station_rows)
    positioned_station_count = len(distances)
    direct_station_count = sum(1 for row in station_rows if int(row.get("direct_segment_mask") or 0) > 0)
    current_median_distance = float(median(distances)) if distances else None
    current_p90_distance = _percentile(distances, 0.90)
    confirmed_distances = [
        float(row["distance_km"])
        for row in station_rows
        if row.get("distance_km") is not None and _bit_count(row.get("segment_mask")) >= 2
    ]
    max_confirmed_distance = max(confirmed_distances) if confirmed_distances else None

    baseline = _baseline_rows(interface_id, normalized_band, hour)
    baseline_counts = [float(row.get("fixed_station_count") or 0) for row in baseline]
    baseline_p90_values = [
        float(row["p90_distance_km"])
        for row in baseline
        if row.get("p90_distance_km") is not None and float(row["p90_distance_km"]) > 0
    ]
    normal_station_count = float(median(baseline_counts)) if baseline_counts else 0.0
    normal_p90_distance = float(median(baseline_p90_values)) if baseline_p90_values else None
    moderate_far_threshold = (
        max(normal_p90_distance * 1.25, normal_p90_distance + 40.0)
        if normal_p90_distance is not None
        else None
    )
    very_far_threshold = (
        max(normal_p90_distance * 1.75, normal_p90_distance + 120.0)
        if normal_p90_distance is not None
        else None
    )

    far_rows = [
        row
        for row in station_rows
        if moderate_far_threshold is not None
        and row.get("distance_km") is not None
        and float(row["distance_km"]) >= moderate_far_threshold
    ]
    very_far_rows = [
        row
        for row in station_rows
        if very_far_threshold is not None
        and row.get("distance_km") is not None
        and float(row["distance_km"]) >= very_far_threshold
    ]
    confirmed_far_count = sum(1 for row in far_rows if _bit_count(row.get("segment_mask")) >= 2)
    confirmed_very_far_count = sum(1 for row in very_far_rows if _bit_count(row.get("segment_mask")) >= 2)
    new_cells = {
        _geographic_cell(_parse_coordinate(row.get("latitude")), _parse_coordinate(row.get("longitude")))
        for row in far_rows
        if int(row.get("historical_hours") or 0) <= max(1, len(baseline) // 20)
    }
    new_cells.discard("")

    history = _history_summary(interface_id, normalized_band, hour)
    history_hours = int(history.get("history_hours") or 0)
    data_hours = int(history.get("data_hours") or 0)
    first_hour = _parse_iso_datetime(history.get("first_hour"))
    history_span_hours = (
        max(0.0, (hour - first_hour).total_seconds() / 3600.0)
        if first_hour is not None
        else 0.0
    )
    current_segment_mask = 0
    for row in station_rows:
        current_segment_mask |= int(row.get("segment_mask") or 0)
    current_segment_count = _bit_count(current_segment_mask)
    rx_total = _hour_rx_total(interface_id, hour)
    stable_station_count = sum(
        1
        for row in station_rows
        if int(row.get("historical_hours") or 0) >= max(2, min(12, history_hours // 12))
    )
    positioned_ratio = positioned_station_count / float(max(1, fixed_station_count))
    confidence = _confidence_score(
        history_hours=data_hours,
        history_span_hours=history_span_hours,
        baseline_rows=len(baseline),
        stable_station_count=stable_station_count,
        positioned_ratio=positioned_ratio,
        current_segment_count=current_segment_count,
        fixed_station_count=fixed_station_count,
    )

    model_ready = (
        history_hours >= BAND_CONDITION_MIN_MODEL_HOURS
        and history_span_hours >= BAND_CONDITION_MIN_MODEL_HOURS
        and len(baseline) >= BAND_CONDITION_MIN_BASELINE_ROWS
    )
    condition_index = None
    if model_ready:
        condition_index = _score_condition(
            fixed_station_count=fixed_station_count,
            normal_station_count=normal_station_count,
            current_p90_distance_km=current_p90_distance,
            normal_p90_distance_km=normal_p90_distance,
            far_station_count=len(far_rows),
            confirmed_far_station_count=confirmed_far_count,
            very_far_station_count=len(very_far_rows),
            confirmed_very_far_station_count=confirmed_very_far_count,
            new_area_count=len(new_cells),
            rx_total=rx_total,
        )

    label = CONDITION_LABELS.get(condition_index, "Collecting data")
    summary = CONDITION_SUMMARIES.get(
        condition_index,
        "The first assessment will appear after 24 hours of monitored RF data.",
    )
    if condition_index is None and model_ready and rx_total <= 0:
        label = "No current RF data"
        summary = "The model is ready, but there is not enough current RF activity for an assessment."
    return {
        "hour_start_utc": hour.isoformat(),
        "interface_id": int(interface_id),
        "interface_name": str(interface_name or f"Interface #{interface_id}"),
        "band": normalized_band,
        "band_label": format_band_label(normalized_band),
        "condition_index": condition_index,
        "label": label,
        "diagnosis_summary": summary,
        "diagnosis_tone": CONDITION_TONES.get(condition_index, "learning"),
        "confidence_score": round(confidence, 4),
        "confidence_percent": int(round(confidence * 100.0)),
        "history_hours": history_hours,
        "data_hours": data_hours,
        "history_days": round(history_span_hours / 24.0, 1),
        "model_ready": model_ready,
        "fixed_station_count": fixed_station_count,
        "positioned_station_count": positioned_station_count,
        "direct_station_count": direct_station_count,
        "median_distance_km": _rounded(current_median_distance),
        "p90_distance_km": _rounded(current_p90_distance),
        "max_confirmed_distance_km": _rounded(max_confirmed_distance),
        "normal_station_count": round(normal_station_count, 1),
        "normal_p90_distance_km": _rounded(normal_p90_distance),
        "far_station_count": len(far_rows),
        "very_far_station_count": len(very_far_rows),
        "new_area_count": len(new_cells),
        "current_segment_count": current_segment_count,
        "rx_total": rx_total,
    }


def _save_hourly_evaluation(evaluation: dict[str, Any]) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO band_condition_hourly (
                hour_start_utc, interface_id, interface_name, band,
                condition_index, confidence_score,
                fixed_station_count, positioned_station_count, direct_station_count,
                median_distance_km, p90_distance_km, max_confirmed_distance_km,
                normal_station_count, normal_p90_distance_km,
                far_station_count, very_far_station_count, new_area_count,
                history_hours, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evaluation["hour_start_utc"],
                evaluation["interface_id"],
                evaluation["interface_name"],
                evaluation["band"],
                evaluation["condition_index"],
                evaluation["confidence_score"],
                evaluation["fixed_station_count"],
                evaluation["positioned_station_count"],
                evaluation["direct_station_count"],
                evaluation["median_distance_km"],
                evaluation["p90_distance_km"],
                evaluation["max_confirmed_distance_km"],
                evaluation["normal_station_count"],
                evaluation["normal_p90_distance_km"],
                evaluation["far_station_count"],
                evaluation["very_far_station_count"],
                evaluation["new_area_count"],
                evaluation["history_hours"],
                utc_now(),
            ),
        )
        inserted = cursor.rowcount > 0
        if not inserted:
            return False

        station_rows = connection.execute(
            """
            SELECT station_key, segment_mask, direct_segment_mask, fixed_hint, mobile_hint,
                   latitude, longitude, distance_km
            FROM band_condition_station_hours
            WHERE hour_start_utc = ?
              AND interface_id = ?
              AND band = ?
            """,
            (
                evaluation["hour_start_utc"],
                evaluation["interface_id"],
                evaluation["band"],
            ),
        ).fetchall()
        timestamp = utc_now()
        for row in station_rows:
            connection.execute(
                """
                INSERT INTO band_condition_station_profiles (
                    interface_id, band, station_key, first_heard_at, last_heard_at,
                    observed_hours, direct_hours, positioned_hours, fixed_hours, mobile_hours,
                    latitude, longitude, distance_km, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(interface_id, band, station_key) DO UPDATE SET
                    last_heard_at = excluded.last_heard_at,
                    observed_hours = observed_hours + 1,
                    direct_hours = direct_hours + excluded.direct_hours,
                    positioned_hours = positioned_hours + excluded.positioned_hours,
                    fixed_hours = fixed_hours + excluded.fixed_hours,
                    mobile_hours = mobile_hours + excluded.mobile_hours,
                    latitude = COALESCE(excluded.latitude, latitude),
                    longitude = COALESCE(excluded.longitude, longitude),
                    distance_km = COALESCE(excluded.distance_km, distance_km),
                    updated_at = excluded.updated_at
                """,
                (
                    evaluation["interface_id"],
                    evaluation["band"],
                    str(row["station_key"]),
                    evaluation["hour_start_utc"],
                    evaluation["hour_start_utc"],
                    1 if int(row["direct_segment_mask"] or 0) > 0 else 0,
                    1 if row["latitude"] is not None and row["longitude"] is not None else 0,
                    int(bool(row["fixed_hint"])),
                    int(bool(row["mobile_hint"])),
                    row["latitude"],
                    row["longitude"],
                    row["distance_km"],
                    timestamp,
                ),
            )
    return True


def finalize_band_condition_hours(*, now_utc: datetime | None = None) -> dict[str, int]:
    now = _normalize_utc_datetime(now_utc or datetime.now(timezone.utc))
    latest_closed_hour = _floor_to_hour(now) - timedelta(hours=1)
    processed = 0

    for interface in _monitored_interfaces():
        interface_id = int(interface["id"])
        band = normalize_band(interface.get("band"))
        latest_row = fetch_one(
            """
            SELECT MAX(hour_start_utc) AS latest_hour
            FROM band_condition_hourly
            WHERE interface_id = ? AND band = ?
            """,
            (interface_id, band),
        )
        latest_saved = _parse_iso_datetime((dict(latest_row) if latest_row is not None else {}).get("latest_hour"))
        if latest_saved is not None:
            next_hour = latest_saved + timedelta(hours=1)
        else:
            oldest_station_row = fetch_one(
                """
                SELECT MIN(hour_start_utc) AS oldest_hour
                FROM band_condition_station_hours
                WHERE interface_id = ? AND band = ?
                """,
                (interface_id, band),
            )
            oldest_station_hour = _parse_iso_datetime(
                (dict(oldest_station_row) if oldest_station_row is not None else {}).get("oldest_hour")
            )
            next_hour = oldest_station_hour or latest_closed_hour

        hours_guard = 0
        while next_hour <= latest_closed_hour and hours_guard < 72:
            evaluation = _evaluate_hour(
                interface_id=interface_id,
                interface_name=str(interface.get("name") or ""),
                band=band,
                hour_start=next_hour,
            )
            if _save_hourly_evaluation(evaluation):
                processed += 1
            next_hour += timedelta(hours=1)
            hours_guard += 1

    history_cutoff = (now - timedelta(days=BAND_CONDITION_HISTORY_DAYS)).isoformat()
    station_cutoff = (now - timedelta(days=BAND_CONDITION_STATION_HISTORY_DAYS)).isoformat()
    with get_connection() as connection:
        history_deleted = connection.execute(
            "DELETE FROM band_condition_hourly WHERE hour_start_utc < ?",
            (history_cutoff,),
        ).rowcount
        station_deleted = connection.execute(
            "DELETE FROM band_condition_station_hours WHERE hour_start_utc < ?",
            (station_cutoff,),
        ).rowcount
        profiles_deleted = connection.execute(
            "DELETE FROM band_condition_station_profiles WHERE last_heard_at < ?",
            (history_cutoff,),
        ).rowcount
    return {
        "processed_hours": processed,
        "history_deleted": max(0, int(history_deleted or 0)),
        "station_hours_deleted": max(0, int(station_deleted or 0)),
        "profiles_deleted": max(0, int(profiles_deleted or 0)),
    }


def _latest_saved_snapshot(interface: dict[str, Any]) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT *
        FROM band_condition_hourly
        WHERE interface_id = ? AND band = ?
        ORDER BY hour_start_utc DESC
        LIMIT 1
        """,
        (int(interface["id"]), normalize_band(interface.get("band"))),
    )
    if row is None:
        return None
    item = dict(row)
    condition_index = item.get("condition_index")
    condition_index = int(condition_index) if condition_index is not None else None
    model_ready = int(item.get("history_hours") or 0) >= BAND_CONDITION_MIN_MODEL_HOURS
    label = CONDITION_LABELS.get(condition_index, "Collecting data")
    summary = CONDITION_SUMMARIES.get(
        condition_index,
        "The first assessment will appear after 24 hours of monitored RF data.",
    )
    if condition_index is None and model_ready:
        label = "No current RF data"
        summary = "The model is ready, but there is not enough current RF activity for an assessment."
    item.update(
        {
            "condition_index": condition_index,
            "band_label": format_band_label(item.get("band")),
            "label": label,
            "diagnosis_summary": summary,
            "diagnosis_tone": CONDITION_TONES.get(condition_index, "learning"),
            "confidence_percent": int(round(float(item.get("confidence_score") or 0.0) * 100.0)),
            "history_days": round(float(item.get("history_hours") or 0) / 24.0, 1),
            "model_ready": model_ready,
        }
    )
    return item


def _interface_snapshot(interface: dict[str, Any], *, now_utc: datetime) -> dict[str, Any]:
    current_hour = _floor_to_hour(now_utc)
    current = _evaluate_hour(
        interface_id=int(interface["id"]),
        interface_name=str(interface.get("name") or ""),
        band=normalize_band(interface.get("band")),
        hour_start=current_hour,
    )
    selected = current
    if current["current_segment_count"] < BAND_CONDITION_CURRENT_MIN_SEGMENTS:
        saved = _latest_saved_snapshot(interface)
        saved_hour = _parse_iso_datetime((saved or {}).get("hour_start_utc"))
        if saved is not None and saved_hour is not None and saved_hour >= current_hour - timedelta(hours=1):
            selected = saved
    selected.update(
        _model_progress(
            int(interface["id"]),
            normalize_band(interface.get("band")),
            current_hour,
            model_ready=bool(selected.get("model_ready")),
        )
    )
    return selected


def get_band_condition_snapshot(*, now_utc: datetime | None = None) -> dict[str, Any]:
    now = _normalize_utc_datetime(now_utc or datetime.now(timezone.utc))
    items = [_interface_snapshot(interface, now_utc=now) for interface in _monitored_interfaces()]
    return {
        "generated_at": utc_now(),
        "interfaces": items,
        # Retain the historical key for dashboard callers while the value is now interface-specific.
        "bands": items,
    }


def get_band_condition_page_data() -> dict[str, Any]:
    snapshot = get_band_condition_snapshot()
    return {
        "summary": snapshot,
        "interfaces": snapshot["interfaces"],
        "bands": snapshot["interfaces"],
    }


def get_band_condition_history(*, days: int = 365) -> dict[str, Any]:
    normalized_days = max(1, min(BAND_CONDITION_HISTORY_DAYS, int(days)))
    end_hour = _floor_to_hour(datetime.now(timezone.utc))
    start_hour = end_hour - timedelta(days=normalized_days)
    bucket_count = normalized_days * 24
    labels = [(start_hour + timedelta(hours=index)).isoformat() for index in range(bucket_count)]
    label_index = {label: index for index, label in enumerate(labels)}
    items: list[dict[str, Any]] = []

    for interface in _monitored_interfaces():
        interface_id = int(interface["id"])
        band = normalize_band(interface.get("band"))
        rows = fetch_all(
            """
            SELECT hour_start_utc, condition_index, confidence_score
            FROM band_condition_hourly
            WHERE interface_id = ?
              AND band = ?
              AND hour_start_utc >= ?
              AND hour_start_utc < ?
            ORDER BY hour_start_utc ASC
            """,
            (interface_id, band, start_hour.isoformat(), end_hour.isoformat()),
        )
        indexes: list[int | None] = [None] * bucket_count
        confidence: list[int | None] = [None] * bucket_count
        for row in rows:
            index = label_index.get(str(row["hour_start_utc"]))
            if index is None:
                continue
            indexes[index] = int(row["condition_index"]) if row["condition_index"] is not None else None
            confidence[index] = int(round(float(row["confidence_score"] or 0.0) * 100.0))
        items.append(
            {
                "interface_id": interface_id,
                "interface_name": str(interface.get("name") or ""),
                "band": band,
                "band_label": format_band_label(band),
                "indexes": indexes,
                "confidence": confidence,
            }
        )
    return {
        "days": normalized_days,
        "resolution_minutes": 60,
        "start_utc": start_hour.isoformat(),
        "end_utc": end_hour.isoformat(),
        "labels": labels,
        "items": items,
    }
