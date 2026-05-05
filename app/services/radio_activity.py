from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db import fetch_all, fetch_one, get_connection, log_event, utc_now
from app.services.aprs_device_identification import get_aprs_device_identification_database, lookup_aprs_device_identification
from app.services.content import parse_tnc2_frame


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
TRAFFIC_STATISTICS_RANGE_24H = "24h"
TRAFFIC_STATISTICS_RANGE_7D = "7d"
TRAFFIC_STATISTICS_RANGE_30D = "30d"
TRAFFIC_STATISTICS_RANGE_365D = "365d"
TRAFFIC_STATISTICS_RANGE_OPTIONS = {
    TRAFFIC_STATISTICS_RANGE_6H: 6 * 60,
    TRAFFIC_STATISTICS_RANGE_24H: 24 * 60,
    TRAFFIC_STATISTICS_RANGE_7D: 7 * 24 * 60,
    TRAFFIC_STATISTICS_RANGE_30D: 30 * 24 * 60,
    TRAFFIC_STATISTICS_RANGE_365D: 365 * 24 * 60,
}
TRAFFIC_STATISTICS_DEVICES_MODE_STATIONS = "stations"
TRAFFIC_STATISTICS_DEVICES_MODE_FRAMES = "frames"
TRAFFIC_STATISTICS_DEVICES_MODE_OPTIONS = {
    TRAFFIC_STATISTICS_DEVICES_MODE_STATIONS,
    TRAFFIC_STATISTICS_DEVICES_MODE_FRAMES,
}
TRAFFIC_STATISTICS_DEVICES_DEFAULT_TOP_LIMIT = 8
TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY = "unknown"
TRAFFIC_STATISTICS_DEVICES_UNKNOWN_LABEL = "Unknown"
TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_KEY = "mixed_unknown"
TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_LABEL = "Mixed / Unknown"
TRAFFIC_STATISTICS_DEVICES_OTHER_KEY = "other"
TRAFFIC_STATISTICS_DEVICES_OTHER_LABEL = "Other"
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
            source_rows = _collect_bucket_source_rows(
                bucket_start_utc=current_bucket_start,
                bucket_end_utc=current_bucket_end,
            )
            _upsert_radio_activity_bucket_rows(
                bucket_start_utc=current_bucket_start,
                bucket_end_utc=current_bucket_end,
                source_rows=source_rows,
            )
            processed_buckets += 1
            last_processed_for_state = current_bucket_start
            current_bucket_start = current_bucket_end

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
    }
    totals = {key: 0 for key in series}

    for index in range(output_bucket_count):
        bucket_start_utc = window_start_utc + timedelta(minutes=output_bucket_minutes * index)
        bucket_start_key = bucket_start_utc.isoformat()
        bucket_starts.append(bucket_start_key)
        labels.append(_format_radio_activity_label(bucket_start_utc, output_bucket_minutes=output_bucket_minutes))
        row = row_by_bucket_start.get(bucket_start_key) or {}
        for key in series:
            value = int(row.get(key) or 0)
            series[key].append(value)
            totals[key] += value

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
    }


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
    mode: str = TRAFFIC_STATISTICS_DEVICES_MODE_STATIONS,
    top_limit: int = TRAFFIC_STATISTICS_DEVICES_DEFAULT_TOP_LIMIT,
) -> dict[str, Any]:
    normalized_range = str(range_value or TRAFFIC_STATISTICS_RANGE_24H).strip().lower()
    if normalized_range not in TRAFFIC_STATISTICS_RANGE_OPTIONS:
        raise ValueError("Unsupported range.")
    normalized_shift_windows = int(shift_windows)
    if normalized_shift_windows < 0:
        raise ValueError("Unsupported range.")
    normalized_mode = str(mode or TRAFFIC_STATISTICS_DEVICES_MODE_STATIONS).strip().lower()
    if normalized_mode not in TRAFFIC_STATISTICS_DEVICES_MODE_OPTIONS:
        raise ValueError("Unsupported mode.")
    normalized_top_limit = max(1, int(top_limit))

    total_minutes = int(TRAFFIC_STATISTICS_RANGE_OPTIONS[normalized_range])
    output_bucket_minutes = _resolve_traffic_statistics_bucket_minutes(total_minutes)
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

    frame_rows = fetch_all(
        """
        SELECT direction, format, line, created_at
        FROM traffic_frames
        WHERE format LIKE 'TNC2%'
          AND created_at >= ?
          AND created_at < ?
        ORDER BY created_at ASC, id ASC
        """,
        (window_start_utc.isoformat(), window_end_utc.isoformat()),
    )

    labels_by_key: dict[str, str] = {
        TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY: TRAFFIC_STATISTICS_DEVICES_UNKNOWN_LABEL,
        TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_KEY: TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_LABEL,
        TRAFFIC_STATISTICS_DEVICES_OTHER_KEY: TRAFFIC_STATISTICS_DEVICES_OTHER_LABEL,
    }
    device_db = get_aprs_device_identification_database()
    destination_cache: dict[str, tuple[str, str, bool]] = {}

    if normalized_mode == TRAFFIC_STATISTICS_DEVICES_MODE_FRAMES:
        frame_counts: dict[str, int] = {}
        for row in frame_rows:
            frame_format = str(row["format"] or "").strip().upper()
            direction = _normalize_direction(row["direction"], frame_format)
            if direction != "RX":
                continue
            parsed = parse_tnc2_frame(str(row["line"] or ""))
            if parsed is None:
                continue
            device_key, device_label, _is_recognized = _resolve_statistics_device_bucket(
                str(parsed.get("logical_destination") or parsed.get("destination") or ""),
                database=device_db,
                cache=destination_cache,
            )
            frame_counts[device_key] = int(frame_counts.get(device_key) or 0) + 1
            labels_by_key[device_key] = device_label

        total = sum(frame_counts.values())
        items = _build_traffic_devices_items(
            counts=frame_counts,
            labels_by_key=labels_by_key,
            total=total,
            top_limit=normalized_top_limit,
        )
        return {
            "range": normalized_range,
            "shift_windows": normalized_shift_windows,
            "mode": normalized_mode,
            "count_basis": "frames",
            "total": total,
            "top_limit": normalized_top_limit,
            "window_start_utc": window_start_utc.isoformat(),
            "window_end_utc": window_end_utc.isoformat(),
            "items": items,
        }

    station_votes: dict[str, dict[str, Any]] = {}
    for row_index, row in enumerate(frame_rows):
        frame_format = str(row["format"] or "").strip().upper()
        direction = _normalize_direction(row["direction"], frame_format)
        if direction != "RX":
            continue
        parsed = parse_tnc2_frame(str(row["line"] or ""))
        if parsed is None:
            continue
        station_key = str(parsed.get("logical_source_key") or parsed.get("source_key") or parsed.get("source") or "").strip().upper()
        if not station_key:
            continue
        device_key, device_label, is_recognized = _resolve_statistics_device_bucket(
            str(parsed.get("logical_destination") or parsed.get("destination") or ""),
            database=device_db,
            cache=destination_cache,
        )
        labels_by_key[device_key] = device_label

        station_bucket = station_votes.get(station_key)
        if station_bucket is None:
            station_bucket = {
                "counts": {},
                "last_index_by_key": {},
                "recognized_by_key": {},
            }
            station_votes[station_key] = station_bucket

        counts_by_key = station_bucket["counts"]
        counts_by_key[device_key] = int(counts_by_key.get(device_key) or 0) + 1
        station_bucket["last_index_by_key"][device_key] = row_index
        if is_recognized:
            station_bucket["recognized_by_key"][device_key] = True
        elif device_key not in station_bucket["recognized_by_key"]:
            station_bucket["recognized_by_key"][device_key] = False

    station_counts: dict[str, int] = {}
    for station_bucket in station_votes.values():
        resolved_key = _resolve_station_device_bucket_key(station_bucket)
        resolved_label = labels_by_key.get(resolved_key) or (
            TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_LABEL
            if resolved_key == TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_KEY
            else TRAFFIC_STATISTICS_DEVICES_UNKNOWN_LABEL
        )
        labels_by_key[resolved_key] = resolved_label
        station_counts[resolved_key] = int(station_counts.get(resolved_key) or 0) + 1

    total = sum(station_counts.values())
    items = _build_traffic_devices_items(
        counts=station_counts,
        labels_by_key=labels_by_key,
        total=total,
        top_limit=normalized_top_limit,
    )
    return {
        "range": normalized_range,
        "shift_windows": normalized_shift_windows,
        "mode": normalized_mode,
        "count_basis": "unique_callsign_ssid",
        "total": total,
        "top_limit": normalized_top_limit,
        "window_start_utc": window_start_utc.isoformat(),
        "window_end_utc": window_end_utc.isoformat(),
        "items": items,
    }


