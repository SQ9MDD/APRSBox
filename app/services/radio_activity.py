from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.db import fetch_all, fetch_one, get_connection, log_event, utc_now
from app.services.aprs_device_identification import get_aprs_device_identification_database, lookup_aprs_device_identification
from app.services.band_condition import (
    aggregate_band_condition_parsed_bucket,
    finalize_band_condition_hours,
    is_band_condition_enabled,
)
from app.services.content import parse_tnc2_frame
from app.services.traffic_source import STATISTICS_TRAFFIC_SQL_PREDICATE


RADIO_ACTIVITY_BUCKET_MINUTES = 5
RADIO_ACTIVITY_STATE_KEY_DEFAULT = "radio_activity_5m.default"
RADIO_ACTIVITY_RETENTION_DAYS = 365
RADIO_ACTIVITY_RANGE_1H = "1h"
RADIO_ACTIVITY_RANGE_3H = "3h"
RADIO_ACTIVITY_RANGE_6H = "6h"
RADIO_ACTIVITY_RANGE_12H = "12h"
RADIO_ACTIVITY_RANGE_24H = "24h"
RADIO_ACTIVITY_RANGE_7D = "7d"
RADIO_ACTIVITY_RANGE_30D = "30d"
RADIO_ACTIVITY_RANGE_365D = "365d"
RADIO_ACTIVITY_RANGE_OPTIONS = {
    RADIO_ACTIVITY_RANGE_1H: 60,
    RADIO_ACTIVITY_RANGE_3H: 3 * 60,
    RADIO_ACTIVITY_RANGE_6H: 6 * 60,
    RADIO_ACTIVITY_RANGE_12H: 12 * 60,
    RADIO_ACTIVITY_RANGE_24H: 24 * 60,
    RADIO_ACTIVITY_RANGE_7D: 7 * 24 * 60,
    RADIO_ACTIVITY_RANGE_30D: 30 * 24 * 60,
    RADIO_ACTIVITY_RANGE_365D: 365 * 24 * 60,
}
RADIO_ACTIVITY_DOWNSAMPLE_MAX_POINTS = 1200
RADIO_ACTIVITY_DOWNSAMPLE_STEPS_MINUTES = (5, 10, 15, 30, 60, 120, 180, 360, 720, 1440)
TRAFFIC_STATISTICS_RANGE_6H = "6h"
TRAFFIC_STATISTICS_RANGE_1H = "1h"
TRAFFIC_STATISTICS_RANGE_24H = "24h"
TRAFFIC_STATISTICS_RANGE_7D = "7d"
TRAFFIC_STATISTICS_RANGE_30D = "30d"
TRAFFIC_STATISTICS_RANGE_365D = "365d"
TRAFFIC_STATISTICS_RANGE_OPTIONS = {
    TRAFFIC_STATISTICS_RANGE_1H: 60,
    TRAFFIC_STATISTICS_RANGE_6H: 6 * 60,
    TRAFFIC_STATISTICS_RANGE_24H: 24 * 60,
    TRAFFIC_STATISTICS_RANGE_7D: 7 * 24 * 60,
    TRAFFIC_STATISTICS_RANGE_30D: 30 * 24 * 60,
    TRAFFIC_STATISTICS_RANGE_365D: 365 * 24 * 60,
}
TRAFFIC_STATISTICS_DEVICES_DEFAULT_TOP_LIMIT = 20
TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY = "unknown"
TRAFFIC_STATISTICS_DEVICES_UNKNOWN_LABEL = "Unknown"
TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_KEY = "mixed_unknown"
TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_LABEL = "Mixed / Unknown"
TRAFFIC_STATISTICS_DEVICES_OTHER_KEY = "other"
TRAFFIC_STATISTICS_DEVICES_OTHER_LABEL = "Other"
TRAFFIC_STATISTICS_TOCALL_UNKNOWN = "UNKNOWN"
_TRAFFIC_STATISTICS_TOCALL_RE = re.compile(r"^AP[A-Z0-9]{2,5}$")
_TRAFFIC_STATISTICS_TOCALL_NON_AP_ALLOWED = frozenset({"PSKAPR"})
TRAFFIC_STATISTICS_USERS_DEFAULT_TOP_LIMIT = 20
_SOURCE_BUCKET_DEFAULTS: dict[str, int | None] = {
    "rx_total": 0,
    "tx_total": 0,
    "digipeated_total": 0,
    "own_frames_total": 0,
    "messages_total": 0,
    "queries_total": 0,
    "objects_total": 0,
    "wx_total": 0,
    "position_total": 0,
    "mobile_total": 0,
    "fixed_total": 0,
    "unique_stations_total": 0,
    "direct_heard_total": 0,
    "indirect_heard_total": 0,
    "rfonly_total": 0,
    "nogate_total": 0,
    "invalid_total": 0,
    "parse_error_total": 0,
    # Placeholder for future normalized deduplication metadata.
    "duplicate_total": 0,
    "type_position_total": 0,
    "type_weather_total": 0,
    "type_message_total": 0,
    "type_object_item_total": 0,
    "type_status_total": 0,
    "type_telemetry_total": 0,
    "type_query_total": 0,
    "type_user_defined_total": 0,
    "type_third_party_total": 0,
    "type_other_unknown_total": 0,
    "max_hops_seen": None,
    "avg_hops": None,
}


class RadioActivityAggregatorService:
    def __init__(
        self,
        *,
        poll_interval: float = 300.0,
        bucket_minutes: int = RADIO_ACTIVITY_BUCKET_MINUTES,
        safety_delay_seconds: int = 45,
        state_key: str = RADIO_ACTIVITY_STATE_KEY_DEFAULT,
    ) -> None:
        self._poll_interval = float(poll_interval)
        self._bucket_minutes = max(1, int(bucket_minutes))
        self._safety_delay_seconds = max(0, int(safety_delay_seconds))
        self._state_key = str(state_key or RADIO_ACTIVITY_STATE_KEY_DEFAULT).strip() or RADIO_ACTIVITY_STATE_KEY_DEFAULT
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="aprsbox-radio-activity-aggregator")

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

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.to_thread(
                run_radio_activity_aggregation,
                state_key=self._state_key,
                bucket_minutes=self._bucket_minutes,
                safety_delay_seconds=self._safety_delay_seconds,
            )
            await self._sleep(self._poll_interval)

    async def _sleep(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=max(0.0, delay))
        except TimeoutError:
            pass


