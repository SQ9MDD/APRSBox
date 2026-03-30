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
FIXED_REFERENCE_STATION_TYPES = ("home", "digi", "igate", "wx-fixed", "fixed")


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
    return [
        {"value": "home", "label": "Home"},
        {"value": "digi", "label": "DIGI"},
        {"value": "igate", "label": "iGate"},
        {"value": "wx-fixed", "label": "WX Fixed"},
        {"value": "fixed", "label": "Other Fixed"},
    ]


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
    return dict(row) if row else None


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
        WHERE enabled = 1 AND modem_type = 'TCP'
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

    bucket_band = normalize_band(band or "") or "unknown"
    bucket_start = current_bucket_start()
    classification = parsed["classification"]
    source_station_key = build_station_key(parsed["source_callsign"], parsed["source_ssid"])
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
            source_callsign=parsed["source_callsign"],
            source_ssid=parsed["source_ssid"],
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
        "station_type_options": station_type_options(),
        "monitored_band": format_band_label(monitored_band_for_active_modem()),
    }


def _known_bands() -> list[str]:
    rows = fetch_all(
        """
        SELECT band
        FROM (
            SELECT DISTINCT band FROM band_condition_reference_stations WHERE enabled = 1
            UNION
            SELECT DISTINCT band FROM modems WHERE enabled = 1 AND TRIM(COALESCE(band, '')) <> ''
            UNION
            SELECT DISTINCT band FROM band_condition_activity_buckets
        )
        WHERE TRIM(COALESCE(band, '')) <> ''
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
        SELECT station_key, sample_count, heard_ratio, ema_heard_ratio
        FROM band_condition_audibility_baseline
        WHERE band = ?
          AND hour_of_day = ?
        """,
        (normalized_band, baseline_hour),
    )
    baseline_map = {str(row["station_key"]): dict(row) for row in baseline_rows}

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
    activity_baseline = fetch_one(
        """
        SELECT sample_count, avg_mobile_frames, avg_total_frames
        FROM band_condition_activity_baseline
        WHERE band = ?
          AND hour_of_day = ?
        """,
        (normalized_band, baseline_hour),
    )

    per_reference: list[dict[str, Any]] = []
    total_weight = 0.0
    current_weight = 0.0
    baseline_weight = 0.0
    active_reference_station_count = 0
    baseline_sample_total = 0

    for reference in reference_rows:
        station_key = reference["station_key"]
        baseline = baseline_map.get(station_key)
        samples = int(baseline["sample_count"]) if baseline else 0
        if samples < MIN_BASELINE_SAMPLES:
            per_reference.append(
                {
                    "station_key": station_key,
                    "station_type": reference["station_type"],
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
    raw_condition_score = _clamp((current_ratio - baseline_ratio) / max(0.25, baseline_ratio), -1.0, 1.0)

    current_mobile_activity = _average_numeric([float(row["mobile_frames"]) for row in activity_rows])
    baseline_mobile_activity = float(activity_baseline["avg_mobile_frames"]) if activity_baseline else 0.0
    current_total_activity = _average_numeric([float(row["total_frames"]) for row in activity_rows])
    baseline_total_activity = float(activity_baseline["avg_total_frames"]) if activity_baseline else 0.0
    congestion_ratio = current_mobile_activity / max(1.0, baseline_mobile_activity)
    congestion_score = _clamp((congestion_ratio - 1.0) / 2.0, -1.0, 1.0)

    condition_score = raw_condition_score
    if condition_score < 0 and congestion_score > 0:
        condition_score = min(0.0, condition_score + min(0.3, congestion_score * 0.25))

    confidence_score = _confidence_score(
        configured_reference_count=reference_count,
        active_reference_station_count=active_reference_station_count,
        baseline_sample_total=baseline_sample_total,
        current_bucket_count=len(activity_rows),
        current_total_activity=current_total_activity,
        congestion_score=congestion_score,
    )
    label = _label_for_scores(condition_score, confidence_score)
    explanation = _build_explanation(
        current_ratio=current_ratio,
        baseline_ratio=baseline_ratio,
        current_mobile_activity=current_mobile_activity,
        baseline_mobile_activity=baseline_mobile_activity,
        confidence_score=confidence_score,
        active_reference_station_count=active_reference_station_count,
    )

    return {
        "band": normalized_band,
        "band_label": format_band_label(normalized_band),
        "label": label,
        "condition_score": round(condition_score, 3),
        "congestion_score": round(congestion_score, 3),
        "confidence_score": round(confidence_score, 3),
        "reference_station_count": reference_count,
        "active_reference_station_count": active_reference_station_count,
        "current_mobile_activity": round(current_mobile_activity, 2),
        "baseline_mobile_activity": round(baseline_mobile_activity, 2),
        "current_total_activity": round(current_total_activity, 2),
        "baseline_total_activity": round(baseline_total_activity, 2),
        "explanation": explanation,
        "per_reference": per_reference,
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
        "condition_score": 0.0,
        "congestion_score": 0.0,
        "confidence_score": 0.0,
        "reference_station_count": reference_station_count,
        "active_reference_station_count": active_reference_station_count,
        "current_mobile_activity": 0.0,
        "baseline_mobile_activity": 0.0,
        "current_total_activity": 0.0,
        "baseline_total_activity": 0.0,
        "explanation": explanation,
        "per_reference": per_reference or [],
    }


def _confidence_score(
    *,
    configured_reference_count: int,
    active_reference_station_count: int,
    baseline_sample_total: int,
    current_bucket_count: int,
    current_total_activity: float,
    congestion_score: float,
) -> float:
    if configured_reference_count <= 0 or active_reference_station_count <= 0:
        return 0.0
    configured_factor = min(1.0, configured_reference_count / 6.0)
    active_factor = active_reference_station_count / max(1.0, configured_reference_count)
    sample_factor = min(1.0, baseline_sample_total / (configured_reference_count * 48.0))
    current_factor = min(1.0, current_bucket_count / float(CURRENT_WINDOW_BUCKETS))
    sparse_penalty = 0.18 if current_total_activity <= 0 else 0.0
    congestion_penalty = max(0.0, congestion_score) * 0.18
    confidence = (configured_factor * 0.2) + (active_factor * 0.35) + (sample_factor * 0.3) + (current_factor * 0.15)
    return _clamp(confidence - sparse_penalty - congestion_penalty, 0.0, 1.0)


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
    current_ratio: float,
    baseline_ratio: float,
    current_mobile_activity: float,
    baseline_mobile_activity: float,
    confidence_score: float,
    active_reference_station_count: int,
) -> str:
    audibility_phrase = "near normal"
    if current_ratio < baseline_ratio - 0.2:
        audibility_phrase = "well below the long-term fixed-station baseline"
    elif current_ratio < baseline_ratio - 0.08:
        audibility_phrase = "below the long-term fixed-station baseline"
    elif current_ratio > baseline_ratio + 0.2:
        audibility_phrase = "well above the long-term fixed-station baseline"
    elif current_ratio > baseline_ratio + 0.08:
        audibility_phrase = "above the long-term fixed-station baseline"

    congestion_phrase = "mobile traffic is close to normal"
    if current_mobile_activity > baseline_mobile_activity * 1.6 and current_mobile_activity > 0:
        congestion_phrase = "mobile traffic is unusually high, so degraded audibility is treated more cautiously"
    elif baseline_mobile_activity <= 0 and current_mobile_activity > 0:
        congestion_phrase = "mobile traffic is present but the long-term congestion baseline is still thin"

    confidence_phrase = "low confidence"
    if confidence_score >= 0.7:
        confidence_phrase = "high confidence"
    elif confidence_score >= 0.45:
        confidence_phrase = "moderate confidence"

    return (
        f"Fixed reference audibility is {audibility_phrase}. "
        f"{congestion_phrase}. "
        f"Estimate uses {active_reference_station_count} baseline-backed reference stations with {confidence_phrase}."
    )


def _average_numeric(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