def _resolve_statistics_device_bucket(
    destination: str,
    *,
    database: Any,
    cache: dict[str, tuple[str, str, bool]],
) -> tuple[str, str, bool]:
    normalized_destination = _normalize_statistics_destination(destination)
    if not normalized_destination:
        return (
            TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY,
            TRAFFIC_STATISTICS_DEVICES_UNKNOWN_LABEL,
            False,
        )
    cached = cache.get(normalized_destination)
    if cached is not None:
        return cached

    matched = lookup_aprs_device_identification(destination=normalized_destination, info="", database=database)
    if matched is not None:
        key = str(matched.get("actual_identifier") or normalized_destination).strip().upper() or normalized_destination
        label = str(matched.get("short_name") or matched.get("identified_as") or key).strip() or key
        resolved = (key, label, True)
    else:
        resolved = (normalized_destination, normalized_destination, True)
    cache[normalized_destination] = resolved
    return resolved


def _normalize_statistics_destination(destination: str) -> str:
    value = str(destination or "").strip().upper()
    base, separator, suffix = value.partition("-")
    if separator and suffix.isdigit():
        value = base
    return value


def _resolve_station_device_bucket_key(station_bucket: dict[str, Any]) -> str:
    counts_by_key = dict(station_bucket.get("counts") or {})
    if not counts_by_key:
        return TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY

    max_count = max(int(value) for value in counts_by_key.values())
    top_keys = [str(key) for key, value in counts_by_key.items() if int(value) == max_count]
    if len(top_keys) == 1:
        return top_keys[0]

    recognized_by_key = dict(station_bucket.get("recognized_by_key") or {})
    last_index_by_key = dict(station_bucket.get("last_index_by_key") or {})
    recognized_top_keys = [key for key in top_keys if bool(recognized_by_key.get(key))]
    if recognized_top_keys:
        recognized_top_keys.sort(key=lambda key: int(last_index_by_key.get(key) or 0), reverse=True)
        best_key = recognized_top_keys[0]
        best_index = int(last_index_by_key.get(best_key) or 0)
        best_keys = [key for key in recognized_top_keys if int(last_index_by_key.get(key) or 0) == best_index]
        if len(best_keys) == 1:
            return best_key
    return TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_KEY


