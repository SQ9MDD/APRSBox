from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Any

from app.db import fetch_all, fetch_one, get_connection, log_event, utc_now
from app.services.content import parse_tnc2_frame

BUCKET_MINUTES = 5
CURRENT_WINDOW_BUCKETS = 3
MIN_BASELINE_SAMPLES = 12
EMA_ALPHA = 0.2
INSUFFICIENT_CONFIDENCE = 0.2
DX_RARE_STATION_RATIO = 0.18
FIXED_REFERENCE_STATION_TYPES = ("home", "digi", "igate", "wx-fixed", "fixed")
BAND_OPTIONS = ("2m", "70cm", "6m")
STATION_TYPE_LABELS = {
    "home": "Home",
    "digi": "DIGI",
    "igate": "iGate",
    "wx-fixed": "WX Fixed",
    "fixed": "Other Fixed",
}


def normalize_band(value: str) -> str:
    return value.strip().lower()


def normalize_callsign(value: str) -> str:
    return value.strip().upper()


def normalize_ssid(value: str | None) -> str:
    normalized = str(value or "").strip()
    return normalized if normalized.isdigit() else ""


def build_station_key(callsign: str, ssid: str | None = "") -> str:
    normalized_callsign = normalize_callsign(callsign)
    normalized_ssid = normalize_ssid(ssid)
    if not normalized_callsign:
        return ""
    if normalized_ssid:
        return f"{normalized_callsign}-{normalized_ssid}"
    return normalized_callsign


def format_band_label(value: str) -> str:
    normalized = normalize_band(value)
    if not normalized:
        return "Unknown"
    mapping = {
        "2m": "2m",
        "70cm": "70cm",
        "6m": "6m",
        "23cm": "23cm",
        "hf": "HF",
        "vhf": "VHF",
        "uhf": "UHF",
        "unknown": "Unknown",
    }
    return mapping.get(normalized, normalized.upper())


def hour_of_day_from_utc(bucket_start_utc: str) -> int:
    bucket_time = datetime.fromisoformat(bucket_start_utc.replace("Z", "+00:00"))
    return bucket_time.astimezone().hour