def run_radio_activity_aggregation(
    *,
    state_key: str = RADIO_ACTIVITY_STATE_KEY_DEFAULT,
    bucket_minutes: int = RADIO_ACTIVITY_BUCKET_MINUTES,
    safety_delay_seconds: int = 45,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    normalized_state_key = str(state_key or RADIO_ACTIVITY_STATE_KEY_DEFAULT).strip() or RADIO_ACTIVITY_STATE_KEY_DEFAULT
    normalized_bucket_minutes = max(1, int(bucket_minutes))
    normalized_safety_delay_seconds = max(0, int(safety_delay_seconds))
    now = _normalize_utc_datetime(now_utc or datetime.now(timezone.utc))
    band_condition_enabled = is_band_condition_enabled()
    _prune_radio_activity_history(now_utc=now)
    latest_closed_bucket_start = _latest_closed_bucket_start(
        now_utc=now,
        bucket_minutes=normalized_bucket_minutes,
        safety_delay_seconds=normalized_safety_delay_seconds,
    )
    state_row = _get_aggregator_state(normalized_state_key)
    current_last_processed = _parse_iso_timestamp_utc(str((state_row or {}).get("last_processed_bucket_start_utc") or ""))
    last_processed_for_state = current_last_processed
    processed_buckets = 0

    if latest_closed_bucket_start is None:
        if band_condition_enabled:
            finalize_band_condition_hours(now_utc=now)
        _upsert_aggregator_state(
            normalized_state_key,
            last_processed_bucket_start_utc=_iso_or_none(last_processed_for_state),
            last_run_utc=now.isoformat(),
            last_error=None,
        )
        return {
            "processed_buckets": 0,
            "last_processed_bucket_start_utc": _iso_or_none(last_processed_for_state),
            "latest_closed_bucket_start_utc": None,
        }

    if current_last_processed is None:
        next_bucket_start = _oldest_closed_bucket_start(
            latest_closed_bucket_start_utc=latest_closed_bucket_start,
            bucket_minutes=normalized_bucket_minutes,
        )
    else:
        next_bucket_start = current_last_processed + timedelta(minutes=normalized_bucket_minutes)

    if next_bucket_start is None or next_bucket_start > latest_closed_bucket_start:
        if band_condition_enabled:
            finalize_band_condition_hours(now_utc=now)
        _upsert_aggregator_state(
            normalized_state_key,
            last_processed_bucket_start_utc=_iso_or_none(last_processed_for_state),
            last_run_utc=now.isoformat(),
            last_error=None,
        )
        return {
            "processed_buckets": 0,
            "last_processed_bucket_start_utc": _iso_or_none(last_processed_for_state),
            "latest_closed_bucket_start_utc": latest_closed_bucket_start.isoformat(),
        }

    current_bucket_start = next_bucket_start
    try:
        while current_bucket_start <= latest_closed_bucket_start:
            current_bucket_end = current_bucket_start + timedelta(minutes=normalized_bucket_minutes)
            source_rows, band_frame_rows = _collect_bucket_source_rows(
                bucket_start_utc=current_bucket_start,
                bucket_end_utc=current_bucket_end,
                collect_band_condition=band_condition_enabled,
            )
            _upsert_radio_activity_bucket_rows(
                bucket_start_utc=current_bucket_start,
                bucket_end_utc=current_bucket_end,
                source_rows=source_rows,
            )
            if band_condition_enabled:
                aggregate_band_condition_parsed_bucket(
                    bucket_start_utc=current_bucket_start,
                    parsed_frame_rows=band_frame_rows,
                )
            processed_buckets += 1
            last_processed_for_state = current_bucket_start
            current_bucket_start = current_bucket_end

        if band_condition_enabled:
            finalize_band_condition_hours(now_utc=now)
        _upsert_aggregator_state(
            normalized_state_key,
            last_processed_bucket_start_utc=_iso_or_none(last_processed_for_state),
            last_run_utc=now.isoformat(),
            last_error=None,
        )
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        _upsert_aggregator_state(
            normalized_state_key,
            last_processed_bucket_start_utc=_iso_or_none(last_processed_for_state),
            last_run_utc=now.isoformat(),
            last_error=message,
        )
        log_event("WARNING", "radio_activity", f"Radio activity aggregation failed: {message}")
        return {
            "processed_buckets": processed_buckets,
            "last_processed_bucket_start_utc": _iso_or_none(last_processed_for_state),
            "latest_closed_bucket_start_utc": latest_closed_bucket_start.isoformat(),
            "error": message,
        }

    return {
        "processed_buckets": processed_buckets,
        "last_processed_bucket_start_utc": _iso_or_none(last_processed_for_state),
        "latest_closed_bucket_start_utc": latest_closed_bucket_start.isoformat(),
    }


def get_dashboard_radio_activity(*, range_value: str = RADIO_ACTIVITY_RANGE_24H) -> dict[str, Any]:
    normalized_range = str(range_value or RADIO_ACTIVITY_RANGE_24H).strip().lower()
    if normalized_range not in RADIO_ACTIVITY_RANGE_OPTIONS:
        raise ValueError("Unsupported range.")

    base_bucket_minutes = RADIO_ACTIVITY_BUCKET_MINUTES
    total_minutes = RADIO_ACTIVITY_RANGE_OPTIONS[normalized_range]
    output_bucket_minutes = _resolve_output_bucket_minutes(total_minutes)
    output_bucket_delta = timedelta(minutes=output_bucket_minutes)
    output_bucket_seconds = output_bucket_minutes * 60
    output_bucket_count = max(1, (total_minutes + output_bucket_minutes - 1) // output_bucket_minutes)
    now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    latest_base_bucket_start = _floor_to_bucket_start(now_utc, bucket_minutes=base_bucket_minutes) - timedelta(
        minutes=base_bucket_minutes
    )
    latest_output_bucket_start = _floor_to_bucket_start(latest_base_bucket_start, bucket_minutes=output_bucket_minutes)
    window_start_utc = latest_output_bucket_start - timedelta(minutes=output_bucket_minutes * (output_bucket_count - 1))
    window_end_utc = latest_output_bucket_start + output_bucket_delta

    rows = fetch_all(
        """
        SELECT
            CAST((CAST(strftime('%s', bucket_start_utc) AS INTEGER) / ?) AS INTEGER) * ? AS bucket_epoch,
            SUM(rx_total) AS rx_total,
            SUM(tx_total) AS tx_total,
            SUM(digipeated_total) AS digipeated_total,
            SUM(own_frames_total) AS own_frames_total,
            SUM(messages_total) AS messages_total,
            SUM(queries_total) AS queries_total,
            SUM(objects_total) AS objects_total,
            SUM(wx_total) AS wx_total,
            SUM(position_total) AS position_total,
            SUM(mobile_total) AS mobile_total,
            SUM(fixed_total) AS fixed_total,
            SUM(unique_stations_total) AS unique_stations_total,
            SUM(direct_heard_total) AS direct_heard_total,
            SUM(indirect_heard_total) AS indirect_heard_total,
            SUM(rfonly_total) AS rfonly_total,
            SUM(nogate_total) AS nogate_total,
            SUM(invalid_total) AS invalid_total,
            SUM(parse_error_total) AS parse_error_total,
            SUM(duplicate_total) AS duplicate_total
        FROM radio_activity_5m
        WHERE bucket_start_utc >= ?
          AND bucket_start_utc < ?
        GROUP BY bucket_epoch
        ORDER BY bucket_epoch ASC
        """,
        (output_bucket_seconds, output_bucket_seconds, window_start_utc.isoformat(), window_end_utc.isoformat()),
    )
    row_by_bucket_start: dict[str, dict[str, Any]] = {}
    for row in rows:
        epoch_raw = row["bucket_epoch"]
        try:
            epoch_value = int(epoch_raw)
        except (TypeError, ValueError):
            continue
        bucket_start_utc = datetime.fromtimestamp(epoch_value, tz=timezone.utc)
        row_by_bucket_start[bucket_start_utc.isoformat()] = dict(row)

    aprsis_rows = fetch_all(
        """
        SELECT
            CAST((CAST(strftime('%s', bucket_minute_utc) AS INTEGER) / ?) AS INTEGER) * ? AS bucket_epoch,
            SUM(tx_count) AS gated_to_aprsis_total
        FROM aprsis_uplink_minute_stats
        WHERE bucket_minute_utc >= ?
          AND bucket_minute_utc < ?
        GROUP BY bucket_epoch
        ORDER BY bucket_epoch ASC
        """,
        (output_bucket_seconds, output_bucket_seconds, window_start_utc.isoformat(), window_end_utc.isoformat()),
    )
    aprsis_by_bucket_start: dict[str, dict[str, Any]] = {}
    for row in aprsis_rows:
        epoch_raw = row["bucket_epoch"]
        try:
            epoch_value = int(epoch_raw)
        except (TypeError, ValueError):
            continue
        bucket_start_utc = datetime.fromtimestamp(epoch_value, tz=timezone.utc)
        aprsis_by_bucket_start[bucket_start_utc.isoformat()] = dict(row)

    bucket_starts: list[str] = []
    labels: list[str] = []
    series: dict[str, list[int]] = {
        "rx_total": [],
        "tx_total": [],
        "digipeated_total": [],
        "own_frames_total": [],
        "messages_total": [],
        "queries_total": [],
        "objects_total": [],
        "wx_total": [],
        "position_total": [],
        "mobile_total": [],
        "fixed_total": [],
        "unique_stations_total": [],
        "direct_heard_total": [],
        "indirect_heard_total": [],
        "rfonly_total": [],
        "nogate_total": [],
        "invalid_total": [],
        "parse_error_total": [],
        "duplicate_total": [],
        "gated_to_aprsis_total": [],
    }
    totals = {key: 0 for key in series}

    for index in range(output_bucket_count):
        bucket_start_utc = window_start_utc + timedelta(minutes=output_bucket_minutes * index)
        bucket_start_key = bucket_start_utc.isoformat()
        bucket_starts.append(bucket_start_key)
        labels.append(_format_radio_activity_label(bucket_start_utc, output_bucket_minutes=output_bucket_minutes))
        row = row_by_bucket_start.get(bucket_start_key) or {}
        aprsis_row = aprsis_by_bucket_start.get(bucket_start_key) or {}
        for key in series:
            if key == "gated_to_aprsis_total":
                value = int(aprsis_row.get(key) or 0)
            else:
                value = int(row.get(key) or 0)
            series[key].append(value)
            totals[key] += value

    heard_station_keys = _dashboard_heard_station_keys(
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
    )

    return {
        "range": normalized_range,
        "range_minutes": total_minutes,
        "base_bucket_minutes": base_bucket_minutes,
        "output_bucket_minutes": output_bucket_minutes,
        "downsampled": bool(output_bucket_minutes > base_bucket_minutes),
        "window_start_utc": window_start_utc.isoformat(),
        "window_end_utc": window_end_utc.isoformat(),
        "bucket_starts_utc": bucket_starts,
        "labels": labels,
        "points": output_bucket_count,
        "series": series,
        "totals": totals,
        "kpis": {
            "heard_stations": len(heard_station_keys),
            "aprs_frames": int(totals.get("rx_total") or 0),
        },
    }


def _dashboard_heard_station_keys(
    *,
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> set[str]:
    station_keys: set[str] = set()
    first_hour_start = window_start_utc.replace(minute=0, second=0, microsecond=0)
    hourly_rows = fetch_all(
        """
        SELECT DISTINCT station_key
        FROM traffic_device_station_device_hourly
        WHERE bucket_start_utc >= ?
          AND bucket_start_utc < ?
          AND last_seen_at >= ?
          AND last_seen_at < ?
        """,
        (
            first_hour_start.isoformat(),
            window_end_utc.isoformat(),
            window_start_utc.isoformat(),
            window_end_utc.isoformat(),
        ),
    )
    for row in hourly_rows:
        station_key = _normalize_station_key_for_devices(row["station_key"])
        if station_key:
            station_keys.add(station_key)

    # Never rebuild the projection from raw 24-hour traffic in an HTTP request.
    # New traffic updates this table synchronously and historical repair belongs
    # to the background aggregator.
    return station_keys


def get_traffic_statistics(
    *,
    range_value: str = TRAFFIC_STATISTICS_RANGE_24H,
    shift_windows: int = 0,
) -> dict[str, Any]:
    normalized_range = str(range_value or TRAFFIC_STATISTICS_RANGE_24H).strip().lower()
    if normalized_range not in TRAFFIC_STATISTICS_RANGE_OPTIONS:
        raise ValueError("Unsupported range.")
    normalized_shift_windows = int(shift_windows)
    if normalized_shift_windows < 0:
        raise ValueError("Unsupported range.")

    total_minutes = int(TRAFFIC_STATISTICS_RANGE_OPTIONS[normalized_range])
    output_bucket_minutes = _resolve_traffic_statistics_bucket_minutes(total_minutes)
    output_bucket_seconds = output_bucket_minutes * 60
    output_bucket_delta = timedelta(minutes=output_bucket_minutes)
    output_bucket_count = max(1, (total_minutes + output_bucket_minutes - 1) // output_bucket_minutes)
    now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)

    latest_base_bucket_start = _floor_to_bucket_start(now_utc, bucket_minutes=RADIO_ACTIVITY_BUCKET_MINUTES) - timedelta(
        minutes=RADIO_ACTIVITY_BUCKET_MINUTES
    )
    latest_output_bucket_start = _floor_to_bucket_start(latest_base_bucket_start, bucket_minutes=output_bucket_minutes)
    if normalized_shift_windows > 0:
        latest_output_bucket_start -= timedelta(minutes=total_minutes * normalized_shift_windows)
    window_start_utc = latest_output_bucket_start - timedelta(minutes=output_bucket_minutes * (output_bucket_count - 1))
    window_end_utc = latest_output_bucket_start + output_bucket_delta

    rows = fetch_all(
        """
        SELECT
            CAST((CAST(strftime('%s', bucket_start_utc) AS INTEGER) / ?) AS INTEGER) * ? AS bucket_epoch,
            SUM(rx_total) AS rx_total,
            SUM(tx_total) AS tx_total,
            SUM(digipeated_total) AS digipeated_total,
            SUM(direct_heard_total) AS direct_heard_total,
            SUM(type_position_total) AS type_position_total,
            SUM(type_weather_total) AS type_weather_total,
            SUM(type_message_total) AS type_message_total,
            SUM(type_object_item_total) AS type_object_item_total,
            SUM(type_status_total) AS type_status_total,
            SUM(type_telemetry_total) AS type_telemetry_total,
            SUM(type_query_total) AS type_query_total,
            SUM(type_user_defined_total) AS type_user_defined_total,
            SUM(type_third_party_total) AS type_third_party_total,
            SUM(type_other_unknown_total) AS type_other_unknown_total
        FROM radio_activity_5m
        WHERE bucket_start_utc >= ?
          AND bucket_start_utc < ?
        GROUP BY bucket_epoch
        ORDER BY bucket_epoch ASC
        """,
        (output_bucket_seconds, output_bucket_seconds, window_start_utc.isoformat(), window_end_utc.isoformat()),
    )
    row_by_bucket_start: dict[str, dict[str, Any]] = {}
    for row in rows:
        epoch_raw = row["bucket_epoch"]
        try:
            epoch_value = int(epoch_raw)
        except (TypeError, ValueError):
            continue
        bucket_start_utc = datetime.fromtimestamp(epoch_value, tz=timezone.utc)
        row_by_bucket_start[bucket_start_utc.isoformat()] = dict(row)

    aprsis_rows = fetch_all(
        """
        SELECT
            CAST((CAST(strftime('%s', bucket_minute_utc) AS INTEGER) / ?) AS INTEGER) * ? AS bucket_epoch,
            SUM(tx_count) AS gated_total,
            SUM(drop_count + strict_count) AS filtered_dropped_total
        FROM aprsis_uplink_minute_stats
        WHERE bucket_minute_utc >= ?
          AND bucket_minute_utc < ?
        GROUP BY bucket_epoch
        ORDER BY bucket_epoch ASC
        """,
        (output_bucket_seconds, output_bucket_seconds, window_start_utc.isoformat(), window_end_utc.isoformat()),
    )
    aprsis_by_bucket_start: dict[str, dict[str, Any]] = {}
    for row in aprsis_rows:
        epoch_raw = row["bucket_epoch"]
        try:
            epoch_value = int(epoch_raw)
        except (TypeError, ValueError):
            continue
        bucket_start_utc = datetime.fromtimestamp(epoch_value, tz=timezone.utc)
        aprsis_by_bucket_start[bucket_start_utc.isoformat()] = dict(row)

    labels: list[str] = []
    frame_type_series: dict[str, list[int]] = {
        "position": [],
        "weather": [],
        "message": [],
        "object_item": [],
        "status": [],
        "telemetry": [],
        "query": [],
        "user_defined": [],
        "third_party": [],
        "other_unknown": [],
    }
    heard_series: dict[str, list[int]] = {
        "direct_heard": [],
        "all_heard": [],
    }
    actions_series: dict[str, list[int]] = {
        "rx": [],
        "tx": [],
        "digipeated": [],
        "gated_to_aprsis": [],
        "filtered_dropped": [],
    }

    for index in range(output_bucket_count):
        bucket_start_utc = window_start_utc + timedelta(minutes=output_bucket_minutes * index)
        bucket_key = bucket_start_utc.isoformat()
        labels.append(_format_radio_activity_label(bucket_start_utc, output_bucket_minutes=output_bucket_minutes))

        row = row_by_bucket_start.get(bucket_key) or {}
        aprsis_row = aprsis_by_bucket_start.get(bucket_key) or {}

        frame_type_series["position"].append(int(row.get("type_position_total") or 0))
        frame_type_series["weather"].append(int(row.get("type_weather_total") or 0))
        frame_type_series["message"].append(int(row.get("type_message_total") or 0))
        frame_type_series["object_item"].append(int(row.get("type_object_item_total") or 0))
        frame_type_series["status"].append(int(row.get("type_status_total") or 0))
        frame_type_series["telemetry"].append(int(row.get("type_telemetry_total") or 0))
        frame_type_series["query"].append(int(row.get("type_query_total") or 0))
        frame_type_series["user_defined"].append(int(row.get("type_user_defined_total") or 0))
        frame_type_series["third_party"].append(int(row.get("type_third_party_total") or 0))
        frame_type_series["other_unknown"].append(int(row.get("type_other_unknown_total") or 0))

        heard_series["direct_heard"].append(int(row.get("direct_heard_total") or 0))
        heard_series["all_heard"].append(int(row.get("rx_total") or 0))

        actions_series["rx"].append(int(row.get("rx_total") or 0))
        actions_series["tx"].append(int(row.get("tx_total") or 0))
        actions_series["digipeated"].append(int(row.get("digipeated_total") or 0))
        actions_series["gated_to_aprsis"].append(int(aprsis_row.get("gated_total") or 0))
        actions_series["filtered_dropped"].append(int(aprsis_row.get("filtered_dropped_total") or 0))

    return {
        "range": normalized_range,
        "shift_windows": normalized_shift_windows,
        "range_minutes": total_minutes,
        "bucket_minutes": output_bucket_minutes,
        "bucket_seconds": output_bucket_seconds,
        "downsampled": bool(output_bucket_minutes > RADIO_ACTIVITY_BUCKET_MINUTES),
        "points": output_bucket_count,
        "window_start_utc": window_start_utc.isoformat(),
        "window_end_utc": window_end_utc.isoformat(),
        "labels": labels,
        "charts": {
            "frame_types": {
                "series": [
                    {"key": "position", "label": "Position", "data": frame_type_series["position"]},
                    {"key": "weather", "label": "Weather", "data": frame_type_series["weather"]},
                    {"key": "message", "label": "Message", "data": frame_type_series["message"]},
                    {"key": "object_item", "label": "Object / Item", "data": frame_type_series["object_item"]},
                    {"key": "status", "label": "Status", "data": frame_type_series["status"]},
                    {"key": "telemetry", "label": "Telemetry", "data": frame_type_series["telemetry"]},
                    {"key": "query", "label": "Query", "data": frame_type_series["query"]},
                    {"key": "user_defined", "label": "User-defined", "data": frame_type_series["user_defined"]},
                    {"key": "third_party", "label": "Third-party", "data": frame_type_series["third_party"]},
                    {"key": "other_unknown", "label": "Other / Unknown", "data": frame_type_series["other_unknown"]},
                ]
            },
            "heard": {
                "series": [
                    {"key": "direct_heard", "label": "Direct heard", "data": heard_series["direct_heard"]},
                    {"key": "all_heard", "label": "All heard", "data": heard_series["all_heard"]},
                ]
            },
            "actions": {
                "series": [
                    {"key": "rx", "label": "RX", "data": actions_series["rx"]},
                    {"key": "tx", "label": "TX", "data": actions_series["tx"]},
                    {"key": "digipeated", "label": "Digipeated", "data": actions_series["digipeated"]},
                    {"key": "gated_to_aprsis", "label": "Gated to APRS-IS", "data": actions_series["gated_to_aprsis"]},
                    {"key": "filtered_dropped", "label": "Filtered / dropped to APRS-IS", "data": actions_series["filtered_dropped"]},
                ]
            },
        },
    }


def get_traffic_devices_statistics(
    *,
    range_value: str = TRAFFIC_STATISTICS_RANGE_24H,
    shift_windows: int = 0,
    window: str | None = None,
    top_limit: int = TRAFFIC_STATISTICS_DEVICES_DEFAULT_TOP_LIMIT,
) -> dict[str, Any]:
    normalized_range = str(range_value or TRAFFIC_STATISTICS_RANGE_24H).strip().lower()
    if normalized_range not in TRAFFIC_STATISTICS_RANGE_OPTIONS:
        raise ValueError("Unsupported range.")
    normalized_shift_windows = int(shift_windows)
    if normalized_shift_windows < 0:
        raise ValueError("Unsupported range.")
    normalized_window = str(window or "").strip().lower()
    if normalized_window and normalized_window not in {"range", "auto"}:
        raise ValueError("Unsupported window.")
    normalized_top_limit = max(1, int(top_limit))

    total_minutes = int(TRAFFIC_STATISTICS_RANGE_OPTIONS[normalized_range])
    output_bucket_minutes = _resolve_traffic_statistics_bucket_minutes(total_minutes)
    output_bucket_count = max(1, (total_minutes + output_bucket_minutes - 1) // output_bucket_minutes)
    now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    latest_base_bucket_start = _floor_to_bucket_start(now_utc, bucket_minutes=RADIO_ACTIVITY_BUCKET_MINUTES) - timedelta(
        minutes=RADIO_ACTIVITY_BUCKET_MINUTES
    )
    latest_output_bucket_start = _floor_to_bucket_start(latest_base_bucket_start, bucket_minutes=output_bucket_minutes)
    if normalized_shift_windows > 0:
        latest_output_bucket_start -= timedelta(minutes=total_minutes * normalized_shift_windows)
    window_start_utc = latest_output_bucket_start - timedelta(minutes=output_bucket_minutes * (output_bucket_count - 1))
    window_end_utc = latest_output_bucket_start + timedelta(minutes=output_bucket_minutes)

    labels_by_key: dict[str, str] = {
        TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY: TRAFFIC_STATISTICS_DEVICES_UNKNOWN_LABEL,
        TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_KEY: TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_LABEL,
        TRAFFIC_STATISTICS_DEVICES_OTHER_KEY: TRAFFIC_STATISTICS_DEVICES_OTHER_LABEL,
    }
    observations_from_buffer = _build_device_pair_observations_from_hourly_buffer(
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        labels_by_key=labels_by_key,
    )
    frame_rows = fetch_all(
        f"""
        SELECT direction, format, line, created_at
        FROM traffic_frames
        WHERE format LIKE 'TNC2%'
          AND {STATISTICS_TRAFFIC_SQL_PREDICATE}
          AND created_at >= ?
          AND created_at < ?
        ORDER BY created_at ASC, id ASC
        """,
        (window_start_utc.isoformat(), window_end_utc.isoformat()),
    )
    observations_from_frames = _build_device_pair_observations_from_frame_rows(
        frame_rows=frame_rows,
        labels_by_key=labels_by_key,
        database=get_aprs_device_identification_database(),
    )
    resolve_group_key, grouped_labels_by_key = _build_device_group_key_resolver(labels_by_key=labels_by_key)
    pair_assignments = _resolve_unique_station_tocall_pair_assignments(
        observations=[*observations_from_buffer, *observations_from_frames],
        resolve_group_key=resolve_group_key,
    )
    entries_by_group: dict[str, list[dict[str, Any]]] = {}
    unique_station_keys: set[str] = set()
    for assignment in pair_assignments.values():
        group_key = str(assignment.get("group_key") or "").strip()
        station_key = _normalize_station_key_for_devices(assignment.get("callsign_ssid"))
        tocall = _normalize_statistics_tocall(assignment.get("tocall"))
        if not group_key or not station_key:
            continue
        unique_station_keys.add(station_key)
        group_entries = entries_by_group.get(group_key)
        if group_entries is None:
            group_entries = []
            entries_by_group[group_key] = group_entries
        group_entries.append(
            {
                "callsign_ssid": station_key,
                "tocall": tocall,
                "model_key": str(assignment.get("model_key") or "").strip().upper() or None,
                "model_label": str(assignment.get("model_label") or "").strip() or None,
                "last_seen": _normalize_traffic_device_last_seen(assignment.get("last_seen")),
            }
        )
    station_entries_by_group = {
        group_key: _normalize_traffic_device_station_entries(group_entries)
        for group_key, group_entries in entries_by_group.items()
        if group_entries
    }
    counts_by_group = {
        group_key: len(group_entries)
        for group_key, group_entries in station_entries_by_group.items()
        if group_entries
    }
    total = sum(counts_by_group.values())
    unique_station_keys_total = len(unique_station_keys)
    items = _build_traffic_devices_items(
        counts=counts_by_group,
        labels_by_key=grouped_labels_by_key,
        total=total,
        top_limit=normalized_top_limit,
        entries_by_key=station_entries_by_group,
    )
    return {
        "range": normalized_range,
        "shift_windows": normalized_shift_windows,
        "window": "range",
        "count_basis": "unique_callsign_ssid_per_model",
        "unique_station_keys_total": unique_station_keys_total,
        "unique_station_device_pairs_total": total,
        "unique_callsign_ssid_tocall_pairs_total": len(pair_assignments),
        "total": total,
        "top_limit": normalized_top_limit,
        "window_start_utc": window_start_utc.isoformat(),
        "window_end_utc": window_end_utc.isoformat(),
        "items": items,
    }


def get_traffic_users_statistics(
    *,
    range_value: str = TRAFFIC_STATISTICS_RANGE_24H,
    shift_windows: int = 0,
    top_limit: int = TRAFFIC_STATISTICS_USERS_DEFAULT_TOP_LIMIT,
) -> dict[str, Any]:
    normalized_range = str(range_value or TRAFFIC_STATISTICS_RANGE_24H).strip().lower()
    if normalized_range not in TRAFFIC_STATISTICS_RANGE_OPTIONS:
        raise ValueError("Unsupported range.")
    normalized_shift_windows = int(shift_windows)
    if normalized_shift_windows < 0:
        raise ValueError("Unsupported range.")
    normalized_top_limit = max(1, int(top_limit))

    total_minutes = int(TRAFFIC_STATISTICS_RANGE_OPTIONS[normalized_range])
    output_bucket_minutes = _resolve_traffic_statistics_bucket_minutes(total_minutes)
    output_bucket_count = max(1, (total_minutes + output_bucket_minutes - 1) // output_bucket_minutes)
    now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    latest_base_bucket_start = _floor_to_bucket_start(now_utc, bucket_minutes=RADIO_ACTIVITY_BUCKET_MINUTES) - timedelta(
        minutes=RADIO_ACTIVITY_BUCKET_MINUTES
    )
    latest_output_bucket_start = _floor_to_bucket_start(latest_base_bucket_start, bucket_minutes=output_bucket_minutes)
    if normalized_shift_windows > 0:
        latest_output_bucket_start -= timedelta(minutes=total_minutes * normalized_shift_windows)
    window_start_utc = latest_output_bucket_start - timedelta(minutes=output_bucket_minutes * (output_bucket_count - 1))
    window_end_utc = latest_output_bucket_start + timedelta(minutes=output_bucket_minutes)

    station_counts: dict[str, int] = {}
    hourly_rows = fetch_all(
        """
        SELECT station_key, SUM(frame_count) AS frame_total
        FROM traffic_device_station_device_hourly
        WHERE frame_count > 0
          AND bucket_start_utc >= ?
          AND bucket_start_utc < ?
        GROUP BY station_key
        ORDER BY frame_total DESC, station_key ASC
        """,
        (window_start_utc.isoformat(), window_end_utc.isoformat()),
    )
    for row in hourly_rows:
        station_key = _normalize_station_key_for_devices(row["station_key"])
        if not station_key:
            continue
        station_counts[station_key] = int(station_counts.get(station_key) or 0) + max(0, int(row["frame_total"] or 0))

    if not station_counts:
        frame_rows = fetch_all(
            f"""
            SELECT direction, format, line
            FROM traffic_frames
            WHERE format LIKE 'TNC2%'
              AND {STATISTICS_TRAFFIC_SQL_PREDICATE}
              AND created_at >= ?
              AND created_at < ?
            ORDER BY created_at ASC, id ASC
            """,
            (window_start_utc.isoformat(), window_end_utc.isoformat()),
        )
        for row in frame_rows:
            frame_format = str(row["format"] or "").strip().upper()
            direction = _normalize_direction(row["direction"], frame_format)
            if direction != "RX":
                continue
            parsed = parse_tnc2_frame(str(row["line"] or ""))
            if parsed is None:
                continue
            station_key = _normalize_station_key_for_devices(
                parsed.get("logical_source_key") or parsed.get("source_key") or parsed.get("source") or ""
            )
            if not station_key:
                continue
            station_counts[station_key] = int(station_counts.get(station_key) or 0) + 1

    total = sum(max(0, int(value)) for value in station_counts.values())
    items = _build_traffic_users_items(counts=station_counts, total=total, top_limit=normalized_top_limit)
    return {
        "range": normalized_range,
        "shift_windows": normalized_shift_windows,
        "count_basis": "frames_rx_tnc2",
        "total": total,
        "top_limit": normalized_top_limit,
        "window_start_utc": window_start_utc.isoformat(),
        "window_end_utc": window_end_utc.isoformat(),
        "items": items,
    }


def get_traffic_direct_heard_statistics(
    *,
    range_value: str = TRAFFIC_STATISTICS_RANGE_24H,
    shift_windows: int = 0,
    top_limit: int = TRAFFIC_STATISTICS_USERS_DEFAULT_TOP_LIMIT,
) -> dict[str, Any]:
    normalized_range = str(range_value or TRAFFIC_STATISTICS_RANGE_24H).strip().lower()
    if normalized_range not in TRAFFIC_STATISTICS_RANGE_OPTIONS:
        raise ValueError("Unsupported range.")
    normalized_shift_windows = int(shift_windows)
    if normalized_shift_windows < 0:
        raise ValueError("Unsupported range.")
    normalized_top_limit = max(1, int(top_limit))

    total_minutes = int(TRAFFIC_STATISTICS_RANGE_OPTIONS[normalized_range])
    output_bucket_minutes = _resolve_traffic_statistics_bucket_minutes(total_minutes)
    output_bucket_count = max(1, (total_minutes + output_bucket_minutes - 1) // output_bucket_minutes)
    now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    latest_base_bucket_start = _floor_to_bucket_start(now_utc, bucket_minutes=RADIO_ACTIVITY_BUCKET_MINUTES) - timedelta(
        minutes=RADIO_ACTIVITY_BUCKET_MINUTES
    )
    latest_output_bucket_start = _floor_to_bucket_start(latest_base_bucket_start, bucket_minutes=output_bucket_minutes)
    if normalized_shift_windows > 0:
        latest_output_bucket_start -= timedelta(minutes=total_minutes * normalized_shift_windows)
    window_start_utc = latest_output_bucket_start - timedelta(minutes=output_bucket_minutes * (output_bucket_count - 1))
    window_end_utc = latest_output_bucket_start + timedelta(minutes=output_bucket_minutes)

    station_counts: dict[str, int] = {}
    frame_rows = fetch_all(
        f"""
        SELECT direction, format, line
        FROM traffic_frames
        WHERE format LIKE 'TNC2%'
          AND {STATISTICS_TRAFFIC_SQL_PREDICATE}
          AND created_at >= ?
          AND created_at < ?
        ORDER BY created_at ASC, id ASC
        """,
        (window_start_utc.isoformat(), window_end_utc.isoformat()),
    )
    for row in frame_rows:
        frame_format = str(row["format"] or "").strip().upper()
        direction = _normalize_direction(row["direction"], frame_format)
        if direction != "RX":
            continue
        parsed = parse_tnc2_frame(str(row["line"] or ""))
        if parsed is None:
            continue
        path_tokens = _split_path_tokens(str(parsed.get("logical_path") or parsed.get("path") or ""))
        if any(token.endswith("*") for token in path_tokens):
            continue
        station_key = _normalize_station_key_for_devices(
            parsed.get("logical_source_key") or parsed.get("source_key") or parsed.get("source") or ""
        )
        if not station_key:
            continue
        station_counts[station_key] = int(station_counts.get(station_key) or 0) + 1

    total = sum(max(0, int(value)) for value in station_counts.values())
    items = _build_traffic_users_items(counts=station_counts, total=total, top_limit=normalized_top_limit)
    return {
        "range": normalized_range,
        "shift_windows": normalized_shift_windows,
        "count_basis": "frames_rx_tnc2_direct_heard",
        "total": total,
        "top_limit": normalized_top_limit,
        "window_start_utc": window_start_utc.isoformat(),
        "window_end_utc": window_end_utc.isoformat(),
        "items": items,
    }


def record_traffic_device_station_observation(
    *,
    frame_format: str,
    line: str,
    timestamp: str,
) -> None:
    normalized_format = str(frame_format or "").strip().upper()
    if not normalized_format.startswith("TNC2"):
        return

    parsed = parse_tnc2_frame(str(line or ""))
    if parsed is None:
        return

    station_key = _normalize_station_key_for_devices(
        parsed.get("logical_source_key") or parsed.get("source_key") or parsed.get("source") or ""
    )
    if not station_key:
        return

    destination_candidate = _normalize_statistics_destination(
        str(parsed.get("logical_destination") or parsed.get("destination") or "")
    )
    destination_key = _normalize_statistics_tocall(destination_candidate)
    device_key, device_label, is_recognized = _resolve_statistics_device_bucket(
        destination_candidate,
        str(parsed.get("logical_info") or parsed.get("info") or ""),
        database=get_aprs_device_identification_database(),
        cache={},
    )

    parsed_timestamp = _parse_iso_timestamp_utc(str(timestamp or ""))
    normalized_timestamp_value = parsed_timestamp if parsed_timestamp is not None else datetime.now(timezone.utc).replace(microsecond=0)
    normalized_timestamp = normalized_timestamp_value.isoformat()
    bucket_start_utc = _floor_to_bucket_start(normalized_timestamp_value, bucket_minutes=60).isoformat()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO traffic_device_station_device_hourly(
                bucket_start_utc, station_key, device_key, destination_key,
                device_label, recognized_flag, frame_count, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(bucket_start_utc, station_key, device_key, destination_key) DO UPDATE SET
                device_label = excluded.device_label,
                recognized_flag = CASE
                    WHEN traffic_device_station_device_hourly.recognized_flag = 1 OR excluded.recognized_flag = 1 THEN 1
                    ELSE 0
                END,
                frame_count = traffic_device_station_device_hourly.frame_count + 1,
                last_seen_at = CASE
                    WHEN excluded.last_seen_at > traffic_device_station_device_hourly.last_seen_at THEN excluded.last_seen_at
                    ELSE traffic_device_station_device_hourly.last_seen_at
                END
            """,
            (
                bucket_start_utc,
                station_key,
                device_key,
                destination_key,
                device_label,
                1 if is_recognized else 0,
                normalized_timestamp,
            ),
        )


def _build_device_pair_observations_from_frame_rows(
    *,
    frame_rows: list[dict[str, Any]],
    labels_by_key: dict[str, str],
    database: Any,
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    destination_cache: dict[str, tuple[str, str, bool]] = {}
    for row in frame_rows:
        frame_format = str(row["format"] or "").strip().upper()
        direction = _normalize_direction(row["direction"], frame_format)
        if direction != "RX":
            continue
        parsed = parse_tnc2_frame(str(row["line"] or ""))
        if parsed is None:
            continue
        station_key = _normalize_station_key_for_devices(
            parsed.get("logical_source_key") or parsed.get("source_key") or parsed.get("source") or ""
        )
        if not station_key:
            continue
        normalized_destination = _normalize_statistics_destination(
            str(parsed.get("logical_destination") or parsed.get("destination") or "")
        )
        tocall = _normalize_statistics_tocall(normalized_destination)
        device_key, device_label, is_recognized = _resolve_statistics_device_bucket(
            normalized_destination,
            str(parsed.get("logical_info") or parsed.get("info") or ""),
            database=database,
            cache=destination_cache,
        )
        labels_by_key[device_key] = device_label
        observations.append(
            {
                "callsign_ssid": station_key,
                "tocall": tocall,
                "model_key": device_key,
                "model_label": device_label,
                "recognized": bool(is_recognized),
                "last_seen": _normalize_traffic_device_last_seen(row["created_at"]),
            }
        )
    return observations


def _build_device_pair_observations_from_hourly_buffer(
    *,
    window_start_utc: datetime,
    window_end_utc: datetime,
    labels_by_key: dict[str, str],
) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT station_key, device_key, destination_key, device_label, frame_count, recognized_flag, last_seen_at
        FROM traffic_device_station_device_hourly
        WHERE frame_count > 0
          AND bucket_start_utc >= ?
          AND bucket_start_utc < ?
        ORDER BY bucket_start_utc ASC, last_seen_at ASC, station_key ASC, device_key ASC, destination_key ASC
        """,
        (window_start_utc.isoformat(), window_end_utc.isoformat()),
    )
    observations: list[dict[str, Any]] = []
    for row in rows:
        station_key = _normalize_station_key_for_devices(row["station_key"])
        if not station_key:
            continue
        model_key = str(row["device_key"] or "").strip().upper()
        if not model_key:
            continue
        normalized_count = max(0, int(row["frame_count"] or 0))
        if normalized_count <= 0:
            continue
        model_label = str(row["device_label"] or "").strip() or model_key
        labels_by_key[model_key] = model_label
        tocall = _normalize_statistics_tocall(str(row["destination_key"] or ""))
        observations.append(
            {
                "callsign_ssid": station_key,
                "tocall": tocall,
                "model_key": model_key,
                "model_label": model_label,
                "recognized": bool(int(row["recognized_flag"] or 0) > 0),
                "last_seen": _normalize_traffic_device_last_seen(row["last_seen_at"]),
            }
        )
    return observations


def _resolve_unique_station_tocall_pair_assignments(
    *,
    observations: list[dict[str, Any]],
    resolve_group_key: Callable[[Any], str],
) -> dict[str, dict[str, Any]]:
    assignments: dict[str, dict[str, Any]] = {}
    for observation in observations:
        station_key = _normalize_station_key_for_devices(observation.get("callsign_ssid"))
        tocall = _normalize_statistics_tocall(observation.get("tocall"))
        model_key = _normalize_statistics_device_key(observation.get("model_key"))
        group_key = resolve_group_key(model_key)
        if not station_key or not tocall or not group_key:
            continue
        pair_key = f"{station_key}\u241f{tocall}"
        candidate = {
            "callsign_ssid": station_key,
            "tocall": tocall,
            "model_key": model_key,
            "model_label": str(observation.get("model_label") or "").strip() or model_key,
            "group_key": group_key,
            "recognized": bool(observation.get("recognized")),
            "last_seen": _normalize_traffic_device_last_seen(observation.get("last_seen")),
        }
        current = assignments.get(pair_key)
        if current is None:
            assignments[pair_key] = candidate
            continue
        if current.get("group_key") == candidate.get("group_key"):
            merged_last_seen = _max_traffic_device_last_seen(
                _normalize_traffic_device_last_seen(current.get("last_seen")),
                _normalize_traffic_device_last_seen(candidate.get("last_seen")),
            )
            current["last_seen"] = merged_last_seen
            if candidate.get("recognized") and not current.get("recognized"):
                current["recognized"] = True
                current["model_key"] = candidate.get("model_key")
                current["model_label"] = candidate.get("model_label")
            continue
        if _device_pair_assignment_priority(candidate) > _device_pair_assignment_priority(current):
            assignments[pair_key] = candidate
    return assignments


def _normalize_station_key_for_devices(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_statistics_tocall(value: Any) -> str:
    normalized = _normalize_statistics_destination(str(value or ""))
    if normalized in {
        "",
        TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY.upper(),
        TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_KEY.upper(),
        TRAFFIC_STATISTICS_DEVICES_OTHER_KEY.upper(),
    }:
        return TRAFFIC_STATISTICS_TOCALL_UNKNOWN
    if not _is_statistics_tocall_candidate(normalized):
        return TRAFFIC_STATISTICS_TOCALL_UNKNOWN
    return normalized


def _is_statistics_tocall_candidate(value: str) -> bool:
    if not value:
        return False
    if value in _TRAFFIC_STATISTICS_TOCALL_NON_AP_ALLOWED:
        return True
    return _TRAFFIC_STATISTICS_TOCALL_RE.fullmatch(value) is not None


def _normalize_traffic_device_last_seen(value: Any) -> str | None:
    parsed = _parse_iso_timestamp_utc(str(value or ""))
    if parsed is None:
        return None
    return parsed.isoformat()


def _max_traffic_device_last_seen(left: str | None, right: str | None) -> str | None:
    left_parsed = _parse_iso_timestamp_utc(str(left or ""))
    right_parsed = _parse_iso_timestamp_utc(str(right or ""))
    if left_parsed is None:
        return right_parsed.isoformat() if right_parsed is not None else None
    if right_parsed is None:
        return left_parsed.isoformat()
    return left_parsed.isoformat() if left_parsed >= right_parsed else right_parsed.isoformat()


def _device_pair_assignment_priority(value: dict[str, Any]) -> tuple[int, int, datetime, str]:
    group_key = str(value.get("group_key") or "").strip().lower()
    recognized_score = 1 if bool(value.get("recognized")) else 0
    non_special_score = 0 if group_key in {
        TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY,
        TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_KEY,
        TRAFFIC_STATISTICS_DEVICES_OTHER_KEY,
    } else 1
    last_seen = _parse_iso_timestamp_utc(str(value.get("last_seen") or ""))
    if last_seen is None:
        last_seen = datetime.min.replace(tzinfo=timezone.utc)
    return (
        recognized_score,
        non_special_score,
        last_seen,
        str(value.get("model_key") or "").strip().upper(),
    )


def _normalize_statistics_device_key(value: Any) -> str:
    resolved_key_raw = str(value or "").strip().upper()
    if resolved_key_raw in {"", TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY.upper()}:
        return TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY
    if resolved_key_raw == TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_KEY.upper():
        return TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_KEY
    if resolved_key_raw == TRAFFIC_STATISTICS_DEVICES_OTHER_KEY.upper():
        return TRAFFIC_STATISTICS_DEVICES_OTHER_KEY
    return resolved_key_raw


def _build_device_group_key_resolver(
    *,
    labels_by_key: dict[str, str],
) -> tuple[Callable[[Any], str], dict[str, str]]:
    special_keys = {
        TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY,
        TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_KEY,
        TRAFFIC_STATISTICS_DEVICES_OTHER_KEY,
    }
    grouped_labels: dict[str, str] = {}
    merged_key_by_label: dict[str, str] = {}
    normalized_labels_by_key = {
        _normalize_statistics_device_key(raw_key): str(raw_label or "").strip()
        for raw_key, raw_label in dict(labels_by_key or {}).items()
        if str(raw_key or "").strip()
    }

    def resolve_group_key(raw_key: Any) -> str:
        normalized_key = _normalize_statistics_device_key(raw_key)
        label = str(normalized_labels_by_key.get(normalized_key) or normalized_key).strip() or normalized_key
        normalized_label = label.casefold()
        if normalized_label in {"unknown", "nieznany"}:
            grouped_labels.setdefault(TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY, TRAFFIC_STATISTICS_DEVICES_UNKNOWN_LABEL)
            return TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY
        if normalized_key in special_keys:
            group_key = normalized_key
        else:
            label_key = normalized_label
            existing_merged_key = merged_key_by_label.get(label_key)
            if existing_merged_key is None:
                group_key = normalized_key
                merged_key_by_label[label_key] = group_key
            else:
                group_key = existing_merged_key

        if group_key not in grouped_labels:
            grouped_labels[group_key] = label
        return group_key

    for special_key, special_label in (
        (TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY, TRAFFIC_STATISTICS_DEVICES_UNKNOWN_LABEL),
        (TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_KEY, TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_LABEL),
        (TRAFFIC_STATISTICS_DEVICES_OTHER_KEY, TRAFFIC_STATISTICS_DEVICES_OTHER_LABEL),
    ):
        grouped_labels.setdefault(special_key, special_label)

    return resolve_group_key, grouped_labels


def _resolve_statistics_device_bucket(
    destination: str,
    info: str,
    *,
    database: Any,
    cache: dict[str, tuple[str, str, bool]],
) -> tuple[str, str, bool]:
    normalized_destination = _normalize_statistics_destination(destination)
    normalized_info = str(info or "")
    if not normalized_destination:
        return (
            TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY,
            TRAFFIC_STATISTICS_DEVICES_UNKNOWN_LABEL,
            False,
        )
    cache_key = f"{normalized_destination}\u241f{normalized_info}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    matched = lookup_aprs_device_identification(destination=normalized_destination, info=normalized_info, database=database)
    if matched is not None:
        key = str(matched.get("actual_identifier") or normalized_destination).strip().upper() or normalized_destination
        label = str(matched.get("short_name") or matched.get("identified_as") or key).strip() or key
        if key == "APRS" and label.casefold() == "unknown":
            resolved = (
                TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY,
                TRAFFIC_STATISTICS_DEVICES_UNKNOWN_LABEL,
                False,
            )
        else:
            resolved = (key, label, True)
    else:
        resolved = (
            TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY,
            TRAFFIC_STATISTICS_DEVICES_UNKNOWN_LABEL,
            False,
        )
    cache[cache_key] = resolved
    return resolved


def _normalize_statistics_destination(destination: str) -> str:
    value = str(destination or "").strip().upper()
    base, separator, suffix = value.partition("-")
    if separator and suffix.isdigit():
        value = base
    return value


def _build_traffic_devices_items(
    *,
    counts: dict[str, int],
    labels_by_key: dict[str, str],
    total: int,
    top_limit: int,
    entries_by_key: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    if total <= 0:
        return []

    non_zero_counts = {str(key): int(value) for key, value in counts.items() if int(value) > 0}
    if not non_zero_counts:
        return []

    ranked_items = [(key, value) for key, value in non_zero_counts.items()]
    ranked_items.sort(key=lambda item: (-item[1], str(labels_by_key.get(item[0]) or item[0]).casefold(), item[0]))

    items: list[dict[str, Any]] = []
    normalized_top_limit = max(1, int(top_limit))
    remaining_items = ranked_items
    if len(ranked_items) > normalized_top_limit and normalized_top_limit > 1:
        selected_items = ranked_items[:normalized_top_limit - 1]
        remaining_items = ranked_items[normalized_top_limit - 1:]
    else:
        selected_items = ranked_items[:normalized_top_limit]
        remaining_items = ranked_items[normalized_top_limit:]

    for key, count in selected_items:
        label = str(labels_by_key.get(key) or key).strip() or key
        normalized_entries = _normalize_traffic_device_station_entries((entries_by_key or {}).get(key))
        items.append(
            _traffic_devices_item(
                key=key,
                label=label,
                count=count,
                total=total,
                entries=normalized_entries,
            )
        )

    other_entries: list[dict[str, Any]] = []
    for remaining_key, _remaining_count in remaining_items:
        other_entries.extend(list((entries_by_key or {}).get(remaining_key) or []))
    normalized_other_entries = _normalize_traffic_device_station_entries(other_entries)
    if normalized_other_entries and len(items) < normalized_top_limit:
        items.append(
            _traffic_devices_item(
                key=TRAFFIC_STATISTICS_DEVICES_OTHER_KEY,
                label=str(labels_by_key.get(TRAFFIC_STATISTICS_DEVICES_OTHER_KEY) or TRAFFIC_STATISTICS_DEVICES_OTHER_LABEL),
                count=len(normalized_other_entries),
                total=total,
                entries=normalized_other_entries,
            )
        )
    return items


def _traffic_devices_item(
    *,
    key: str,
    label: str,
    count: int,
    total: int,
    entries: Any = None,
) -> dict[str, Any]:
    normalized_entries = _normalize_traffic_device_station_entries(entries)
    normalized_count = max(0, int(count))
    if normalized_entries:
        normalized_count = len(normalized_entries)
    normalized_total = max(0, int(total))
    percent = 0.0
    if normalized_total > 0:
        percent = round((float(normalized_count) * 100.0) / float(normalized_total), 1)
    unique_station_keys = sorted(
        {
            _normalize_station_key_for_devices(entry.get("callsign_ssid"))
            for entry in normalized_entries
            if _normalize_station_key_for_devices(entry.get("callsign_ssid"))
        }
    )
    unique_tocalls = sorted(
        {
            _normalize_statistics_tocall(value)
            for entry in normalized_entries
            for value in list(entry.get("tocalls") or ([entry.get("tocall")] if entry.get("tocall") else []))
            if _normalize_statistics_tocall(value)
        }
    )
    tocall_value = unique_tocalls[0] if len(unique_tocalls) == 1 else None
    return {
        "key": str(key or "").strip() or TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY,
        "label": str(label or "").strip() or TRAFFIC_STATISTICS_DEVICES_UNKNOWN_LABEL,
        "count": normalized_count,
        "percent": percent,
        "ident": str(key or "").strip() or TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY,
        "tocall": tocall_value,
        "stations_tocall": unique_station_keys,
        "stations_model": unique_station_keys,
        "entries": normalized_entries,
    }


def _normalize_traffic_device_station_entries(entries: Any) -> list[dict[str, Any]]:
    normalized_by_station: dict[str, dict[str, Any]] = {}
    for raw_entry in list(entries or []):
        if not isinstance(raw_entry, dict):
            continue
        station_key = _normalize_station_key_for_devices(raw_entry.get("callsign_ssid"))
        if not station_key:
            continue
        tocall_values = list(raw_entry.get("tocalls") or [])
        if not tocall_values and raw_entry.get("tocall") is not None:
            tocall_values = [raw_entry.get("tocall")]
        normalized_tocalls = sorted(
            {
                _normalize_statistics_tocall(value)
                for value in tocall_values
                if _normalize_statistics_tocall(value)
            }
        )
        normalized_entry = {
            "callsign_ssid": station_key,
            "tocall": normalized_tocalls[0] if len(normalized_tocalls) == 1 else None,
            "tocalls": normalized_tocalls,
            "model_key": _normalize_statistics_device_key(raw_entry.get("model_key")) if raw_entry.get("model_key") else None,
            "model_label": str(raw_entry.get("model_label") or "").strip() or None,
            "last_seen": _normalize_traffic_device_last_seen(raw_entry.get("last_seen")),
        }
        existing = normalized_by_station.get(station_key)
        if existing is None:
            normalized_by_station[station_key] = normalized_entry
            continue
        merged_tocalls = sorted(
            {
                _normalize_statistics_tocall(value)
                for value in [*list(existing.get("tocalls") or []), *normalized_tocalls]
                if _normalize_statistics_tocall(value)
            }
        )
        existing["tocalls"] = merged_tocalls
        existing["tocall"] = merged_tocalls[0] if len(merged_tocalls) == 1 else None
        existing["last_seen"] = _max_traffic_device_last_seen(existing.get("last_seen"), normalized_entry.get("last_seen"))
        if normalized_entry.get("model_key") and not existing.get("model_key"):
            existing["model_key"] = normalized_entry.get("model_key")
            existing["model_label"] = normalized_entry.get("model_label")

    normalized_entries = list(normalized_by_station.values())
    normalized_entries.sort(
        key=lambda item: (
            str(item.get("callsign_ssid") or ""),
            str(item.get("last_seen") or ""),
        )
    )
    return normalized_entries


def _build_traffic_users_items(
    *,
    counts: dict[str, int],
    total: int,
    top_limit: int,
) -> list[dict[str, Any]]:
    if total <= 0:
        return []
    items = [
        (str(key).strip().upper(), max(0, int(value)))
        for key, value in dict(counts or {}).items()
        if str(key).strip() and int(value) > 0
    ]
    if not items:
        return []
    items.sort(key=lambda item: (-item[1], item[0]))
    normalized_top_limit = max(1, int(top_limit))
    selected_items = items[:normalized_top_limit]
    return [
        _traffic_users_item(station_key=station_key, count=count, total=total)
        for station_key, count in selected_items
    ]


def _traffic_users_item(*, station_key: str, count: int, total: int) -> dict[str, Any]:
    normalized_count = max(0, int(count))
    normalized_total = max(0, int(total))
    percent = 0.0
    if normalized_total > 0:
        percent = round((float(normalized_count) * 100.0) / float(normalized_total), 1)
    normalized_station_key = str(station_key or "").strip().upper()
    return {
        "key": normalized_station_key,
        "label": normalized_station_key,
        "count": normalized_count,
        "percent": percent,
    }


def _resolve_output_bucket_minutes(total_minutes: int) -> int:
    normalized_total_minutes = max(RADIO_ACTIVITY_BUCKET_MINUTES, int(total_minutes))
    if normalized_total_minutes <= RADIO_ACTIVITY_RANGE_OPTIONS[RADIO_ACTIVITY_RANGE_7D]:
        return RADIO_ACTIVITY_BUCKET_MINUTES
    for step_minutes in RADIO_ACTIVITY_DOWNSAMPLE_STEPS_MINUTES:
        if step_minutes < RADIO_ACTIVITY_BUCKET_MINUTES:
            continue
        bucket_count = (normalized_total_minutes + step_minutes - 1) // step_minutes
        if bucket_count <= RADIO_ACTIVITY_DOWNSAMPLE_MAX_POINTS:
            return step_minutes
    return RADIO_ACTIVITY_DOWNSAMPLE_STEPS_MINUTES[-1]


def _resolve_traffic_statistics_bucket_minutes(total_minutes: int) -> int:
    normalized_total_minutes = max(1, int(total_minutes))
    if normalized_total_minutes <= TRAFFIC_STATISTICS_RANGE_OPTIONS[TRAFFIC_STATISTICS_RANGE_24H]:
        return 60
    return 1440


def _format_radio_activity_label(bucket_start_utc: datetime, *, output_bucket_minutes: int) -> str:
    if output_bucket_minutes >= 1440:
        return bucket_start_utc.strftime("%d.%m")
    if output_bucket_minutes >= 60:
        return bucket_start_utc.strftime("%d.%m %H:%M")
    return bucket_start_utc.strftime("%H:%M")


def _collect_bucket_source_rows(
    *,
    bucket_start_utc: datetime,
    bucket_end_utc: datetime,
    collect_band_condition: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    frame_rows = fetch_all(
        f"""
        SELECT source, interface_id, direction, format, line, command
        FROM traffic_frames
        WHERE created_at >= ?
          AND created_at < ?
          AND {STATISTICS_TRAFFIC_SQL_PREDICATE}
        ORDER BY created_at ASC, id ASC
        """,
        (bucket_start_utc.isoformat(), bucket_end_utc.isoformat()),
    )
    if not frame_rows:
        return [], []

    station_source_key, station_callsign, wx_source_key = _station_identity_keys()
    grouped: dict[str, dict[str, Any]] = {}
    band_frame_rows: list[dict[str, Any]] = []

    for row in frame_rows:
        source_name = str(row["source"] or "").strip() or "Unknown source"
        source_bucket = grouped.get(source_name)
        if source_bucket is None:
            source_bucket = _new_source_bucket(source_name)
            grouped[source_name] = source_bucket

        interface_id = _int_or_none(row["interface_id"])
        if source_bucket.get("interface_id") is None and interface_id is not None:
            source_bucket["interface_id"] = interface_id

        direction = _normalize_direction(row["direction"], row["format"])
        command = str(row["command"] or "").strip().upper()
        is_skipped_tx = direction == "TX" and command.startswith("TX-SKIP")

        if direction == "RX":
            source_bucket["rx_total"] += 1
        elif direction == "TX" and not is_skipped_tx:
            source_bucket["tx_total"] += 1

        frame_format = str(row["format"] or "").strip().upper()
        line = str(row["line"] or "")
        if not frame_format.startswith("TNC2"):
            continue

        parsed = parse_tnc2_frame(line)
        if parsed is None:
            source_bucket["parse_error_total"] += 1
            source_bucket["type_other_unknown_total"] += 1
            continue
        if collect_band_condition and direction == "RX" and frame_format == "TNC2" and interface_id is not None:
            band_frame_rows.append(
                {
                    "interface_id": interface_id,
                    "parsed": parsed,
                }
            )

        frame_type_bucket_key = _classify_frame_type_bucket_key(parsed=parsed)
        source_bucket[frame_type_bucket_key] += 1

        parsed_source_key = str(parsed.get("source_key") or "").strip().upper()
        parsed_source_callsign = str(parsed.get("source_callsign") or "").strip().upper()
        is_own_frame = (
            (bool(station_source_key) and parsed_source_key == station_source_key)
            or (bool(wx_source_key) and parsed_source_key == wx_source_key)
            or (bool(station_callsign) and parsed_source_callsign == station_callsign)
        )
        if is_own_frame:
            source_bucket["own_frames_total"] += 1
        if direction == "TX" and not is_skipped_tx and not command.startswith("TX-PROXY") and not is_own_frame:
            source_bucket["digipeated_total"] += 1

        source_station_key = str(parsed.get("logical_source_key") or parsed.get("source_key") or "").strip().upper()
        if source_station_key:
            source_bucket["_unique_station_keys"].add(source_station_key)

        aprs_data = dict(parsed.get("aprs_data") or {})
        packet_group = str(aprs_data.get("packet_group") or "").strip().lower()
        classification = str(parsed.get("classification") or "").strip().lower()
        if packet_group == "message":
            source_bucket["messages_total"] += 1
        elif packet_group == "query":
            source_bucket["queries_total"] += 1
        elif packet_group == "object":
            source_bucket["objects_total"] += 1
        elif packet_group == "weather":
            source_bucket["wx_total"] += 1
        elif packet_group == "position":
            source_bucket["position_total"] += 1

        if classification == "mobile":
            source_bucket["mobile_total"] += 1
        elif classification == "fixed":
            source_bucket["fixed_total"] += 1

        if bool(parsed.get("is_third_party")) and not bool(parsed.get("third_party_inner_valid")):
            source_bucket["invalid_total"] += 1

        path_tokens = _split_path_tokens(str(parsed.get("logical_path") or parsed.get("path") or ""))
        if path_tokens:
            hop_count = len(path_tokens)
            source_bucket["_hop_count_total"] += hop_count
            source_bucket["_hop_samples"] += 1
            previous_max_hops = source_bucket.get("max_hops_seen")
            if previous_max_hops is None or hop_count > previous_max_hops:
                source_bucket["max_hops_seen"] = hop_count

            consumed_hops = [token for token in path_tokens if token.endswith("*")]
            if direction == "RX":
                if consumed_hops:
                    source_bucket["indirect_heard_total"] += 1
                else:
                    source_bucket["direct_heard_total"] += 1

            normalized_path_tokens = [token.rstrip("*").upper() for token in path_tokens]
            if "RFONLY" in normalized_path_tokens:
                source_bucket["rfonly_total"] += 1
            if "NOGATE" in normalized_path_tokens:
                source_bucket["nogate_total"] += 1
        elif direction == "RX":
            source_bucket["direct_heard_total"] += 1

    source_rows: list[dict[str, Any]] = []
    for source_bucket in grouped.values():
        source_bucket["unique_stations_total"] = len(source_bucket["_unique_station_keys"])
        hop_samples = int(source_bucket.get("_hop_samples") or 0)
        if hop_samples > 0:
            source_bucket["avg_hops"] = float(source_bucket["_hop_count_total"]) / float(hop_samples)
        else:
            source_bucket["avg_hops"] = None
            source_bucket["max_hops_seen"] = None

        source_bucket["duplicate_total"] = 0
        source_bucket.pop("_unique_station_keys", None)
        source_bucket.pop("_hop_count_total", None)
        source_bucket.pop("_hop_samples", None)
        source_rows.append(source_bucket)
    return source_rows, band_frame_rows


def _upsert_radio_activity_bucket_rows(
    *,
    bucket_start_utc: datetime,
    bucket_end_utc: datetime,
    source_rows: list[dict[str, Any]],
) -> None:
    if not source_rows:
        return
    now_utc = utc_now()
    bucket_start_iso = bucket_start_utc.isoformat()
    bucket_end_iso = bucket_end_utc.isoformat()
    with get_connection() as connection:
        for row in source_rows:
            connection.execute(
                """
                INSERT INTO radio_activity_5m (
                    bucket_start_utc, bucket_end_utc, interface_id, source_name,
                    rx_total, tx_total, digipeated_total, own_frames_total,
                    messages_total, queries_total, objects_total, wx_total,
                    position_total, mobile_total, fixed_total, unique_stations_total,
                    direct_heard_total, indirect_heard_total, rfonly_total, nogate_total,
                    invalid_total, parse_error_total, duplicate_total,
                    type_position_total, type_weather_total, type_message_total, type_object_item_total,
                    type_status_total, type_telemetry_total, type_query_total, type_user_defined_total,
                    type_third_party_total, type_other_unknown_total,
                    max_hops_seen, avg_hops,
                    created_at_utc, updated_at_utc
                )
                VALUES (
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?,
                    ?, ?,
                    ?, ?
                )
                ON CONFLICT(bucket_start_utc, source_name) DO UPDATE SET
                    bucket_end_utc = excluded.bucket_end_utc,
                    interface_id = excluded.interface_id,
                    rx_total = excluded.rx_total,
                    tx_total = excluded.tx_total,
                    digipeated_total = excluded.digipeated_total,
                    own_frames_total = excluded.own_frames_total,
                    messages_total = excluded.messages_total,
                    queries_total = excluded.queries_total,
                    objects_total = excluded.objects_total,
                    wx_total = excluded.wx_total,
                    position_total = excluded.position_total,
                    mobile_total = excluded.mobile_total,
                    fixed_total = excluded.fixed_total,
                    unique_stations_total = excluded.unique_stations_total,
                    direct_heard_total = excluded.direct_heard_total,
                    indirect_heard_total = excluded.indirect_heard_total,
                    rfonly_total = excluded.rfonly_total,
                    nogate_total = excluded.nogate_total,
                    invalid_total = excluded.invalid_total,
                    parse_error_total = excluded.parse_error_total,
                    duplicate_total = excluded.duplicate_total,
                    type_position_total = excluded.type_position_total,
                    type_weather_total = excluded.type_weather_total,
                    type_message_total = excluded.type_message_total,
                    type_object_item_total = excluded.type_object_item_total,
                    type_status_total = excluded.type_status_total,
                    type_telemetry_total = excluded.type_telemetry_total,
                    type_query_total = excluded.type_query_total,
                    type_user_defined_total = excluded.type_user_defined_total,
                    type_third_party_total = excluded.type_third_party_total,
                    type_other_unknown_total = excluded.type_other_unknown_total,
                    max_hops_seen = excluded.max_hops_seen,
                    avg_hops = excluded.avg_hops,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (
                    bucket_start_iso,
                    bucket_end_iso,
                    row.get("interface_id"),
                    str(row.get("source_name") or "").strip() or "Unknown source",
                    int(row.get("rx_total") or 0),
                    int(row.get("tx_total") or 0),
                    int(row.get("digipeated_total") or 0),
                    int(row.get("own_frames_total") or 0),
                    int(row.get("messages_total") or 0),
                    int(row.get("queries_total") or 0),
                    int(row.get("objects_total") or 0),
                    int(row.get("wx_total") or 0),
                    int(row.get("position_total") or 0),
                    int(row.get("mobile_total") or 0),
                    int(row.get("fixed_total") or 0),
                    int(row.get("unique_stations_total") or 0),
                    int(row.get("direct_heard_total") or 0),
                    int(row.get("indirect_heard_total") or 0),
                    int(row.get("rfonly_total") or 0),
                    int(row.get("nogate_total") or 0),
                    int(row.get("invalid_total") or 0),
                    int(row.get("parse_error_total") or 0),
                    int(row.get("duplicate_total") or 0),
                    int(row.get("type_position_total") or 0),
                    int(row.get("type_weather_total") or 0),
                    int(row.get("type_message_total") or 0),
                    int(row.get("type_object_item_total") or 0),
                    int(row.get("type_status_total") or 0),
                    int(row.get("type_telemetry_total") or 0),
                    int(row.get("type_query_total") or 0),
                    int(row.get("type_user_defined_total") or 0),
                    int(row.get("type_third_party_total") or 0),
                    int(row.get("type_other_unknown_total") or 0),
                    _int_or_none(row.get("max_hops_seen")),
                    float(row["avg_hops"]) if row.get("avg_hops") is not None else None,
                    now_utc,
                    now_utc,
                ),
            )


def _prune_radio_activity_history(*, now_utc: datetime) -> None:
    cutoff_utc = (_normalize_utc_datetime(now_utc) - timedelta(days=RADIO_ACTIVITY_RETENTION_DAYS)).replace(microsecond=0)
    with get_connection() as connection:
        connection.execute(
            """
            DELETE FROM radio_activity_5m
            WHERE bucket_start_utc < ?
            """,
            (cutoff_utc.isoformat(),),
        )


def _classify_frame_type_bucket_key(*, parsed: dict[str, Any]) -> str:
    if bool(parsed.get("is_third_party")):
        return "type_third_party_total"
    logical_info = str(parsed.get("logical_info") or parsed.get("info") or "")
    if logical_info.startswith("{"):
        return "type_user_defined_total"

    aprs_data = dict(parsed.get("aprs_data") or {})
    packet_group = str(aprs_data.get("packet_group") or "").strip().lower()
    if packet_group == "position":
        return "type_position_total"
    if packet_group == "weather":
        return "type_weather_total"
    if packet_group == "message":
        return "type_message_total"
    if packet_group in {"object", "item"}:
        return "type_object_item_total"
    if packet_group == "status":
        return "type_status_total"
    if packet_group == "telemetry":
        return "type_telemetry_total"
    if packet_group == "query":
        return "type_query_total"
    return "type_other_unknown_total"


def _oldest_closed_bucket_start(
    *,
    latest_closed_bucket_start_utc: datetime,
    bucket_minutes: int,
) -> datetime | None:
    oldest_row = fetch_one(
        f"""
        SELECT created_at
        FROM traffic_frames
        WHERE created_at < ?
          AND {STATISTICS_TRAFFIC_SQL_PREDICATE}
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        ((latest_closed_bucket_start_utc + timedelta(minutes=bucket_minutes)).isoformat(),),
    )
    if oldest_row is None:
        return None
    oldest_frame = _parse_iso_timestamp_utc(str(oldest_row["created_at"] or ""))
    if oldest_frame is None:
        return None
    return _floor_to_bucket_start(oldest_frame, bucket_minutes=bucket_minutes)


def _latest_closed_bucket_start(
    *,
    now_utc: datetime,
    bucket_minutes: int,
    safety_delay_seconds: int,
) -> datetime | None:
    safe_now = _normalize_utc_datetime(now_utc) - timedelta(seconds=max(0, int(safety_delay_seconds)))
    safe_bucket_start = _floor_to_bucket_start(safe_now, bucket_minutes=bucket_minutes)
    latest_closed_start = safe_bucket_start - timedelta(minutes=bucket_minutes)
    if latest_closed_start.year < 1970:
        return None
    return latest_closed_start


def _floor_to_bucket_start(value: datetime, *, bucket_minutes: int) -> datetime:
    normalized = _normalize_utc_datetime(value)
    bucket_seconds = max(60, int(bucket_minutes) * 60)
    floored_epoch = (int(normalized.timestamp()) // bucket_seconds) * bucket_seconds
    return datetime.fromtimestamp(floored_epoch, tz=timezone.utc).replace(second=0, microsecond=0)


def _get_aggregator_state(state_key: str) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT key, last_processed_bucket_start_utc, last_run_utc, last_error, updated_at_utc
        FROM radio_activity_aggregator_state
        WHERE key = ?
        """,
        (state_key,),
    )
    return dict(row) if row is not None else None


def _upsert_aggregator_state(
    state_key: str,
    *,
    last_processed_bucket_start_utc: str | None,
    last_run_utc: str | None,
    last_error: str | None,
) -> None:
    updated_at = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO radio_activity_aggregator_state (
                key, last_processed_bucket_start_utc, last_run_utc, last_error, updated_at_utc
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                last_processed_bucket_start_utc = excluded.last_processed_bucket_start_utc,
                last_run_utc = excluded.last_run_utc,
                last_error = excluded.last_error,
                updated_at_utc = excluded.updated_at_utc
            """,
            (state_key, last_processed_bucket_start_utc, last_run_utc, last_error, updated_at),
        )


def _station_identity_keys() -> tuple[str, str, str]:
    station_row = fetch_one("SELECT callsign, ssid FROM station_settings WHERE id = 1")
    wx_row = fetch_one("SELECT callsign, ssid FROM wx_config WHERE id = 1")
    station_source_key = _build_source_key(
        str(_row_value(station_row, "callsign", "") or ""),
        str(_row_value(station_row, "ssid", "") or ""),
    )
    station_callsign = station_source_key.partition("-")[0]
    wx_source_key = _build_source_key(
        str(_row_value(wx_row, "callsign", "") or ""),
        str(_row_value(wx_row, "ssid", "") or ""),
    )
    return station_source_key, station_callsign, wx_source_key


def _build_source_key(callsign: str, ssid: str) -> str:
    normalized_callsign = str(callsign or "").strip().upper()
    normalized_ssid = str(ssid or "").strip()
    if normalized_ssid == "0":
        normalized_ssid = ""
    if not normalized_callsign:
        return ""
    if normalized_ssid:
        return f"{normalized_callsign}-{normalized_ssid}"
    return normalized_callsign


def _split_path_tokens(path: str) -> list[str]:
    return [item.strip().upper() for item in str(path or "").split(",") if item.strip()]


def _new_source_bucket(source_name: str) -> dict[str, Any]:
    row: dict[str, Any] = {"source_name": source_name, "interface_id": None}
    row.update({key: value for key, value in _SOURCE_BUCKET_DEFAULTS.items()})
    row["_unique_station_keys"] = set()
    row["_hop_count_total"] = 0
    row["_hop_samples"] = 0
    return row


def _normalize_direction(direction: Any, frame_format: Any) -> str:
    normalized_direction = str(direction or "").strip().upper()
    if normalized_direction in {"RX", "TX"}:
        return normalized_direction
    normalized_format = str(frame_format or "").strip().upper()
    if normalized_format.endswith("-TX"):
        return "TX"
    return "RX"


def _parse_iso_timestamp_utc(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _normalize_utc_datetime(parsed)


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _int_or_none(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        return row[key]
    except Exception:
        return default