def _build_traffic_devices_items(
    *,
    counts: dict[str, int],
    labels_by_key: dict[str, str],
    total: int,
    top_limit: int,
) -> list[dict[str, Any]]:
    if total <= 0:
        return []

    non_zero_counts = {str(key): int(value) for key, value in counts.items() if int(value) > 0}
    if not non_zero_counts:
        return []

    special_keys = {
        TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY,
        TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_KEY,
    }
    regular_items = [(key, value) for key, value in non_zero_counts.items() if key not in special_keys]
    regular_items.sort(key=lambda item: (-item[1], str(labels_by_key.get(item[0]) or item[0]).casefold(), item[0]))

    normalized_top_limit = max(1, int(top_limit))
    selected_regular = regular_items[:normalized_top_limit]
    remaining_regular = regular_items[normalized_top_limit:]
    other_count = sum(count for _key, count in remaining_regular)

    items: list[dict[str, Any]] = []
    for key, count in selected_regular:
        label = str(labels_by_key.get(key) or key).strip() or key
        items.append(_traffic_devices_item(key=key, label=label, count=count, total=total))

    for special_key, special_label in (
        (TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_KEY, TRAFFIC_STATISTICS_DEVICES_MIXED_UNKNOWN_LABEL),
        (TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY, TRAFFIC_STATISTICS_DEVICES_UNKNOWN_LABEL),
    ):
        special_count = int(non_zero_counts.get(special_key) or 0)
        if special_count <= 0:
            continue
        label = str(labels_by_key.get(special_key) or special_label).strip() or special_label
        items.append(_traffic_devices_item(key=special_key, label=label, count=special_count, total=total))

    if other_count > 0:
        items.append(
            _traffic_devices_item(
                key=TRAFFIC_STATISTICS_DEVICES_OTHER_KEY,
                label=str(labels_by_key.get(TRAFFIC_STATISTICS_DEVICES_OTHER_KEY) or TRAFFIC_STATISTICS_DEVICES_OTHER_LABEL),
                count=other_count,
                total=total,
            )
        )
    return items


def _traffic_devices_item(*, key: str, label: str, count: int, total: int) -> dict[str, Any]:
    normalized_count = max(0, int(count))
    normalized_total = max(0, int(total))
    percent = 0.0
    if normalized_total > 0:
        percent = round((float(normalized_count) * 100.0) / float(normalized_total), 1)
    return {
        "key": str(key or "").strip() or TRAFFIC_STATISTICS_DEVICES_UNKNOWN_KEY,
        "label": str(label or "").strip() or TRAFFIC_STATISTICS_DEVICES_UNKNOWN_LABEL,
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
) -> list[dict[str, Any]]:
    frame_rows = fetch_all(
        """
        SELECT source, interface_id, direction, format, line, command
        FROM traffic_frames
        WHERE created_at >= ?
          AND created_at < ?
        ORDER BY created_at ASC, id ASC
        """,
        (bucket_start_utc.isoformat(), bucket_end_utc.isoformat()),
    )
    if not frame_rows:
        return []

    station_source_key, station_callsign, wx_source_key = _station_identity_keys()
    grouped: dict[str, dict[str, Any]] = {}

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
    return source_rows


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
        """
        SELECT created_at
        FROM traffic_frames
        WHERE created_at < ?
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