def current_bucket_start(reference: datetime | None = None) -> str:
    now = reference or datetime.now(timezone.utc)
    rounded_minute = (now.minute // BUCKET_MINUTES) * BUCKET_MINUTES
    bucket = now.replace(minute=rounded_minute, second=0, microsecond=0)
    return bucket.isoformat()


def station_type_options() -> list[dict[str, str]]:
    return [{"value": value, "label": label} for value, label in STATION_TYPE_LABELS.items()]


def band_options() -> list[dict[str, str]]:
    return [{"value": band, "label": band} for band in BAND_OPTIONS]


def split_station_key(station_key: str) -> tuple[str, str]:
    normalized = station_key.strip().upper()
    if not normalized:
        return "", ""
    base, separator, suffix = normalized.partition("-")
    if separator and suffix.isdigit():
        return base, suffix
    return normalized, ""


def list_reference_station_candidates() -> list[dict[str, str]]:
    rows = fetch_all(
        """
        SELECT DISTINCT band, station_key
        FROM band_condition_activity_station_buckets
        WHERE is_fixed = 1
          AND TRIM(COALESCE(band, '')) <> ''
          AND TRIM(COALESCE(station_key, '')) <> ''
        ORDER BY band ASC, station_key ASC
        """
    )
    result: list[dict[str, str]] = []
    for row in rows:
        callsign, ssid = split_station_key(str(row["station_key"]))
        if not callsign:
            continue
        result.append(
            {
                "band": normalize_band(str(row["band"])),
                "callsign": callsign,
                "ssid": ssid,
                "station_key": build_station_key(callsign, ssid),
            }
        )
    return result


def list_reference_stations(*, band: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if band is not None:
        where = "WHERE band = ?"
        params.append(normalize_band(band))
    rows = fetch_all(
        f"""
        SELECT id, band, callsign, ssid, station_type, enabled, weight, created_at, updated_at
        FROM band_condition_reference_stations
        {where}
        ORDER BY band ASC, callsign ASC, ssid ASC, id ASC
        """,
        tuple(params),
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["station_key"] = build_station_key(item["callsign"], item["ssid"])
        item["band_label"] = format_band_label(item["band"])
        item["station_type_label"] = STATION_TYPE_LABELS.get(str(item["station_type"]), str(item["station_type"]))
        result.append(item)
    return result


def get_reference_station(record_id: int) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT id, band, callsign, ssid, station_type, enabled, weight, created_at, updated_at
        FROM band_condition_reference_stations
        WHERE id = ?
        """,
        (record_id,),
    )
    if not row:
        return None
    item = dict(row)
    item["station_key"] = build_station_key(item["callsign"], item["ssid"])
    item["band_label"] = format_band_label(item["band"])
    item["station_type_label"] = STATION_TYPE_LABELS.get(str(item["station_type"]), str(item["station_type"]))
    return item


def save_reference_station(payload: dict[str, Any], record_id: int | None = None) -> tuple[bool, str | None]:
    band = normalize_band(str(payload.get("band", "")))
    callsign = normalize_callsign(str(payload.get("callsign", "")))
    ssid = normalize_ssid(payload.get("ssid"))
    station_type = str(payload.get("station_type", "")).strip()
    enabled = int(bool(payload.get("enabled")))
    try:
        weight = float(payload.get("weight", 1.0))
    except (TypeError, ValueError):
        return False, "Weight must be a valid number."

    if not band:
        return False, "Band is required."
    if band not in BAND_OPTIONS:
        return False, "Band must be one of: 2m, 70cm, 6m."
    if not callsign:
        return False, "Callsign is required."
    if station_type not in FIXED_REFERENCE_STATION_TYPES:
        return False, "Station type must be a fixed/reference station type."
    if weight <= 0:
        return False, "Weight must be greater than zero."

    timestamp = utc_now()
    values = {
        "band": band,
        "callsign": callsign,
        "ssid": ssid,
        "station_type": station_type,
        "enabled": enabled,
        "weight": weight,
        "updated_at": timestamp,
    }
    try:
        with get_connection() as connection:
            if record_id is None:
                connection.execute(
                    """
                    INSERT INTO band_condition_reference_stations (
                        band, callsign, ssid, station_type, enabled, weight, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (band, callsign, ssid, station_type, enabled, weight, timestamp, timestamp),
                )
            else:
                connection.execute(
                    """
                    UPDATE band_condition_reference_stations
                    SET band = :band,
                        callsign = :callsign,
                        ssid = :ssid,
                        station_type = :station_type,
                        enabled = :enabled,
                        weight = :weight,
                        updated_at = :updated_at
                    WHERE id = :id
                    """,
                    {**values, "id": record_id},
                )
    except sqlite3.IntegrityError as exc:
        return False, str(exc)

    action = "Updated" if record_id is not None else "Created"
    log_event("INFO", "band_condition", f"{action} reference station {build_station_key(callsign, ssid)} on {band}")
    return True, None


def delete_reference_station(record_id: int) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM band_condition_reference_stations WHERE id = ?", (record_id,))
    log_event("INFO", "band_condition", f"Deleted reference station #{record_id}")


def monitored_band_for_active_modem() -> str:
    row = fetch_one(
        """
        SELECT band
        FROM modems
        WHERE enabled = 1 AND modem_type IN ('TCP', 'SERIALL')
        ORDER BY id ASC
        LIMIT 1
        """
    )
    band = normalize_band(str(row["band"] if row else ""))
    return band or "unknown"


def process_incoming_frame(line: str, band: str | None = None, timestamp: str | None = None) -> None:
    parsed = parse_tnc2_frame(line)
    if parsed is None:
        return
    if bool(parsed.get("is_third_party")) and not bool(parsed.get("third_party_inner_valid")):
        source_label = str(parsed.get("source_key") or parsed.get("source") or "").strip() or "unknown"
        log_event("WARNING", "aprs", f"Ignored malformed third-party APRS payload from {source_label}.")
        return

    bucket_band = normalize_band(band or "") or "unknown"
    bucket_start = current_bucket_start()
    classification = parsed["classification"]
    source_station_key = build_station_key(
        str(parsed.get("logical_source_callsign") or parsed.get("source_callsign") or ""),
        str(parsed.get("logical_source_ssid") or parsed.get("source_ssid") or ""),
    )
    if not source_station_key:
        return

    is_mobile = 1 if classification == "mobile" else 0
    is_fixed = 1 if classification in {"fixed", "object"} else 0

    with get_connection() as connection:
        _upsert_activity_bucket(connection, bucket_start, bucket_band, source_station_key, is_mobile=is_mobile, is_fixed=is_fixed)
        _upsert_audibility_bucket(
            connection,
            bucket_start,
            bucket_band,
            source_callsign=str(parsed.get("logical_source_callsign") or parsed.get("source_callsign") or ""),
            source_ssid=str(parsed.get("logical_source_ssid") or parsed.get("source_ssid") or ""),
        )
        _rollup_closed_buckets(connection, current_bucket_utc=bucket_start, processed_at=timestamp or utc_now())


def _upsert_activity_bucket(
    connection: sqlite3.Connection,
    bucket_start: str,
    band: str,
    station_key: str,
    *,
    is_mobile: int,
    is_fixed: int,
) -> None:
    connection.execute(
        """
        INSERT INTO band_condition_activity_buckets (
            bucket_start_utc, band, total_frames, total_unique_stations,
            mobile_frames, mobile_unique_stations, fixed_frames, fixed_unique_stations
        )
        VALUES (?, ?, 1, 0, ?, 0, ?, 0)
        ON CONFLICT(bucket_start_utc, band) DO UPDATE SET
            total_frames = total_frames + 1,
            mobile_frames = mobile_frames + excluded.mobile_frames,
            fixed_frames = fixed_frames + excluded.fixed_frames
        """,
        (bucket_start, band, is_mobile, is_fixed),
    )
    connection.execute(
        """
        INSERT INTO band_condition_activity_station_buckets (
            bucket_start_utc, band, station_key, is_mobile, is_fixed
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(bucket_start_utc, band, station_key) DO UPDATE SET
            is_mobile = CASE
                WHEN band_condition_activity_station_buckets.is_mobile = 1 OR excluded.is_mobile = 1 THEN 1
                ELSE 0
            END,
            is_fixed = CASE
                WHEN band_condition_activity_station_buckets.is_fixed = 1 OR excluded.is_fixed = 1 THEN 1
                ELSE 0
            END
        """,
        (bucket_start, band, station_key, is_mobile, is_fixed),
    )
    connection.execute(
        """
        UPDATE band_condition_activity_buckets
        SET total_unique_stations = (
                SELECT COUNT(*)
                FROM band_condition_activity_station_buckets
                WHERE bucket_start_utc = ? AND band = ?
            ),
            mobile_unique_stations = (
                SELECT COUNT(*)
                FROM band_condition_activity_station_buckets
                WHERE bucket_start_utc = ? AND band = ? AND is_mobile = 1
            ),
            fixed_unique_stations = (
                SELECT COUNT(*)
                FROM band_condition_activity_station_buckets
                WHERE bucket_start_utc = ? AND band = ? AND is_fixed = 1
            )
        WHERE bucket_start_utc = ? AND band = ?
        """,
        (bucket_start, band, bucket_start, band, bucket_start, band, bucket_start, band),
    )


def _upsert_audibility_bucket(
    connection: sqlite3.Connection,
    bucket_start: str,
    band: str,
    *,
    source_callsign: str,
    source_ssid: str,
) -> None:
    rows = connection.execute(
        """
        SELECT callsign, ssid
        FROM band_condition_reference_stations
        WHERE enabled = 1
          AND band = ?
          AND callsign = ?
          AND ssid = ?
        """,
        (band, normalize_callsign(source_callsign), normalize_ssid(source_ssid)),
    ).fetchall()
    for row in rows:
        station_key = build_station_key(row["callsign"], row["ssid"])
        connection.execute(
            """
            INSERT INTO band_condition_audibility_buckets (
                bucket_start_utc, band, station_key, heard_flag, frame_count
            )
            VALUES (?, ?, ?, 1, 1)
            ON CONFLICT(bucket_start_utc, band, station_key) DO UPDATE SET
                heard_flag = 1,
                frame_count = frame_count + 1
            """,
            (bucket_start, band, station_key),
        )


def _rollup_closed_buckets(connection: sqlite3.Connection, *, current_bucket_utc: str, processed_at: str) -> None:
    activity_band_rows = connection.execute(
        """
        SELECT bucket_start_utc, band
        FROM band_condition_activity_buckets
        WHERE baseline_processed_at IS NULL
          AND bucket_start_utc < ?
        ORDER BY bucket_start_utc ASC
        LIMIT 200
        """,
        (current_bucket_utc,),
    ).fetchall()
    for row in activity_band_rows:
        references = connection.execute(
            """
            SELECT callsign, ssid
            FROM band_condition_reference_stations
            WHERE enabled = 1 AND band = ?
            """,
            (row["band"],),
        ).fetchall()
        for reference in references:
            connection.execute(
                """
                INSERT INTO band_condition_audibility_buckets (
                    bucket_start_utc, band, station_key, heard_flag, frame_count
                )
                VALUES (?, ?, ?, 0, 0)
                ON CONFLICT(bucket_start_utc, band, station_key) DO NOTHING
                """,
                (
                    row["bucket_start_utc"],
                    row["band"],
                    build_station_key(reference["callsign"], reference["ssid"]),
                ),
            )

    audibility_rows = connection.execute(
        """
        SELECT bucket_start_utc, band, station_key, heard_flag
        FROM band_condition_audibility_buckets
        WHERE baseline_processed_at IS NULL
          AND bucket_start_utc < ?
        ORDER BY bucket_start_utc ASC
        LIMIT 200
        """,
        (current_bucket_utc,),
    ).fetchall()
    for row in audibility_rows:
        hour_of_day = hour_of_day_from_utc(row["bucket_start_utc"])
        connection.execute(
            """
            INSERT INTO band_condition_audibility_baseline (
                band, station_key, hour_of_day, sample_count, heard_sum,
                heard_ratio, ema_heard_ratio, updated_at
            )
            VALUES (?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(band, station_key, hour_of_day) DO UPDATE SET
                sample_count = sample_count + 1,
                heard_sum = heard_sum + excluded.heard_sum,
                heard_ratio = (heard_sum + excluded.heard_sum) / (sample_count + 1.0),
                ema_heard_ratio = CASE
                    WHEN ema_heard_ratio IS NULL THEN excluded.ema_heard_ratio
                    ELSE ((1.0 - ?) * ema_heard_ratio) + (? * excluded.ema_heard_ratio)
                END,
                updated_at = excluded.updated_at
            """,
            (
                row["band"],
                row["station_key"],
                hour_of_day,
                float(row["heard_flag"]),
                float(row["heard_flag"]),
                float(row["heard_flag"]),
                processed_at,
                EMA_ALPHA,
                EMA_ALPHA,
            ),
        )
        connection.execute(
            """
            UPDATE band_condition_audibility_buckets
            SET baseline_processed_at = ?
            WHERE bucket_start_utc = ? AND band = ? AND station_key = ?
            """,
            (processed_at, row["bucket_start_utc"], row["band"], row["station_key"]),
        )

    activity_rows = connection.execute(
        """
        SELECT bucket_start_utc, band, mobile_frames, total_frames
        FROM band_condition_activity_buckets
        WHERE baseline_processed_at IS NULL
          AND bucket_start_utc < ?
        ORDER BY bucket_start_utc ASC
        LIMIT 200
        """,
        (current_bucket_utc,),
    ).fetchall()
    for row in activity_rows:
        hour_of_day = hour_of_day_from_utc(row["bucket_start_utc"])
        connection.execute(
            """
            INSERT INTO band_condition_fixed_station_baseline (
                band, station_key, hour_of_day, heard_count, updated_at
            )
            SELECT ?, station_key, ?, 1, ?
            FROM band_condition_activity_station_buckets
            WHERE bucket_start_utc = ?
              AND band = ?
              AND is_fixed = 1
            ON CONFLICT(band, station_key, hour_of_day) DO UPDATE SET
                heard_count = heard_count + 1,
                updated_at = excluded.updated_at
            """,
            (row["band"], hour_of_day, processed_at, row["bucket_start_utc"], row["band"]),
        )
        connection.execute(
            """
            INSERT INTO band_condition_activity_baseline (
                band, hour_of_day, sample_count, avg_mobile_frames, avg_total_frames, updated_at
            )
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(band, hour_of_day) DO UPDATE SET
                avg_mobile_frames = ((avg_mobile_frames * sample_count) + excluded.avg_mobile_frames) / (sample_count + 1.0),
                avg_total_frames = ((avg_total_frames * sample_count) + excluded.avg_total_frames) / (sample_count + 1.0),
                sample_count = sample_count + 1,
                updated_at = excluded.updated_at
            """,
            (row["band"], hour_of_day, float(row["mobile_frames"]), float(row["total_frames"]), processed_at),
        )
        connection.execute(
            """
            UPDATE band_condition_activity_buckets
            SET baseline_processed_at = ?
            WHERE bucket_start_utc = ? AND band = ?
            """,
            (processed_at, row["bucket_start_utc"], row["band"]),
        )


def get_band_condition_snapshot() -> dict[str, Any]:
    bands = _known_bands()
    items = [_build_band_snapshot(band) for band in bands]
    return {
        "generated_at": utc_now(),
        "bands": items,
    }


def get_band_condition_page_data(*, edit_reference_id: int | None = None) -> dict[str, Any]:
    snapshot = get_band_condition_snapshot()
    references = list_reference_stations()
    edit_reference = get_reference_station(edit_reference_id) if edit_reference_id is not None else None
    return {
        "summary": snapshot,
        "bands": snapshot["bands"],
        "references": references,
        "edit_reference": edit_reference,
        "band_options": band_options(),
        "station_type_options": station_type_options(),
        "reference_station_candidates": list_reference_station_candidates(),
        "monitored_band": format_band_label(monitored_band_for_active_modem()),
    }


def _known_bands() -> list[str]:
    rows = fetch_all(
        """
        SELECT DISTINCT band
        FROM modems
        WHERE enabled = 1
          AND TRIM(COALESCE(band, '')) <> ''
        ORDER BY band ASC
        """
    )
    bands = [normalize_band(str(row["band"])) for row in rows if normalize_band(str(row["band"]))]
    return bands or [monitored_band_for_active_modem()]


def _build_band_snapshot(band: str) -> dict[str, Any]:
    normalized_band = normalize_band(band) or "unknown"
    reference_rows = [row for row in list_reference_stations(band=normalized_band) if row["enabled"]]
    reference_count = len(reference_rows)
    if reference_count == 0:
        return _insufficient_band_snapshot(
            normalized_band,
            reference_station_count=0,
            active_reference_station_count=0,
            explanation="No fixed reference stations are configured for this band yet.",
        )

    current_bucket = current_bucket_start()
    window_start = (
        datetime.fromisoformat(current_bucket.replace("Z", "+00:00")) - timedelta(minutes=BUCKET_MINUTES * (CURRENT_WINDOW_BUCKETS - 1))
    ).isoformat()
    baseline_hour = datetime.now(timezone.utc).astimezone().hour

    audibility_rows = fetch_all(
        """
        SELECT station_key, MAX(heard_flag) AS heard_flag, SUM(frame_count) AS frame_count
        FROM band_condition_audibility_buckets
        WHERE band = ?
          AND bucket_start_utc >= ?
          AND bucket_start_utc <= ?
        GROUP BY station_key
        """,
        (normalized_band, window_start, current_bucket),
    )
    audibility_map = {str(row["station_key"]): dict(row) for row in audibility_rows}

    baseline_rows = fetch_all(
        """
        SELECT station_key, hour_of_day, sample_count, heard_ratio, ema_heard_ratio
        FROM band_condition_audibility_baseline
        WHERE band = ?
        """,
        (normalized_band,),
    )
    baseline_by_station_hour = {(str(row["station_key"]), int(row["hour_of_day"])): dict(row) for row in baseline_rows}
    baseline_rows_by_station: dict[str, list[dict[str, Any]]] = {}
    for row in baseline_rows:
        baseline_rows_by_station.setdefault(str(row["station_key"]), []).append(dict(row))
    reference_keys = {str(row["station_key"]) for row in reference_rows}

    activity_rows = fetch_all(
        """
        SELECT total_frames, mobile_frames, total_unique_stations, mobile_unique_stations, fixed_unique_stations
        FROM band_condition_activity_buckets
        WHERE band = ?
          AND bucket_start_utc >= ?
          AND bucket_start_utc <= ?
        ORDER BY bucket_start_utc DESC
        """,
        (normalized_band, window_start, current_bucket),
    )
    activity_baseline_rows = fetch_all(
        """
        SELECT hour_of_day, sample_count, avg_mobile_frames, avg_total_frames
        FROM band_condition_activity_baseline
        WHERE band = ?
        """,
        (normalized_band,),
    )
    current_hour_activity_baseline = next(
        (dict(row) for row in activity_baseline_rows if int(row["hour_of_day"]) == baseline_hour),
        None,
    )
    use_current_hour_activity_baseline = bool(
        current_hour_activity_baseline and int(current_hour_activity_baseline["sample_count"]) >= MIN_BASELINE_SAMPLES
    )
    activity_baseline = _select_activity_baseline(
        activity_baseline_rows,
        current_hour_activity_baseline=current_hour_activity_baseline,
    )
    fixed_station_baseline_rows = fetch_all(
        """
        SELECT station_key, hour_of_day, heard_count
        FROM band_condition_fixed_station_baseline
        WHERE band = ?
        """,
        (normalized_band,),
    )
    fixed_station_baseline_map = _select_fixed_station_baseline_map(
        fixed_station_baseline_rows,
        baseline_hour=baseline_hour,
        use_current_hour=use_current_hour_activity_baseline,
    )
    current_fixed_station_rows = fetch_all(
        """
        SELECT station_key, COUNT(*) AS bucket_hits
        FROM band_condition_activity_station_buckets
        WHERE band = ?
          AND bucket_start_utc >= ?
          AND bucket_start_utc <= ?
          AND is_fixed = 1
        GROUP BY station_key
        ORDER BY bucket_hits DESC, station_key ASC
        """,
        (normalized_band, window_start, current_bucket),
    )

    per_reference: list[dict[str, Any]] = []
    total_weight = 0.0
    current_weight = 0.0
    baseline_weight = 0.0
    active_reference_station_count = 0
    baseline_sample_total = 0

    for reference in reference_rows:
        station_key = reference["station_key"]
        baseline = _select_reference_baseline(
            baseline_by_station_hour=baseline_by_station_hour,
            baseline_rows_by_station=baseline_rows_by_station,
            station_key=station_key,
            baseline_hour=baseline_hour,
        )
        samples = int(baseline["sample_count"]) if baseline else 0
        if samples < MIN_BASELINE_SAMPLES:
            per_reference.append(
                {
                    "station_key": station_key,
                    "station_type": reference["station_type"],
                    "station_type_label": STATION_TYPE_LABELS.get(str(reference["station_type"]), str(reference["station_type"])),
                    "weight": reference["weight"],
                    "current_heard": None,
                    "current_frame_count": int((audibility_map.get(station_key) or {}).get("frame_count") or 0),
                    "baseline_heard_ratio": None,
                    "baseline_sample_count": samples,
                }
            )
            continue

        weight = float(reference["weight"])
        active_reference_station_count += 1
        baseline_sample_total += samples
        current_heard = 1.0 if int((audibility_map.get(station_key) or {}).get("heard_flag") or 0) else 0.0
        baseline_heard_ratio = float(baseline["ema_heard_ratio"] or baseline["heard_ratio"] or 0.0)
        total_weight += weight
        current_weight += weight * current_heard
        baseline_weight += weight * baseline_heard_ratio
        per_reference.append(
            {
                "station_key": station_key,
                "station_type": reference["station_type"],
                "station_type_label": STATION_TYPE_LABELS.get(str(reference["station_type"]), str(reference["station_type"])),
                "weight": weight,
                "current_heard": bool(current_heard),
                "current_frame_count": int((audibility_map.get(station_key) or {}).get("frame_count") or 0),
                "baseline_heard_ratio": round(baseline_heard_ratio, 3),
                "baseline_sample_count": samples,
            }
        )

    if active_reference_station_count == 0 or total_weight <= 0:
        return _insufficient_band_snapshot(
            normalized_band,
            reference_station_count=reference_count,
            active_reference_station_count=0,
            explanation="Historical baseline is still too sparse for this band.",
            per_reference=per_reference,
        )

    current_ratio = current_weight / total_weight
    baseline_ratio = baseline_weight / total_weight
    local_reference_score = _clamp((current_ratio - baseline_ratio) / max(0.25, baseline_ratio), -1.0, 1.0)

    current_mobile_activity = _average_numeric([float(row["mobile_frames"]) for row in activity_rows])
    baseline_mobile_activity = float(activity_baseline["avg_mobile_frames"]) if activity_baseline else 0.0
    current_total_activity = _average_numeric([float(row["total_frames"]) for row in activity_rows])
    baseline_total_activity = float(activity_baseline["avg_total_frames"]) if activity_baseline else 0.0
    baseline_activity_samples = int(activity_baseline["sample_count"]) if activity_baseline else 0
    dx_station_details = _build_dx_station_details(
        current_rows=current_fixed_station_rows,
        reference_keys=reference_keys,
        fixed_station_baseline_map=fixed_station_baseline_map,
        baseline_activity_samples=baseline_activity_samples,
    )
    dx_opening_score = _dx_opening_score(dx_station_details)
    occupancy_score = _occupancy_score(
        current_total_activity=current_total_activity,
        baseline_total_activity=baseline_total_activity,
        current_mobile_activity=current_mobile_activity,
        baseline_mobile_activity=baseline_mobile_activity,
        local_reference_score=local_reference_score,
    )
    condition_score = _condition_score(
        dx_opening_score=dx_opening_score,
        local_reference_score=local_reference_score,
        occupancy_score=occupancy_score,
    )

    confidence_score = _confidence_score(
        configured_reference_count=reference_count,
        active_reference_station_count=active_reference_station_count,
        baseline_sample_total=baseline_sample_total,
        current_bucket_count=len(activity_rows),
        current_total_activity=current_total_activity,
        baseline_activity_samples=baseline_activity_samples,
        dx_station_count=len(dx_station_details),
    )
    label = _label_for_scores(condition_score, confidence_score)
    diagnosis = _diagnosis_for_scores(
        condition_score=condition_score,
        dx_opening_score=dx_opening_score,
        occupancy_score=occupancy_score,
        confidence_score=confidence_score,
    )
    opening_summary = _opening_summary(dx_opening_score)
    load_summary = _load_summary(occupancy_score)
    reference_summary = _reference_summary(local_reference_score)
    why_items = _why_items(
        active_reference_station_count=active_reference_station_count,
        reference_count=reference_count,
        dx_station_count=len(dx_station_details),
        current_mobile_activity=current_mobile_activity,
        baseline_mobile_activity=baseline_mobile_activity,
        current_total_activity=current_total_activity,
        baseline_total_activity=baseline_total_activity,
        local_reference_score=local_reference_score,
    )
    why_item_defs = _why_item_defs(
        active_reference_station_count=active_reference_station_count,
        reference_count=reference_count,
        dx_station_count=len(dx_station_details),
        current_mobile_activity=current_mobile_activity,
        baseline_mobile_activity=baseline_mobile_activity,
        current_total_activity=current_total_activity,
        baseline_total_activity=baseline_total_activity,
        local_reference_score=local_reference_score,
    )
    explanation = _build_explanation(
        local_reference_score=local_reference_score,
        dx_opening_score=dx_opening_score,
        occupancy_score=occupancy_score,
        current_mobile_activity=current_mobile_activity,
        baseline_mobile_activity=baseline_mobile_activity,
        confidence_score=confidence_score,
        active_reference_station_count=active_reference_station_count,
        dx_station_count=len(dx_station_details),
    )
    explanation_parts = _build_explanation_parts(
        local_reference_score=local_reference_score,
        dx_opening_score=dx_opening_score,
        occupancy_score=occupancy_score,
        current_mobile_activity=current_mobile_activity,
        baseline_mobile_activity=baseline_mobile_activity,
        confidence_score=confidence_score,
        active_reference_station_count=active_reference_station_count,
        dx_station_count=len(dx_station_details),
    )

    return {
        "band": normalized_band,
        "band_label": format_band_label(normalized_band),
        "label": label,
        "diagnosis_title": diagnosis["title"],
        "diagnosis_summary": diagnosis["summary"],
        "diagnosis_tone": diagnosis["tone"],
        "condition_score": round(condition_score, 3),
        "occupancy_score": round(occupancy_score, 3),
        "dx_opening_score": round(dx_opening_score, 3),
        "local_reference_score": round(local_reference_score, 3),
        "opening_label": opening_summary["label"],
        "opening_tone": opening_summary["tone"],
        "load_label": load_summary["label"],
        "load_tone": load_summary["tone"],
        "reference_label": reference_summary["label"],
        "reference_tone": reference_summary["tone"],
        "confidence_score": round(confidence_score, 3),
        "reference_station_count": reference_count,
        "active_reference_station_count": active_reference_station_count,
        "current_mobile_activity": round(current_mobile_activity, 2),
        "baseline_mobile_activity": round(baseline_mobile_activity, 2),
        "current_total_activity": round(current_total_activity, 2),
        "baseline_total_activity": round(baseline_total_activity, 2),
        "current_fixed_station_count": len(current_fixed_station_rows),
        "dx_station_count": len(dx_station_details),
        "baseline_activity_samples": baseline_activity_samples,
        "explanation": explanation,
        "explanation_parts": explanation_parts,
        "why_items": why_items,
        "why_item_defs": why_item_defs,
        "per_reference": per_reference,
        "dx_station_details": dx_station_details,
    }


def _insufficient_band_snapshot(
    band: str,
    *,
    reference_station_count: int,
    active_reference_station_count: int,
    explanation: str,
    per_reference: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "band": band,
        "band_label": format_band_label(band),
        "label": "Insufficient data",
        "diagnosis_title": "Band uncertain",
        "diagnosis_summary": "Not enough stable history yet to describe the band confidently.",
        "diagnosis_tone": "caution",
        "condition_score": 0.0,
        "occupancy_score": 0.0,
        "dx_opening_score": 0.0,
        "local_reference_score": 0.0,
        "opening_label": "Unknown",
        "opening_tone": "caution",
        "load_label": "Unknown",
        "load_tone": "caution",
        "reference_label": "Unknown",
        "reference_tone": "caution",
        "confidence_score": 0.0,
        "reference_station_count": reference_station_count,
        "active_reference_station_count": active_reference_station_count,
        "current_mobile_activity": 0.0,
        "baseline_mobile_activity": 0.0,
        "current_total_activity": 0.0,
        "baseline_total_activity": 0.0,
        "current_fixed_station_count": 0,
        "dx_station_count": 0,
        "baseline_activity_samples": 0,
        "explanation": explanation,
        "explanation_parts": [{"message": explanation, "params": {}}],
        "why_items": [],
        "why_item_defs": [],
        "per_reference": per_reference or [],
        "dx_station_details": [],
    }


def _confidence_score(
    *,
    configured_reference_count: int,
    active_reference_station_count: int,
    baseline_sample_total: int,
    current_bucket_count: int,
    current_total_activity: float,
    baseline_activity_samples: int,
    dx_station_count: int,
) -> float:
    if configured_reference_count <= 0 or active_reference_station_count <= 0:
        return 0.0
    configured_factor = min(1.0, configured_reference_count / 6.0)
    active_factor = active_reference_station_count / max(1.0, configured_reference_count)
    sample_factor = min(1.0, baseline_sample_total / (configured_reference_count * 48.0))
    current_factor = min(1.0, current_bucket_count / float(CURRENT_WINDOW_BUCKETS))
    history_factor = min(1.0, baseline_activity_samples / 48.0)
    dx_factor = min(1.0, dx_station_count / 3.0)
    sparse_penalty = 0.18 if current_total_activity <= 0 else 0.0
    confidence = (
        (configured_factor * 0.18)
        + (active_factor * 0.32)
        + (sample_factor * 0.24)
        + (history_factor * 0.16)
        + (current_factor * 0.1)
    )
    confidence += dx_factor * 0.05
    return _clamp(confidence - sparse_penalty, 0.0, 1.0)


def _label_for_scores(condition_score: float, confidence_score: float) -> str:
    if confidence_score < INSUFFICIENT_CONFIDENCE:
        return "Insufficient data"
    if condition_score <= -0.55:
        return "Poor"
    if condition_score <= -0.18:
        return "Below normal"
    if condition_score < 0.18:
        return "Normal"
    if condition_score < 0.55:
        return "Good"
    return "Enhanced"


def _build_explanation(
    *,
    local_reference_score: float,
    dx_opening_score: float,
    occupancy_score: float,
    current_mobile_activity: float,
    baseline_mobile_activity: float,
    confidence_score: float,
    active_reference_station_count: int,
    dx_station_count: int,
) -> str:
    parts = _build_explanation_parts(
        local_reference_score=local_reference_score,
        dx_opening_score=dx_opening_score,
        occupancy_score=occupancy_score,
        current_mobile_activity=current_mobile_activity,
        baseline_mobile_activity=baseline_mobile_activity,
        confidence_score=confidence_score,
        active_reference_station_count=active_reference_station_count,
        dx_station_count=dx_station_count,
    )
    rendered: list[str] = []
    for part in parts:
        message = str(part.get("message") or "")
        params = dict(part.get("params") or {})
        if params:
            rendered.append(message.format(**params))
        else:
            rendered.append(message)
    return " ".join(rendered)


def _build_explanation_parts(
    *,
    local_reference_score: float,
    dx_opening_score: float,
    occupancy_score: float,
    current_mobile_activity: float,
    baseline_mobile_activity: float,
    confidence_score: float,
    active_reference_station_count: int,
    dx_station_count: int,
) -> list[dict[str, Any]]:
    reference_phrase = "local reference audibility is near normal"
    if local_reference_score <= -0.45:
        reference_phrase = "local reference audibility is clearly below normal"
    elif local_reference_score <= -0.12:
        reference_phrase = "local reference audibility is slightly below normal"
    elif local_reference_score >= 0.45:
        reference_phrase = "local reference audibility is clearly above normal"
    elif local_reference_score >= 0.12:
        reference_phrase = "local reference audibility is slightly above normal"

    dx_phrase = "no unusual fixed-station opening is visible"
    if dx_station_count > 0 and dx_opening_score >= 0.6:
        dx_phrase = f"{dx_station_count} rare fixed stations are currently present, which strongly suggests wider propagation"
    elif dx_station_count > 0 and dx_opening_score >= 0.25:
        dx_phrase = f"{dx_station_count} less-common fixed stations are currently present, which suggests some opening"

    occupancy_phrase = "channel occupancy looks close to normal"
    if occupancy_score >= 0.65:
        occupancy_phrase = "channel occupancy looks elevated, so local overload may be affecting what is heard"
    elif occupancy_score >= 0.3:
        occupancy_phrase = "channel occupancy is somewhat elevated"
    elif baseline_mobile_activity <= 0 and current_mobile_activity > 0:
        occupancy_phrase = "mobile traffic is present but the long-term occupancy baseline is still thin"

    confidence_phrase = "low confidence"
    if confidence_score >= 0.7:
        confidence_phrase = "high confidence"
    elif confidence_score >= 0.45:
        confidence_phrase = "moderate confidence"

    return [
        {"message": f"{reference_phrase}.", "params": {}},
        {"message": f"{dx_phrase}.", "params": {}},
        {"message": f"{occupancy_phrase}.", "params": {}},
        {
            "message": "Estimate uses {active_reference_station_count} baseline-backed reference stations with {confidence_phrase}.",
            "params": {
                "active_reference_station_count": active_reference_station_count,
                "confidence_phrase": confidence_phrase,
            },
        },
    ]


def _build_dx_station_details(
    *,
    current_rows: list[dict[str, Any]],
    reference_keys: set[str],
    fixed_station_baseline_map: dict[str, int],
    baseline_activity_samples: int,
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    if baseline_activity_samples < MIN_BASELINE_SAMPLES:
        return details
    for row in current_rows:
        station_key = str(row["station_key"])
        if station_key in reference_keys:
            continue
        heard_count = int(fixed_station_baseline_map.get(station_key, 0))
        baseline_ratio = heard_count / float(max(1, baseline_activity_samples))
        rarity_score = _dx_station_score(baseline_ratio, heard_count)
        if rarity_score <= 0:
            continue
        details.append(
            {
                "station_key": station_key,
                "bucket_hits": int(row["bucket_hits"]),
                "baseline_heard_count": heard_count,
                "baseline_heard_ratio": round(baseline_ratio, 3),
                "rarity_score": round(rarity_score, 3),
            }
        )
    details.sort(key=lambda item: (-float(item["rarity_score"]), -int(item["bucket_hits"]), str(item["station_key"])))
    return details[:8]


def _select_reference_baseline(
    *,
    baseline_by_station_hour: dict[tuple[str, int], dict[str, Any]],
    baseline_rows_by_station: dict[str, list[dict[str, Any]]],
    station_key: str,
    baseline_hour: int,
) -> dict[str, Any] | None:
    current_hour_row = baseline_by_station_hour.get((station_key, baseline_hour))
    if current_hour_row and int(current_hour_row["sample_count"]) >= MIN_BASELINE_SAMPLES:
        return current_hour_row
    rows = baseline_rows_by_station.get(station_key, [])
    if not rows:
        return current_hour_row
    total_samples = sum(int(row["sample_count"]) for row in rows)
    if total_samples <= 0:
        return current_hour_row
    heard_ratio = sum(float(row["heard_ratio"]) * int(row["sample_count"]) for row in rows) / float(total_samples)
    ema_candidates = [row for row in rows if row.get("ema_heard_ratio") is not None]
    ema_ratio = None
    if ema_candidates:
        ema_weight = sum(int(row["sample_count"]) for row in ema_candidates)
        if ema_weight > 0:
            ema_ratio = sum(float(row["ema_heard_ratio"]) * int(row["sample_count"]) for row in ema_candidates) / float(ema_weight)
    return {
        "sample_count": total_samples,
        "heard_ratio": heard_ratio,
        "ema_heard_ratio": ema_ratio,
    }


def _select_activity_baseline(
    rows: list[dict[str, Any]],
    *,
    current_hour_activity_baseline: dict[str, Any] | None,
) -> dict[str, Any] | None:
    current_hour_row = current_hour_activity_baseline
    if current_hour_row and int(current_hour_row["sample_count"]) >= MIN_BASELINE_SAMPLES:
        return current_hour_row
    if not rows:
        return current_hour_row
    total_samples = sum(int(row["sample_count"]) for row in rows)
    if total_samples <= 0:
        return current_hour_row
    return {
        "sample_count": total_samples,
        "avg_mobile_frames": sum(float(row["avg_mobile_frames"]) * int(row["sample_count"]) for row in rows) / float(total_samples),
        "avg_total_frames": sum(float(row["avg_total_frames"]) * int(row["sample_count"]) for row in rows) / float(total_samples),
    }


def _select_fixed_station_baseline_map(
    rows: list[dict[str, Any]],
    *,
    baseline_hour: int,
    use_current_hour: bool,
) -> dict[str, int]:
    current_hour_rows = [dict(row) for row in rows if int(row["hour_of_day"]) == baseline_hour]
    if use_current_hour and current_hour_rows:
        station_map = {str(row["station_key"]): int(row["heard_count"]) for row in current_hour_rows}
        if station_map:
            return station_map
    station_map: dict[str, int] = {}
    for row in rows:
        station_key = str(row["station_key"])
        station_map[station_key] = station_map.get(station_key, 0) + int(row["heard_count"])
    return station_map


def _dx_station_score(baseline_ratio: float, heard_count: int) -> float:
    if heard_count <= 0:
        return 1.0
    return _clamp((DX_RARE_STATION_RATIO - baseline_ratio) / DX_RARE_STATION_RATIO, 0.0, 1.0)


def _dx_opening_score(dx_station_details: list[dict[str, Any]]) -> float:
    if not dx_station_details:
        return 0.0
    station_scores = [float(item["rarity_score"]) for item in dx_station_details]
    coverage_factor = min(1.0, len(station_scores) / 3.0)
    return _clamp(_average_numeric(station_scores) * coverage_factor, 0.0, 1.0)


def _occupancy_score(
    *,
    current_total_activity: float,
    baseline_total_activity: float,
    current_mobile_activity: float,
    baseline_mobile_activity: float,
    local_reference_score: float,
) -> float:
    total_pressure = _clamp((current_total_activity - baseline_total_activity) / max(3.0, baseline_total_activity), -1.0, 1.0)
    mobile_pressure = _clamp((current_mobile_activity - baseline_mobile_activity) / max(2.0, baseline_mobile_activity), -1.0, 1.0)
    reference_penalty = max(0.0, -local_reference_score)
    return _clamp((max(0.0, total_pressure) * 0.45) + (max(0.0, mobile_pressure) * 0.35) + (reference_penalty * 0.2), 0.0, 1.0)


def _condition_score(*, dx_opening_score: float, local_reference_score: float, occupancy_score: float) -> float:
    occupancy_penalty = occupancy_score * max(0.15, 0.4 - (dx_opening_score * 0.25))
    return _clamp((dx_opening_score * 0.65) + (local_reference_score * 0.35) - occupancy_penalty, -1.0, 1.0)


def _diagnosis_for_scores(
    *,
    condition_score: float,
    dx_opening_score: float,
    occupancy_score: float,
    confidence_score: float,
) -> dict[str, str]:
    if confidence_score < INSUFFICIENT_CONFIDENCE:
        return {
            "title": "Band uncertain",
            "summary": "History is still too thin to classify the band confidently.",
            "tone": "caution",
        }
    if dx_opening_score >= 0.7 and condition_score >= 0.25:
        return {
            "title": "Band open",
            "summary": "Rare fixed stations are present and propagation looks wider than normal.",
            "tone": "good",
        }
    if occupancy_score >= 0.65 and dx_opening_score < 0.35:
        return {
            "title": "Band busy locally",
            "summary": "Traffic load is elevated and there is little evidence of a wider opening.",
            "tone": "busy",
        }
    if condition_score <= -0.2:
        return {
            "title": "Band degraded",
            "summary": "Local references are underperforming and the band looks worse than usual.",
            "tone": "bad",
        }
    if condition_score >= 0.2:
        return {
            "title": "Band above normal",
            "summary": "References are healthy and there are signs of better-than-normal reach.",
            "tone": "good",
        }
    return {
        "title": "Band normal",
        "summary": "Current hearing pattern is close to the usual local baseline.",
        "tone": "neutral",
    }


def _opening_summary(score: float) -> dict[str, str]:
    if score >= 0.8:
        return {"label": "Very strong", "tone": "good"}
    if score >= 0.55:
        return {"label": "Strong", "tone": "good"}
    if score >= 0.3:
        return {"label": "Noticeable", "tone": "neutral"}
    if score >= 0.12:
        return {"label": "Weak", "tone": "caution"}
    return {"label": "Quiet", "tone": "muted"}


def _load_summary(score: float) -> dict[str, str]:
    if score >= 0.72:
        return {"label": "High", "tone": "bad"}
    if score >= 0.45:
        return {"label": "Moderate", "tone": "caution"}
    if score >= 0.2:
        return {"label": "Light", "tone": "neutral"}
    return {"label": "Low", "tone": "good"}


def _reference_summary(score: float) -> dict[str, str]:
    if score >= 0.4:
        return {"label": "Above normal", "tone": "good"}
    if score >= 0.1:
        return {"label": "Healthy", "tone": "good"}
    if score > -0.12:
        return {"label": "Near normal", "tone": "neutral"}
    if score > -0.4:
        return {"label": "Weak", "tone": "caution"}
    return {"label": "Poor", "tone": "bad"}


def _why_items(
    *,
    active_reference_station_count: int,
    reference_count: int,
    dx_station_count: int,
    current_mobile_activity: float,
    baseline_mobile_activity: float,
    current_total_activity: float,
    baseline_total_activity: float,
    local_reference_score: float,
) -> list[str]:
    items = _why_item_defs(
        active_reference_station_count=active_reference_station_count,
        reference_count=reference_count,
        dx_station_count=dx_station_count,
        current_mobile_activity=current_mobile_activity,
        baseline_mobile_activity=baseline_mobile_activity,
        current_total_activity=current_total_activity,
        baseline_total_activity=baseline_total_activity,
        local_reference_score=local_reference_score,
    )
    rendered: list[str] = []
    for item in items:
        message = str(item.get("message") or "")
        params = dict(item.get("params") or {})
        if params:
            rendered.append(message.format(**params))
        else:
            rendered.append(message)
    return rendered[:4]


def _why_item_defs(
    *,
    active_reference_station_count: int,
    reference_count: int,
    dx_station_count: int,
    current_mobile_activity: float,
    baseline_mobile_activity: float,
    current_total_activity: float,
    baseline_total_activity: float,
    local_reference_score: float,
) -> list[dict[str, Any]]:
    items: list[str] = []
    items.append(
        {
            "message": "{active_reference_station_count}/{reference_count} local references are baseline-backed",
            "params": {
                "active_reference_station_count": active_reference_station_count,
                "reference_count": reference_count,
            },
        }
    )
    if dx_station_count > 0:
        items.append(
            {
                "message": "{dx_station_count} rare fixed stations are present now",
                "params": {"dx_station_count": dx_station_count},
            }
        )
    else:
        items.append({"message": "No rare fixed stations are visible right now", "params": {}})
    if current_total_activity > baseline_total_activity * 1.35 and current_total_activity > 0:
        items.append({"message": "Total traffic is above its normal level", "params": {}})
    elif current_total_activity < baseline_total_activity * 0.75 and baseline_total_activity > 0:
        items.append({"message": "Total traffic is below its normal level", "params": {}})
    else:
        items.append({"message": "Total traffic is close to its normal level", "params": {}})
    if current_mobile_activity > baseline_mobile_activity * 1.35 and current_mobile_activity > 0:
        items.append({"message": "Mobile traffic suggests elevated local channel load", "params": {}})
    elif local_reference_score >= 0.1:
        items.append({"message": "Local references are being heard at or above their normal level", "params": {}})
    else:
        items.append({"message": "Local references are not outperforming their usual baseline", "params": {}})
    return items[:4]


def _average_numeric(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
