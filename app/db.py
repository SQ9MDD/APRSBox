from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import settings

DEFAULT_EVENT_LOG_KEEP_ROWS = 5000
EVENT_LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR")
EVENT_LOG_MIN_LEVEL_SETTING_KEY = "event_log_min_level"
EVENT_LOG_DEBUG_ENABLED_SETTING_KEY = "event_log_debug_enabled"
DEFAULT_EVENT_LOG_MIN_LEVEL = "INFO"
_EVENT_LOG_LEVEL_RANK = {level: index for index, level in enumerate(EVENT_LOG_LEVELS)}

_event_log_min_level_cache: str | None = None
_event_log_debug_enabled_cache: bool | None = None

RUNTIME_MAINTENANCE_RESET_TABLES: tuple[str, ...] = (
    "event_logs",
    "traffic_frames",
    "digi_flow_event_log",
    "traffic_device_station_device_hourly",
    "radio_activity_5m",
    "aprsis_uplink_minute_stats",
    "aprsis_uplink_stats",
    "wx_runtime_cache",
    "band_condition_audibility_buckets",
    "band_condition_activity_station_buckets",
    "band_condition_activity_buckets",
)
VACUUM_RECOMMEND_FREE_BYTES_MIN = 16 * 1024 * 1024
VACUUM_RECOMMEND_FREE_RATIO_MIN = 0.20


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_runtime_dirs() -> None:
    for directory in (
        settings.data_dir,
        settings.log_dir,
        settings.config_dir,
        settings.backups_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    ensure_runtime_dirs()
    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    connection = connect()
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'operator', 'viewer')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    last_login_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS map_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url_template TEXT NOT NULL,
    attribution TEXT NOT NULL DEFAULT '',
    min_zoom INTEGER NOT NULL DEFAULT 0 CHECK (min_zoom BETWEEN 0 AND 30),
    max_zoom INTEGER NOT NULL DEFAULT 19 CHECK (max_zoom BETWEEN 0 AND 30),
    subdomains TEXT NOT NULL DEFAULT '',
    api_key TEXT NOT NULL DEFAULT '',
    local_cache_enabled INTEGER NOT NULL DEFAULT 0 CHECK (local_cache_enabled IN (0, 1)),
    cache_tile_count INTEGER NOT NULL DEFAULT 0 CHECK (cache_tile_count >= 0),
    cache_size_bytes INTEGER NOT NULL DEFAULT 0 CHECK (cache_size_bytes >= 0),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (min_zoom <= max_zoom),
    CHECK (NOT (enabled = 0 AND is_default = 1))
);

CREATE TABLE IF NOT EXISTS system_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'success', 'error')),
    message TEXT NOT NULL DEFAULT '',
    log_file TEXT,
    pid INTEGER,
    exit_code INTEGER,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS modems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    modem_type TEXT NOT NULL,
    band TEXT NOT NULL DEFAULT '',
    device_path TEXT,
    baud_rate INTEGER,
    serial_rx_silence_reconnect_seconds INTEGER NOT NULL DEFAULT 150
        CHECK (serial_rx_silence_reconnect_seconds IN (0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 360, 390, 420, 450, 480, 510, 540, 570, 600)),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    tx_blocked INTEGER NOT NULL DEFAULT 0 CHECK (tx_blocked IN (0, 1)),
    tx_min_gap_seconds REAL NOT NULL DEFAULT 0.35
        CHECK (tx_min_gap_seconds >= 0.2 AND tx_min_gap_seconds <= 1.2),
    expose_port_enabled INTEGER NOT NULL DEFAULT 0 CHECK (expose_port_enabled IN (0, 1)),
    expose_allow_tx INTEGER NOT NULL DEFAULT 1 CHECK (expose_allow_tx IN (0, 1)),
    expose_bind_address TEXT NOT NULL DEFAULT '0.0.0.0',
    expose_port INTEGER NOT NULL DEFAULT 8002 CHECK (expose_port BETWEEN 1 AND 65535),
    expose_whitelist TEXT NOT NULL DEFAULT '',
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aprsis_servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    use_tls INTEGER NOT NULL DEFAULT 0 CHECK (use_tls IN (0, 1)),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS station_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    callsign TEXT,
    ssid TEXT,
    beacon_interface_id INTEGER,
    beacon_tx_scope TEXT NOT NULL DEFAULT 'single' CHECK (beacon_tx_scope IN ('single', 'all_active')),
    beacon_comment TEXT,
    beacon_interval_mode TEXT NOT NULL DEFAULT 'fixed' CHECK (beacon_interval_mode IN ('fixed', 'proportional')),
    beacon_interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (beacon_interval_minutes IN (15, 30, 45, 60)),
    beacon_path TEXT,
    status_enabled INTEGER NOT NULL DEFAULT 0 CHECK (status_enabled IN (0, 1)),
    status_text TEXT,
    status_interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (status_interval_minutes IN (15, 30, 45, 60)),
    latitude TEXT,
    longitude TEXT,
    symbol_table TEXT,
    symbol_code TEXT,
    symbol_overlay TEXT,
    default_units TEXT NOT NULL DEFAULT 'metric' CHECK (default_units IN ('metric', 'imperial')),
    tx_enabled INTEGER NOT NULL DEFAULT 0 CHECK (tx_enabled IN (0, 1)),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wx_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    callsign TEXT NOT NULL DEFAULT '',
    ssid TEXT NOT NULL DEFAULT '',
    beacon_interface_id INTEGER,
    beacon_tx_scope TEXT NOT NULL DEFAULT 'single' CHECK (beacon_tx_scope IN ('single', 'all_active')),
    path TEXT NOT NULL DEFAULT '',
    latitude TEXT NOT NULL DEFAULT '',
    longitude TEXT NOT NULL DEFAULT '',
    refresh_interval_s INTEGER NOT NULL DEFAULT 300 CHECK (refresh_interval_s BETWEEN 15 AND 3600),
    allow_cache_fallback INTEGER NOT NULL DEFAULT 1 CHECK (allow_cache_fallback IN (0, 1)),
    default_cache_max_age_s INTEGER NOT NULL DEFAULT 900 CHECK (default_cache_max_age_s BETWEEN 1 AND 86400),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (beacon_interface_id) REFERENCES modems(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS wx_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL CHECK (source_type IN ('home_assistant', 'domoticz')),
    base_url TEXT NOT NULL,
    auth_type TEXT NOT NULL CHECK (auth_type IN ('none', 'bearer', 'basic')),
    auth_payload TEXT NOT NULL DEFAULT '{}',
    timeout_s INTEGER NOT NULL DEFAULT 5 CHECK (timeout_s BETWEEN 1 AND 60),
    verify_tls INTEGER NOT NULL DEFAULT 1 CHECK (verify_tls IN (0, 1)),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    last_test_status TEXT NOT NULL DEFAULT '' CHECK (last_test_status IN ('', 'ok', 'error')),
    last_test_error TEXT NOT NULL DEFAULT '',
    last_test_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wx_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parameter_name TEXT NOT NULL UNIQUE,
    required_flag INTEGER NOT NULL DEFAULT 0 CHECK (required_flag IN (0, 1)),
    source_id INTEGER,
    identifier TEXT NOT NULL DEFAULT '',
    value_selector TEXT NOT NULL DEFAULT '',
    transform_config_json TEXT NOT NULL DEFAULT '{}',
    cache_max_age_s INTEGER CHECK (cache_max_age_s IS NULL OR cache_max_age_s BETWEEN 1 AND 86400),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES wx_sources(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS wx_runtime_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parameter_name TEXT NOT NULL UNIQUE,
    source_id INTEGER,
    identifier TEXT NOT NULL DEFAULT '',
    raw_value TEXT,
    raw_unit TEXT,
    normalized_value TEXT,
    normalized_unit TEXT,
    value_origin TEXT NOT NULL DEFAULT 'missing',
    status TEXT NOT NULL DEFAULT 'MISSING' CHECK (status IN ('LIVE', 'CACHED', 'STALE', 'MISSING', 'ERROR')),
    last_success_at TEXT,
    last_attempt_at TEXT,
    last_error TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES wx_sources(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS outbound_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    interface_id INTEGER,
    aprs_message_id INTEGER,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'sent', 'failed', 'cancelled')),
    scheduled_at TEXT NOT NULL,
    locked_at TEXT,
    started_at TEXT,
    sent_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (interface_id) REFERENCES modems(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS aprs_message_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    remote_callsign TEXT NOT NULL,
    remote_ssid TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (remote_callsign, remote_ssid)
);

CREATE TABLE IF NOT EXISTS aprs_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('rx', 'tx')),
    sender TEXT NOT NULL,
    addressee TEXT NOT NULL,
    message_text TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    message_number TEXT,
    status TEXT NOT NULL CHECK (status IN ('queued', 'sent', 'acked', 'rejected', 'failed', 'received')),
    tx_attempt_count INTEGER NOT NULL DEFAULT 0,
    is_unread INTEGER NOT NULL DEFAULT 0 CHECK (is_unread IN (0, 1)),
    outbound_job_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    sent_at TEXT,
    acked_at TEXT,
    last_attempt_at TEXT,
    failed_at TEXT,
    failure_reason TEXT,
    FOREIGN KEY (conversation_id) REFERENCES aprs_message_conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (outbound_job_id) REFERENCES outbound_jobs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS igate_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
    direction TEXT NOT NULL DEFAULT 'rx-only',
    policy_text TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digi_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
    source_match TEXT,
    destination_match TEXT,
    path_rewrite TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digi_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('receiver_rf', 'receiver_aprsis', 'receiver_local_tx')),
    source_ref TEXT NOT NULL,
    target_kind TEXT NOT NULL CHECK (target_kind IN ('tx_rf', 'tx_aprsis', 'action_drop', 'action_log')),
    target_ref TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digi_flow_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flow_id INTEGER NOT NULL,
    step_order INTEGER NOT NULL,
    step_type TEXT NOT NULL CHECK (step_type IN (
        'receiver_rf',
        'receiver_aprsis',
        'receiver_local_tx',
        'filter_dupe',
        'filter_direct_only',
        'filter_digi',
        'filter_path',
        'filter_strict',
        'filter_callsign',
        'filter_packet_type',
        'filter_icon',
        'filter_distance',
        'filter_rate_limit',
        'filter_rate_limit_per_callsign',
        'tx_rf',
        'tx_aprsis',
        'action_drop',
        'action_log'
    )),
    title TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (flow_id) REFERENCES digi_flows(id) ON DELETE CASCADE,
    UNIQUE (flow_id, step_order)
);

CREATE TABLE IF NOT EXISTS digi_flow_event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_uid TEXT NOT NULL,
    flow_id INTEGER NOT NULL,
    step_id INTEGER,
    event_type TEXT NOT NULL,
    decision TEXT,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (flow_id) REFERENCES digi_flows(id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES digi_flow_steps(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS aprs_objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    lifetime TEXT NOT NULL DEFAULT 'temporary' CHECK (lifetime IN ('temporary', 'permanent')),
    state TEXT NOT NULL DEFAULT 'live' CHECK (state IN ('live', 'killed')),
    is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0, 1)),
    interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (interval_minutes IN (5, 10, 15, 30, 45, 60)),
    valid_until_utc TEXT,
    latitude TEXT,
    longitude TEXT,
    symbol_table TEXT,
    symbol_code TEXT,
    symbol_overlay TEXT,
    path TEXT,
    comment TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aprs_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL DEFAULT 'live' CHECK (state IN ('live', 'killed')),
    is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0, 1)),
    interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (interval_minutes IN (5, 10, 15, 30, 45, 60)),
    latitude TEXT,
    longitude TEXT,
    symbol_table TEXT,
    symbol_code TEXT,
    symbol_overlay TEXT,
    path TEXT,
    comment TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bulletins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_kind TEXT NOT NULL DEFAULT 'bulletin' CHECK (message_kind IN ('bulletin', 'announcement', 'group_bulletin')),
    addressee TEXT,
    bulletin_code TEXT,
    group_name TEXT,
    is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0, 1)),
    interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (interval_minutes IN (5, 10, 15, 30, 45, 60)),
    valid_until_utc TEXT,
    path TEXT,
    message_text TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS traffic_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    interface_id INTEGER,
    direction TEXT,
    band TEXT,
    format TEXT NOT NULL,
    line TEXT NOT NULL,
    port TEXT,
    command TEXT,
    length INTEGER NOT NULL,
    hex TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS traffic_device_station_device_hourly (
    bucket_start_utc TEXT NOT NULL,
    station_key TEXT NOT NULL,
    device_key TEXT NOT NULL,
    destination_key TEXT NOT NULL,
    device_label TEXT NOT NULL,
    recognized_flag INTEGER NOT NULL DEFAULT 0 CHECK (recognized_flag IN (0, 1)),
    frame_count INTEGER NOT NULL DEFAULT 0,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (bucket_start_utc, station_key, device_key, destination_key)
);

CREATE TABLE IF NOT EXISTS traffic_runtime_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    status TEXT NOT NULL,
    status_detail TEXT NOT NULL,
    active_modem_name TEXT,
    active_modem_endpoint TEXT,
    expose_port_enabled INTEGER NOT NULL DEFAULT 0 CHECK (expose_port_enabled IN (0, 1)),
    expose_bind_address TEXT,
    expose_port INTEGER,
    expose_active_clients INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aprsis_runtime_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    status TEXT NOT NULL DEFAULT 'inactive' CHECK (status IN ('inactive', 'connecting', 'connected', 'error')),
    status_detail TEXT NOT NULL DEFAULT '',
    server TEXT,
    port INTEGER,
    login TEXT,
    connected_at TEXT,
    last_error TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aprsis_uplink_stats (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    tx_total INTEGER NOT NULL DEFAULT 0,
    drop_total INTEGER NOT NULL DEFAULT 0,
    strict_total INTEGER NOT NULL DEFAULT 0,
    strict_blocked_tcpip_tcpxx_total INTEGER NOT NULL DEFAULT 0,
    strict_blocked_nogate_rfonly_total INTEGER NOT NULL DEFAULT 0,
    strict_malformed_third_party_total INTEGER NOT NULL DEFAULT 0,
    strict_other_total INTEGER NOT NULL DEFAULT 0,
    last_sent_at TEXT,
    last_sent_line TEXT,
    last_drop_at TEXT,
    last_drop_line TEXT,
    last_strict_reject_at TEXT,
    last_strict_reject_line TEXT,
    last_strict_reject_reason TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aprsis_uplink_minute_stats (
    bucket_minute_utc TEXT PRIMARY KEY,
    tx_count INTEGER NOT NULL DEFAULT 0,
    drop_count INTEGER NOT NULL DEFAULT 0,
    strict_count INTEGER NOT NULL DEFAULT 0,
    strict_blocked_tcpip_tcpxx_count INTEGER NOT NULL DEFAULT 0,
    strict_blocked_nogate_rfonly_count INTEGER NOT NULL DEFAULT 0,
    strict_malformed_third_party_count INTEGER NOT NULL DEFAULT 0,
    strict_other_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS traffic_runtime_interfaces (
    modem_id INTEGER PRIMARY KEY,
    modem_name TEXT NOT NULL,
    modem_endpoint TEXT,
    band TEXT,
    status TEXT NOT NULL,
    status_detail TEXT NOT NULL,
    expose_port_enabled INTEGER NOT NULL DEFAULT 0 CHECK (expose_port_enabled IN (0, 1)),
    expose_bind_address TEXT,
    expose_port INTEGER,
    expose_active_clients INTEGER NOT NULL DEFAULT 0,
    mqtt_connected INTEGER NOT NULL DEFAULT 0 CHECK (mqtt_connected IN (0, 1)),
    mqtt_subscribed_topic TEXT,
    mqtt_broker_host TEXT,
    mqtt_broker_port INTEGER,
    mqtt_last_frame_at TEXT,
    mqtt_frames_received INTEGER NOT NULL DEFAULT 0,
    mqtt_duplicates_dropped INTEGER NOT NULL DEFAULT 0,
    mqtt_invalid_json_dropped INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (modem_id) REFERENCES modems(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS band_condition_reference_stations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    band TEXT NOT NULL,
    callsign TEXT NOT NULL,
    ssid TEXT NOT NULL DEFAULT '',
    station_type TEXT NOT NULL CHECK (station_type IN ('home', 'digi', 'igate', 'wx-fixed', 'fixed')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    weight REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (band, callsign, ssid)
);

CREATE TABLE IF NOT EXISTS band_condition_audibility_buckets (
    bucket_start_utc TEXT NOT NULL,
    band TEXT NOT NULL,
    station_key TEXT NOT NULL,
    heard_flag INTEGER NOT NULL DEFAULT 0 CHECK (heard_flag IN (0, 1)),
    frame_count INTEGER NOT NULL DEFAULT 0,
    baseline_processed_at TEXT,
    PRIMARY KEY (bucket_start_utc, band, station_key)
);

CREATE TABLE IF NOT EXISTS band_condition_activity_station_buckets (
    bucket_start_utc TEXT NOT NULL,
    band TEXT NOT NULL,
    station_key TEXT NOT NULL,
    is_mobile INTEGER NOT NULL DEFAULT 0 CHECK (is_mobile IN (0, 1)),
    is_fixed INTEGER NOT NULL DEFAULT 0 CHECK (is_fixed IN (0, 1)),
    PRIMARY KEY (bucket_start_utc, band, station_key)
);

CREATE TABLE IF NOT EXISTS band_condition_activity_buckets (
    bucket_start_utc TEXT NOT NULL,
    band TEXT NOT NULL,
    total_frames INTEGER NOT NULL DEFAULT 0,
    total_unique_stations INTEGER NOT NULL DEFAULT 0,
    mobile_frames INTEGER NOT NULL DEFAULT 0,
    mobile_unique_stations INTEGER NOT NULL DEFAULT 0,
    fixed_frames INTEGER NOT NULL DEFAULT 0,
    fixed_unique_stations INTEGER NOT NULL DEFAULT 0,
    baseline_processed_at TEXT,
    PRIMARY KEY (bucket_start_utc, band)
);

CREATE TABLE IF NOT EXISTS band_condition_audibility_baseline (
    band TEXT NOT NULL,
    station_key TEXT NOT NULL,
    hour_of_day INTEGER NOT NULL CHECK (hour_of_day BETWEEN 0 AND 23),
    sample_count INTEGER NOT NULL DEFAULT 0,
    heard_sum REAL NOT NULL DEFAULT 0,
    heard_ratio REAL NOT NULL DEFAULT 0,
    ema_heard_ratio REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (band, station_key, hour_of_day)
);

CREATE TABLE IF NOT EXISTS band_condition_activity_baseline (
    band TEXT NOT NULL,
    hour_of_day INTEGER NOT NULL CHECK (hour_of_day BETWEEN 0 AND 23),
    sample_count INTEGER NOT NULL DEFAULT 0,
    avg_mobile_frames REAL NOT NULL DEFAULT 0,
    avg_total_frames REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (band, hour_of_day)
);

CREATE TABLE IF NOT EXISTS band_condition_fixed_station_baseline (
    band TEXT NOT NULL,
    station_key TEXT NOT NULL,
    hour_of_day INTEGER NOT NULL CHECK (hour_of_day BETWEEN 0 AND 23),
    heard_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (band, station_key, hour_of_day)
);

CREATE TABLE IF NOT EXISTS radio_activity_5m (
    bucket_start_utc TEXT NOT NULL,
    bucket_end_utc TEXT NOT NULL,
    interface_id INTEGER,
    source_name TEXT NOT NULL,
    rx_total INTEGER NOT NULL DEFAULT 0,
    tx_total INTEGER NOT NULL DEFAULT 0,
    digipeated_total INTEGER NOT NULL DEFAULT 0,
    own_frames_total INTEGER NOT NULL DEFAULT 0,
    messages_total INTEGER NOT NULL DEFAULT 0,
    queries_total INTEGER NOT NULL DEFAULT 0,
    objects_total INTEGER NOT NULL DEFAULT 0,
    wx_total INTEGER NOT NULL DEFAULT 0,
    position_total INTEGER NOT NULL DEFAULT 0,
    mobile_total INTEGER NOT NULL DEFAULT 0,
    fixed_total INTEGER NOT NULL DEFAULT 0,
    unique_stations_total INTEGER NOT NULL DEFAULT 0,
    direct_heard_total INTEGER NOT NULL DEFAULT 0,
    indirect_heard_total INTEGER NOT NULL DEFAULT 0,
    rfonly_total INTEGER NOT NULL DEFAULT 0,
    nogate_total INTEGER NOT NULL DEFAULT 0,
    invalid_total INTEGER NOT NULL DEFAULT 0,
    parse_error_total INTEGER NOT NULL DEFAULT 0,
    duplicate_total INTEGER NOT NULL DEFAULT 0,
    type_position_total INTEGER NOT NULL DEFAULT 0,
    type_weather_total INTEGER NOT NULL DEFAULT 0,
    type_message_total INTEGER NOT NULL DEFAULT 0,
    type_object_item_total INTEGER NOT NULL DEFAULT 0,
    type_status_total INTEGER NOT NULL DEFAULT 0,
    type_telemetry_total INTEGER NOT NULL DEFAULT 0,
    type_query_total INTEGER NOT NULL DEFAULT 0,
    type_user_defined_total INTEGER NOT NULL DEFAULT 0,
    type_third_party_total INTEGER NOT NULL DEFAULT 0,
    type_other_unknown_total INTEGER NOT NULL DEFAULT 0,
    max_hops_seen INTEGER,
    avg_hops REAL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS radio_activity_aggregator_state (
    key TEXT PRIMARY KEY,
    last_processed_bucket_start_utc TEXT,
    last_run_utc TEXT,
    last_error TEXT,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_event_logs_created_at ON event_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_traffic_frames_created_at ON traffic_frames(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_traffic_frames_format_created_at ON traffic_frames(format, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_traffic_device_station_device_hourly_bucket
    ON traffic_device_station_device_hourly(bucket_start_utc, station_key);
CREATE INDEX IF NOT EXISTS idx_traffic_runtime_interfaces_status_updated_at ON traffic_runtime_interfaces(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_digi_flow_event_log_flow_created_at ON digi_flow_event_log(flow_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_map_sources_enabled_sort ON map_sources(enabled DESC, sort_order ASC, id ASC);
CREATE INDEX IF NOT EXISTS idx_digi_flow_event_log_frame_uid ON digi_flow_event_log(frame_uid);
CREATE INDEX IF NOT EXISTS idx_digi_flows_route_pair ON digi_flows(source_kind, source_ref, target_kind, target_ref);
CREATE INDEX IF NOT EXISTS idx_outbound_jobs_status_scheduled_at ON outbound_jobs(status, scheduled_at, id);
CREATE INDEX IF NOT EXISTS idx_system_jobs_created_at ON system_jobs(created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_aprs_message_conversations_remote ON aprs_message_conversations(remote_callsign, remote_ssid);
CREATE INDEX IF NOT EXISTS idx_aprs_messages_conversation_created ON aprs_messages(conversation_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_aprs_messages_tx_lookup ON aprs_messages(direction, sender, addressee, message_number, status, id);
CREATE INDEX IF NOT EXISTS idx_wx_sources_type_enabled ON wx_sources(source_type, enabled, name);
CREATE INDEX IF NOT EXISTS idx_wx_mappings_source_enabled ON wx_mappings(source_id, enabled, parameter_name);
CREATE INDEX IF NOT EXISTS idx_wx_runtime_cache_status_updated ON wx_runtime_cache(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_band_condition_refs_band_enabled
    ON band_condition_reference_stations(band, enabled);
CREATE INDEX IF NOT EXISTS idx_band_condition_audibility_processed
    ON band_condition_audibility_buckets(baseline_processed_at, bucket_start_utc);
CREATE INDEX IF NOT EXISTS idx_band_condition_activity_processed
    ON band_condition_activity_buckets(baseline_processed_at, bucket_start_utc);
CREATE INDEX IF NOT EXISTS idx_band_condition_fixed_station_baseline_band_hour
    ON band_condition_fixed_station_baseline(band, hour_of_day);
CREATE INDEX IF NOT EXISTS idx_radio_activity_5m_bucket_start
    ON radio_activity_5m(bucket_start_utc);
CREATE INDEX IF NOT EXISTS idx_radio_activity_5m_bucket_interface
    ON radio_activity_5m(bucket_start_utc, interface_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_radio_activity_5m_bucket_source
    ON radio_activity_5m(bucket_start_utc, source_name);
"""


def init_db() -> None:
    global _event_log_min_level_cache, _event_log_debug_enabled_cache
    _event_log_min_level_cache = None
    _event_log_debug_enabled_cache = None
    with get_connection() as connection:
        connection.executescript(SCHEMA)
        _migrate_system_jobs_table(connection)
        _migrate_entity_interval_constraints(connection)
        _migrate_aprs_messages_table(connection)
        _migrate_bulletin_table(connection)
        _migrate_digi_flows_table(connection)
        _migrate_digi_flow_steps_table(connection)
        _migrate_digi_flow_event_log_table(connection)
        _cleanup_legacy_digi_flow_tables(connection)
        station_columns = {row["name"] for row in connection.execute("PRAGMA table_info(station_settings)").fetchall()}
        user_columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()}
        modem_columns = {row["name"] for row in connection.execute("PRAGMA table_info(modems)").fetchall()}
        map_columns = {row["name"] for row in connection.execute("PRAGMA table_info(map_sources)").fetchall()}
        wx_columns = {row["name"] for row in connection.execute("PRAGMA table_info(wx_config)").fetchall()}
        object_columns = {row["name"] for row in connection.execute("PRAGMA table_info(aprs_objects)").fetchall()}
        item_columns = {row["name"] for row in connection.execute("PRAGMA table_info(aprs_items)").fetchall()}
        bulletin_columns = {row["name"] for row in connection.execute("PRAGMA table_info(bulletins)").fetchall()}
        outbound_columns = {row["name"] for row in connection.execute("PRAGMA table_info(outbound_jobs)").fetchall()}
        traffic_frame_columns = {row["name"] for row in connection.execute("PRAGMA table_info(traffic_frames)").fetchall()}
        traffic_runtime_columns = {row["name"] for row in connection.execute("PRAGMA table_info(traffic_runtime_state)").fetchall()}
        traffic_runtime_interface_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(traffic_runtime_interfaces)").fetchall()
        }
        digi_flow_columns = {row["name"] for row in connection.execute("PRAGMA table_info(digi_flows)").fetchall()}
        radio_activity_columns = {row["name"] for row in connection.execute("PRAGMA table_info(radio_activity_5m)").fetchall()}
        if "last_login_at" not in user_columns:
            connection.execute(
                """
                ALTER TABLE users
                ADD COLUMN last_login_at TEXT
                """
            )
        if "default_units" not in station_columns:
            connection.execute(
                """
                ALTER TABLE station_settings
                ADD COLUMN default_units TEXT NOT NULL DEFAULT 'metric'
                CHECK (default_units IN ('metric', 'imperial'))
                """
            )
        if "beacon_interval_minutes" not in station_columns:
            connection.execute(
                """
                ALTER TABLE station_settings
                ADD COLUMN beacon_interval_minutes INTEGER NOT NULL DEFAULT 30
                CHECK (beacon_interval_minutes IN (15, 30, 45, 60))
                """
            )
        if "beacon_interval_mode" not in station_columns:
            connection.execute(
                """
                ALTER TABLE station_settings
                ADD COLUMN beacon_interval_mode TEXT NOT NULL DEFAULT 'fixed'
                CHECK (beacon_interval_mode IN ('fixed', 'proportional'))
                """
            )
        if "beacon_path" not in station_columns:
            connection.execute(
                """
                ALTER TABLE station_settings
                ADD COLUMN beacon_path TEXT
                """
            )
        if "status_enabled" not in station_columns:
            connection.execute(
                """
                ALTER TABLE station_settings
                ADD COLUMN status_enabled INTEGER NOT NULL DEFAULT 0
                CHECK (status_enabled IN (0, 1))
                """
            )
        if "status_text" not in station_columns:
            connection.execute(
                """
                ALTER TABLE station_settings
                ADD COLUMN status_text TEXT
                """
            )
        if "status_interval_minutes" not in station_columns:
            connection.execute(
                """
                ALTER TABLE station_settings
                ADD COLUMN status_interval_minutes INTEGER NOT NULL DEFAULT 30
                CHECK (status_interval_minutes IN (15, 30, 45, 60))
                """
            )
        if "beacon_interface_id" not in station_columns:
            connection.execute(
                """
                ALTER TABLE station_settings
                ADD COLUMN beacon_interface_id INTEGER
                """
            )
        if "beacon_tx_scope" not in station_columns:
            connection.execute(
                """
                ALTER TABLE station_settings
                ADD COLUMN beacon_tx_scope TEXT NOT NULL DEFAULT 'single'
                CHECK (beacon_tx_scope IN ('single', 'all_active'))
                """
            )
        if "symbol_overlay" not in station_columns:
            connection.execute(
                """
                ALTER TABLE station_settings
                ADD COLUMN symbol_overlay TEXT
                """
            )
        if "beacon_interface_id" not in wx_columns:
            connection.execute(
                """
                ALTER TABLE wx_config
                ADD COLUMN beacon_interface_id INTEGER
                """
            )
        if "beacon_tx_scope" not in wx_columns:
            connection.execute(
                """
                ALTER TABLE wx_config
                ADD COLUMN beacon_tx_scope TEXT NOT NULL DEFAULT 'single'
                CHECK (beacon_tx_scope IN ('single', 'all_active'))
                """
            )
        if "path" not in wx_columns:
            connection.execute(
                """
                ALTER TABLE wx_config
                ADD COLUMN path TEXT NOT NULL DEFAULT ''
                """
            )
        if "latitude" not in wx_columns:
            connection.execute(
                """
                ALTER TABLE wx_config
                ADD COLUMN latitude TEXT NOT NULL DEFAULT ''
                """
            )
        if "longitude" not in wx_columns:
            connection.execute(
                """
                ALTER TABLE wx_config
                ADD COLUMN longitude TEXT NOT NULL DEFAULT ''
                """
            )
        if "band" not in modem_columns:
            connection.execute(
                """
                ALTER TABLE modems
                ADD COLUMN band TEXT NOT NULL DEFAULT ''
                """
            )
        if "tx_blocked" not in modem_columns:
            connection.execute(
                """
                ALTER TABLE modems
                ADD COLUMN tx_blocked INTEGER NOT NULL DEFAULT 0
                CHECK (tx_blocked IN (0, 1))
                """
            )
        if "tx_min_gap_seconds" not in modem_columns:
            connection.execute(
                """
                ALTER TABLE modems
                ADD COLUMN tx_min_gap_seconds REAL NOT NULL DEFAULT 0.35
                CHECK (tx_min_gap_seconds >= 0.2 AND tx_min_gap_seconds <= 1.2)
                """
            )
        if "serial_rx_silence_reconnect_seconds" not in modem_columns:
            connection.execute(
                """
                ALTER TABLE modems
                ADD COLUMN serial_rx_silence_reconnect_seconds INTEGER NOT NULL DEFAULT 150
                CHECK (serial_rx_silence_reconnect_seconds IN (0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 360, 390, 420, 450, 480, 510, 540, 570, 600))
                """
            )
        if "expose_port_enabled" not in modem_columns:
            connection.execute(
                """
                ALTER TABLE modems
                ADD COLUMN expose_port_enabled INTEGER NOT NULL DEFAULT 0
                CHECK (expose_port_enabled IN (0, 1))
                """
            )
        if "expose_allow_tx" not in modem_columns:
            connection.execute(
                """
                ALTER TABLE modems
                ADD COLUMN expose_allow_tx INTEGER NOT NULL DEFAULT 1
                CHECK (expose_allow_tx IN (0, 1))
                """
            )
        if "expose_bind_address" not in modem_columns:
            connection.execute(
                """
                ALTER TABLE modems
                ADD COLUMN expose_bind_address TEXT NOT NULL DEFAULT '0.0.0.0'
                """
            )
        if "expose_port" not in modem_columns:
            connection.execute(
                """
                ALTER TABLE modems
                ADD COLUMN expose_port INTEGER NOT NULL DEFAULT 8002
                CHECK (expose_port BETWEEN 1 AND 65535)
                """
            )
        if "expose_whitelist" not in modem_columns:
            connection.execute(
                """
                ALTER TABLE modems
                ADD COLUMN expose_whitelist TEXT NOT NULL DEFAULT ''
                """
            )
        if "local_cache_enabled" not in map_columns:
            connection.execute(
                """
                ALTER TABLE map_sources
                ADD COLUMN local_cache_enabled INTEGER NOT NULL DEFAULT 0
                CHECK (local_cache_enabled IN (0, 1))
                """
            )
        if "cache_tile_count" not in map_columns:
            connection.execute(
                """
                ALTER TABLE map_sources
                ADD COLUMN cache_tile_count INTEGER NOT NULL DEFAULT 0
                CHECK (cache_tile_count >= 0)
                """
            )
        if "cache_size_bytes" not in map_columns:
            connection.execute(
                """
                ALTER TABLE map_sources
                ADD COLUMN cache_size_bytes INTEGER NOT NULL DEFAULT 0
                CHECK (cache_size_bytes >= 0)
                """
            )
        if "aprs_message_id" not in outbound_columns:
            connection.execute(
                """
                ALTER TABLE outbound_jobs
                ADD COLUMN aprs_message_id INTEGER
                """
            )
        if "sort_order" not in digi_flow_columns:
            connection.execute(
                """
                ALTER TABLE digi_flows
                ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0
                """
            )
        if "interface_id" not in traffic_frame_columns:
            connection.execute(
                """
                ALTER TABLE traffic_frames
                ADD COLUMN interface_id INTEGER
                """
            )
        if "direction" not in traffic_frame_columns:
            connection.execute(
                """
                ALTER TABLE traffic_frames
                ADD COLUMN direction TEXT
                """
            )
        if "band" not in traffic_frame_columns:
            connection.execute(
                """
                ALTER TABLE traffic_frames
                ADD COLUMN band TEXT
                """
            )
        if "type_position_total" not in radio_activity_columns:
            connection.execute(
                """
                ALTER TABLE radio_activity_5m
                ADD COLUMN type_position_total INTEGER NOT NULL DEFAULT 0
                """
            )
        if "type_weather_total" not in radio_activity_columns:
            connection.execute(
                """
                ALTER TABLE radio_activity_5m
                ADD COLUMN type_weather_total INTEGER NOT NULL DEFAULT 0
                """
            )
        if "type_message_total" not in radio_activity_columns:
            connection.execute(
                """
                ALTER TABLE radio_activity_5m
                ADD COLUMN type_message_total INTEGER NOT NULL DEFAULT 0
                """
            )
        if "type_object_item_total" not in radio_activity_columns:
            connection.execute(
                """
                ALTER TABLE radio_activity_5m
                ADD COLUMN type_object_item_total INTEGER NOT NULL DEFAULT 0
                """
            )
        if "type_status_total" not in radio_activity_columns:
            connection.execute(
                """
                ALTER TABLE radio_activity_5m
                ADD COLUMN type_status_total INTEGER NOT NULL DEFAULT 0
                """
            )
        if "type_telemetry_total" not in radio_activity_columns:
            connection.execute(
                """
                ALTER TABLE radio_activity_5m
                ADD COLUMN type_telemetry_total INTEGER NOT NULL DEFAULT 0
                """
            )
        if "type_query_total" not in radio_activity_columns:
            connection.execute(
                """
                ALTER TABLE radio_activity_5m
                ADD COLUMN type_query_total INTEGER NOT NULL DEFAULT 0
                """
            )
        if "type_user_defined_total" not in radio_activity_columns:
            connection.execute(
                """
                ALTER TABLE radio_activity_5m
                ADD COLUMN type_user_defined_total INTEGER NOT NULL DEFAULT 0
                """
            )
        if "type_third_party_total" not in radio_activity_columns:
            connection.execute(
                """
                ALTER TABLE radio_activity_5m
                ADD COLUMN type_third_party_total INTEGER NOT NULL DEFAULT 0
                """
            )
        if "type_other_unknown_total" not in radio_activity_columns:
            connection.execute(
                """
                ALTER TABLE radio_activity_5m
                ADD COLUMN type_other_unknown_total INTEGER NOT NULL DEFAULT 0
                """
            )
        connection.execute(
            """
CREATE INDEX IF NOT EXISTS idx_traffic_frames_interface_created_at
    ON traffic_frames(interface_id, created_at DESC, id DESC)
"""
        )
        connection.execute(
            """
CREATE INDEX IF NOT EXISTS idx_traffic_frames_format_created_at
    ON traffic_frames(format, created_at DESC, id DESC)
"""
        )
        if "expose_port_enabled" not in traffic_runtime_columns:
            connection.execute(
                """
                ALTER TABLE traffic_runtime_state
                ADD COLUMN expose_port_enabled INTEGER NOT NULL DEFAULT 0
                CHECK (expose_port_enabled IN (0, 1))
                """
            )
        if "expose_bind_address" not in traffic_runtime_columns:
            connection.execute(
                """
                ALTER TABLE traffic_runtime_state
                ADD COLUMN expose_bind_address TEXT
                """
            )
        if "expose_port" not in traffic_runtime_columns:
            connection.execute(
                """
                ALTER TABLE traffic_runtime_state
                ADD COLUMN expose_port INTEGER
                """
            )
        if "expose_active_clients" not in traffic_runtime_columns:
            connection.execute(
                """
                ALTER TABLE traffic_runtime_state
                ADD COLUMN expose_active_clients INTEGER NOT NULL DEFAULT 0
                """
            )
        if "mqtt_connected" not in traffic_runtime_interface_columns:
            connection.execute(
                """
                ALTER TABLE traffic_runtime_interfaces
                ADD COLUMN mqtt_connected INTEGER NOT NULL DEFAULT 0
                CHECK (mqtt_connected IN (0, 1))
                """
            )
        if "mqtt_subscribed_topic" not in traffic_runtime_interface_columns:
            connection.execute(
                """
                ALTER TABLE traffic_runtime_interfaces
                ADD COLUMN mqtt_subscribed_topic TEXT
                """
            )
        if "mqtt_broker_host" not in traffic_runtime_interface_columns:
            connection.execute(
                """
                ALTER TABLE traffic_runtime_interfaces
                ADD COLUMN mqtt_broker_host TEXT
                """
            )
        if "mqtt_broker_port" not in traffic_runtime_interface_columns:
            connection.execute(
                """
                ALTER TABLE traffic_runtime_interfaces
                ADD COLUMN mqtt_broker_port INTEGER
                """
            )
        if "mqtt_last_frame_at" not in traffic_runtime_interface_columns:
            connection.execute(
                """
                ALTER TABLE traffic_runtime_interfaces
                ADD COLUMN mqtt_last_frame_at TEXT
                """
            )
        if "mqtt_frames_received" not in traffic_runtime_interface_columns:
            connection.execute(
                """
                ALTER TABLE traffic_runtime_interfaces
                ADD COLUMN mqtt_frames_received INTEGER NOT NULL DEFAULT 0
                """
            )
        if "mqtt_duplicates_dropped" not in traffic_runtime_interface_columns:
            connection.execute(
                """
                ALTER TABLE traffic_runtime_interfaces
                ADD COLUMN mqtt_duplicates_dropped INTEGER NOT NULL DEFAULT 0
                """
            )
        if "mqtt_invalid_json_dropped" not in traffic_runtime_interface_columns:
            connection.execute(
                """
                ALTER TABLE traffic_runtime_interfaces
                ADD COLUMN mqtt_invalid_json_dropped INTEGER NOT NULL DEFAULT 0
                """
            )
        connection.execute(
            """
CREATE INDEX IF NOT EXISTS idx_outbound_jobs_aprs_message_id
    ON outbound_jobs(aprs_message_id, status, scheduled_at, id)
"""
        )
        connection.execute(
            """
            INSERT INTO aprsis_runtime_state (
                id, status, status_detail, server, port, login, connected_at, last_error, updated_at
            )
            VALUES (1, 'inactive', 'APRS-IS uplink is inactive.', NULL, NULL, NULL, NULL, NULL, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (utc_now(),),
        )
        connection.execute(
            """
            INSERT INTO aprsis_uplink_stats (
                id, tx_total, drop_total, strict_total,
                strict_blocked_tcpip_tcpxx_total, strict_blocked_nogate_rfonly_total,
                strict_malformed_third_party_total, strict_other_total,
                last_sent_at, last_sent_line, last_drop_at, last_drop_line,
                last_strict_reject_at, last_strict_reject_line, last_strict_reject_reason, updated_at
            )
            VALUES (1, 0, 0, 0, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (utc_now(),),
        )
        if "state" not in object_columns:
            connection.execute(
                """
                ALTER TABLE aprs_objects
                ADD COLUMN state TEXT NOT NULL DEFAULT 'live'
                CHECK (state IN ('live', 'killed'))
                """
            )
        if "lifetime" not in object_columns:
            connection.execute(
                """
                ALTER TABLE aprs_objects
                ADD COLUMN lifetime TEXT NOT NULL DEFAULT 'temporary'
                CHECK (lifetime IN ('temporary', 'permanent'))
                """
            )
        if "path" not in object_columns:
            connection.execute(
                """
                ALTER TABLE aprs_objects
                ADD COLUMN path TEXT
                """
            )
        if "interval_minutes" not in object_columns:
            connection.execute(
                """
                ALTER TABLE aprs_objects
                ADD COLUMN interval_minutes INTEGER NOT NULL DEFAULT 30
                CHECK (interval_minutes IN (5, 10, 15, 30, 45, 60))
                """
            )
        if "valid_until_utc" not in object_columns:
            connection.execute(
                """
                ALTER TABLE aprs_objects
                ADD COLUMN valid_until_utc TEXT
                """
            )
        if "symbol_overlay" not in object_columns:
            connection.execute(
                """
                ALTER TABLE aprs_objects
                ADD COLUMN symbol_overlay TEXT
                """
            )
        if "state" not in item_columns:
            connection.execute(
                """
                ALTER TABLE aprs_items
                ADD COLUMN state TEXT NOT NULL DEFAULT 'live'
                CHECK (state IN ('live', 'killed'))
                """
            )
        if "path" not in item_columns:
            connection.execute(
                """
                ALTER TABLE aprs_items
                ADD COLUMN path TEXT
                """
            )
        if "interval_minutes" not in item_columns:
            connection.execute(
                """
                ALTER TABLE aprs_items
                ADD COLUMN interval_minutes INTEGER NOT NULL DEFAULT 30
                CHECK (interval_minutes IN (5, 10, 15, 30, 45, 60))
                """
            )
        if "symbol_overlay" not in item_columns:
            connection.execute(
                """
                ALTER TABLE aprs_items
                ADD COLUMN symbol_overlay TEXT
                """
            )
        if "valid_until_utc" not in bulletin_columns:
            connection.execute(
                """
                ALTER TABLE bulletins
                ADD COLUMN valid_until_utc TEXT
                """
            )
        connection.execute(
            """
            UPDATE modems
            SET modem_type = 'SERIALL',
                updated_at = ?
            WHERE UPPER(TRIM(COALESCE(modem_type, ''))) = 'SERIAL'
            """,
            (utc_now(),),
        )
        connection.execute(
            """
            INSERT INTO station_settings (
                id, callsign, ssid, beacon_interface_id, beacon_tx_scope, beacon_comment, beacon_interval_mode, beacon_interval_minutes, beacon_path,
                status_enabled, status_text, status_interval_minutes, latitude, longitude,
                symbol_table, symbol_code, symbol_overlay, default_units, tx_enabled, updated_at
            )
            VALUES (1, '', '', NULL, 'single', '', 'fixed', 30, '', 0, '', 30, '', '', '/', '>', NULL, 'metric', 0, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (utc_now(),),
        )
        connection.execute(
            """
            INSERT INTO traffic_runtime_state (
                id, status, status_detail, active_modem_name, active_modem_endpoint,
                expose_port_enabled, expose_bind_address, expose_port, expose_active_clients,
                last_error, updated_at
            )
            VALUES (1, 'idle', 'Traffic monitor is starting.', NULL, NULL, 0, NULL, NULL, 0, NULL, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (utc_now(),),
        )
        connection.execute(
            """
            INSERT INTO wx_config (
                id, enabled, callsign, ssid, beacon_interface_id, beacon_tx_scope, path, latitude, longitude, refresh_interval_s,
                allow_cache_fallback, default_cache_max_age_s, created_at, updated_at
            )
            VALUES (1, 0, '', '', NULL, 'single', '', '', '', 300, 1, 900, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (utc_now(), utc_now()),
        )
        connection.execute(
            """
            INSERT INTO map_sources (
                name, url_template, attribution, min_zoom, max_zoom,
                subdomains, api_key, local_cache_enabled, cache_tile_count, cache_size_bytes,
                enabled, is_default, sort_order, notes, created_at, updated_at
            )
            SELECT ?, ?, ?, 0, 19, '', '', 0, 0, 0, 1, 1, 0, '', ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM map_sources)
            """,
            (
                settings.map_tile_source_name,
                settings.map_tile_url,
                settings.map_tile_attribution,
                utc_now(),
                utc_now(),
            ),
        )
        _normalize_map_sources_table(connection)


def _normalize_map_sources_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        UPDATE map_sources
        SET local_cache_enabled = CASE WHEN local_cache_enabled IN (0, 1) THEN local_cache_enabled ELSE 0 END,
            cache_tile_count = CASE WHEN cache_tile_count >= 0 THEN cache_tile_count ELSE 0 END,
            cache_size_bytes = CASE WHEN cache_size_bytes >= 0 THEN cache_size_bytes ELSE 0 END
        """
    )
    rows = list(
        connection.execute(
            """
            SELECT id, enabled, is_default
            FROM map_sources
            ORDER BY sort_order ASC, id ASC
            """
        ).fetchall()
    )
    if not rows:
        return

    now = utc_now()
    default_rows = [row for row in rows if int(row["is_default"] or 0) == 1]
    if len(default_rows) > 1:
        keep_id = int(default_rows[0]["id"])
        connection.execute(
            """
            UPDATE map_sources
            SET is_default = CASE WHEN id = ? THEN 1 ELSE 0 END,
                updated_at = ?
            WHERE is_default = 1
            """,
            (keep_id, now),
        )
    elif len(default_rows) == 0:
        first_enabled = next((row for row in rows if int(row["enabled"] or 0) == 1), rows[0])
        keep_id = int(first_enabled["id"])
        connection.execute(
            """
            UPDATE map_sources
            SET is_default = CASE WHEN id = ? THEN 1 ELSE 0 END,
                enabled = CASE WHEN id = ? THEN 1 ELSE enabled END,
                updated_at = ?
            """,
            (keep_id, keep_id, now),
        )
    else:
        default_id = int(default_rows[0]["id"])
        if int(default_rows[0]["enabled"] or 0) != 1:
            connection.execute(
                """
                UPDATE map_sources
                SET enabled = 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, default_id),
            )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_map_sources_single_default
            ON map_sources(is_default)
            WHERE is_default = 1
        """
    )


def _migrate_system_jobs_table(connection: sqlite3.Connection) -> None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'system_jobs' LIMIT 1"
    ).fetchone()
    if exists is not None:
        return
    connection.execute(
        """
        CREATE TABLE system_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'success', 'error')),
            message TEXT NOT NULL DEFAULT '',
            log_file TEXT,
            pid INTEGER,
            exit_code INTEGER,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_system_jobs_created_at ON system_jobs(created_at DESC, id DESC)")


def _migrate_entity_interval_constraints(connection: sqlite3.Connection) -> None:
    objects_sql = _table_sql(connection, "aprs_objects")
    if objects_sql and "interval_minutes IN (5, 10, 15, 30, 45, 60)" not in objects_sql:
        object_columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(aprs_objects)").fetchall()}
        object_overlay_select = "symbol_overlay" if "symbol_overlay" in object_columns else "NULL"
        connection.executescript(
            f"""
            ALTER TABLE aprs_objects RENAME TO aprs_objects_old;
            CREATE TABLE aprs_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                lifetime TEXT NOT NULL DEFAULT 'temporary' CHECK (lifetime IN ('temporary', 'permanent')),
                state TEXT NOT NULL DEFAULT 'live' CHECK (state IN ('live', 'killed')),
                is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0, 1)),
                interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (interval_minutes IN (5, 10, 15, 30, 45, 60)),
                latitude TEXT,
                longitude TEXT,
                symbol_table TEXT,
                symbol_code TEXT,
                symbol_overlay TEXT,
                path TEXT,
                comment TEXT,
                updated_at TEXT NOT NULL
            );
            INSERT INTO aprs_objects (
                id, name, lifetime, state, is_enabled, interval_minutes, latitude, longitude, symbol_table, symbol_code, symbol_overlay, path, comment, updated_at
            )
            SELECT
                id,
                name,
                COALESCE(lifetime, 'temporary'),
                COALESCE(state, 'live'),
                COALESCE(is_enabled, 0),
                CASE
                    WHEN interval_minutes IN (5, 10, 15, 30, 45, 60) THEN interval_minutes
                    ELSE 30
                END,
                latitude,
                longitude,
                symbol_table,
                symbol_code,
                {object_overlay_select},
                path,
                comment,
                updated_at
            FROM aprs_objects_old;
            DROP TABLE aprs_objects_old;
            """
        )
    items_sql = _table_sql(connection, "aprs_items")
    if items_sql and "interval_minutes IN (5, 10, 15, 30, 45, 60)" not in items_sql:
        item_columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(aprs_items)").fetchall()}
        item_overlay_select = "symbol_overlay" if "symbol_overlay" in item_columns else "NULL"
        connection.executescript(
            f"""
            ALTER TABLE aprs_items RENAME TO aprs_items_old;
            CREATE TABLE aprs_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL DEFAULT 'live' CHECK (state IN ('live', 'killed')),
                is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0, 1)),
                interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (interval_minutes IN (5, 10, 15, 30, 45, 60)),
                latitude TEXT,
                longitude TEXT,
                symbol_table TEXT,
                symbol_code TEXT,
                symbol_overlay TEXT,
                path TEXT,
                comment TEXT,
                updated_at TEXT NOT NULL
            );
            INSERT INTO aprs_items (
                id, name, state, is_enabled, interval_minutes, latitude, longitude, symbol_table, symbol_code, symbol_overlay, path, comment, updated_at
            )
            SELECT
                id,
                name,
                COALESCE(state, 'live'),
                COALESCE(is_enabled, 0),
                CASE
                    WHEN interval_minutes IN (5, 10, 15, 30, 45, 60) THEN interval_minutes
                    ELSE 30
                END,
                latitude,
                longitude,
                symbol_table,
                symbol_code,
                {item_overlay_select},
                path,
                comment,
                updated_at
            FROM aprs_items_old;
            DROP TABLE aprs_items_old;
            """
        )


def _migrate_aprs_messages_table(connection: sqlite3.Connection) -> None:
    messages_sql = _table_sql(connection, "aprs_messages")
    if not messages_sql:
        return
    if "status IN ('queued', 'sent', 'acked', 'rejected', 'failed', 'received')" in messages_sql:
        return
    old_columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(aprs_messages)").fetchall()}
    connection.executescript(
        """
        ALTER TABLE aprs_messages RENAME TO aprs_messages_old;
        CREATE TABLE aprs_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('rx', 'tx')),
            sender TEXT NOT NULL,
            addressee TEXT NOT NULL,
            message_text TEXT NOT NULL,
            path TEXT NOT NULL DEFAULT '',
            message_number TEXT,
            status TEXT NOT NULL CHECK (status IN ('queued', 'sent', 'acked', 'rejected', 'failed', 'received')),
            tx_attempt_count INTEGER NOT NULL DEFAULT 0,
            is_unread INTEGER NOT NULL DEFAULT 0 CHECK (is_unread IN (0, 1)),
            outbound_job_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            sent_at TEXT,
            acked_at TEXT,
            last_attempt_at TEXT,
            failed_at TEXT,
            failure_reason TEXT,
            FOREIGN KEY (conversation_id) REFERENCES aprs_message_conversations(id) ON DELETE CASCADE,
            FOREIGN KEY (outbound_job_id) REFERENCES outbound_jobs(id) ON DELETE SET NULL
        );
        """
    )
    if "created_at" in old_columns and "updated_at" in old_columns:
        created_at_expr = "COALESCE(created_at, updated_at, '1970-01-01T00:00:00+00:00')"
        updated_at_expr = "COALESCE(updated_at, created_at, '1970-01-01T00:00:00+00:00')"
    elif "created_at" in old_columns:
        created_at_expr = "COALESCE(created_at, '1970-01-01T00:00:00+00:00')"
        updated_at_expr = "COALESCE(created_at, '1970-01-01T00:00:00+00:00')"
    elif "updated_at" in old_columns:
        created_at_expr = "COALESCE(updated_at, '1970-01-01T00:00:00+00:00')"
        updated_at_expr = "COALESCE(updated_at, '1970-01-01T00:00:00+00:00')"
    else:
        created_at_expr = "'1970-01-01T00:00:00+00:00'"
        updated_at_expr = "'1970-01-01T00:00:00+00:00'"

    direction_expr = "CASE WHEN direction IN ('rx', 'tx') THEN direction ELSE 'rx' END" if "direction" in old_columns else "'rx'"
    status_expr = (
        "CASE WHEN status IN ('queued', 'sent', 'acked', 'rejected', 'failed', 'received') THEN status ELSE 'failed' END"
        if "status" in old_columns
        else "'failed'"
    )
    is_unread_expr = "CASE WHEN is_unread IN (0, 1) THEN is_unread ELSE 0 END" if "is_unread" in old_columns else "0"

    connection.execute(
        f"""
        INSERT INTO aprs_messages(
            id, conversation_id, direction, sender, addressee, message_text, path, message_number,
            status, tx_attempt_count, is_unread, outbound_job_id, created_at, updated_at,
            sent_at, acked_at, last_attempt_at, failed_at, failure_reason
        )
        SELECT
            {'id' if 'id' in old_columns else 'NULL'},
            {'conversation_id' if 'conversation_id' in old_columns else '0'},
            {direction_expr},
            {'sender' if 'sender' in old_columns else "''"},
            {'addressee' if 'addressee' in old_columns else "''"},
            {'message_text' if 'message_text' in old_columns else "''"},
            {"COALESCE(path, '')" if 'path' in old_columns else "''"},
            {'message_number' if 'message_number' in old_columns else 'NULL'},
            {status_expr},
            {'COALESCE(tx_attempt_count, 0)' if 'tx_attempt_count' in old_columns else '0'},
            {is_unread_expr},
            {'outbound_job_id' if 'outbound_job_id' in old_columns else 'NULL'},
            {created_at_expr},
            {updated_at_expr},
            {'sent_at' if 'sent_at' in old_columns else 'NULL'},
            {'acked_at' if 'acked_at' in old_columns else 'NULL'},
            {'last_attempt_at' if 'last_attempt_at' in old_columns else 'NULL'},
            {'failed_at' if 'failed_at' in old_columns else 'NULL'},
            {'failure_reason' if 'failure_reason' in old_columns else 'NULL'}
        FROM aprs_messages_old
        """
    )
    connection.executescript(
        """
        DROP TABLE aprs_messages_old;
        CREATE INDEX IF NOT EXISTS idx_aprs_messages_conversation_created ON aprs_messages(conversation_id, created_at, id);
        CREATE INDEX IF NOT EXISTS idx_aprs_messages_tx_lookup ON aprs_messages(direction, sender, addressee, message_number, status, id);
        """
    )


def _migrate_bulletin_table(connection: sqlite3.Connection) -> None:
    bulletins_sql = _table_sql(connection, "bulletins")
    bulletin_columns = {row["name"] for row in connection.execute("PRAGMA table_info(bulletins)").fetchall()}
    if bulletins_sql and "message_kind" not in bulletins_sql:
        connection.executescript(
            """
            ALTER TABLE bulletins RENAME TO bulletins_old;
            CREATE TABLE bulletins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_kind TEXT NOT NULL DEFAULT 'bulletin' CHECK (message_kind IN ('bulletin', 'announcement', 'group_bulletin')),
                addressee TEXT,
                bulletin_code TEXT,
                group_name TEXT,
                is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0, 1)),
                interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (interval_minutes IN (5, 10, 15, 30, 45, 60)),
                path TEXT,
                message_text TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO bulletins (
                id, message_kind, addressee, bulletin_code, group_name, is_enabled, interval_minutes, path, message_text, updated_at
            )
            SELECT
                id,
                'bulletin',
                NULL,
                '0',
                '',
                COALESCE(is_enabled, 0),
                CASE
                    WHEN cadence_minutes IN (5, 10, 15, 30, 45, 60) THEN cadence_minutes
                    ELSE 30
                END,
                NULL,
                SUBSTR(COALESCE(body, ''), 1, 67),
                updated_at
            FROM bulletins_old;
            DROP TABLE bulletins_old;
            """
        )
    elif bulletins_sql and "path" not in bulletin_columns:
        connection.executescript(
            """
            ALTER TABLE bulletins RENAME TO bulletins_old;
            CREATE TABLE bulletins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_kind TEXT NOT NULL DEFAULT 'bulletin' CHECK (message_kind IN ('bulletin', 'announcement', 'group_bulletin')),
                addressee TEXT,
                bulletin_code TEXT,
                group_name TEXT,
                is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0, 1)),
                interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (interval_minutes IN (5, 10, 15, 30, 45, 60)),
                path TEXT,
                message_text TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO bulletins (
                id, message_kind, addressee, bulletin_code, group_name, is_enabled, interval_minutes, path, message_text, updated_at
            )
            SELECT
                id,
                CASE
                    WHEN message_kind IN ('bulletin', 'announcement', 'group_bulletin') THEN message_kind
                    ELSE 'bulletin'
                END,
                NULL,
                COALESCE(bulletin_code, '0'),
                COALESCE(group_name, ''),
                COALESCE(is_enabled, 0),
                CASE
                    WHEN interval_minutes IN (5, 10, 15, 30, 45, 60) THEN interval_minutes
                    ELSE 30
                END,
                NULL,
                SUBSTR(COALESCE(message_text, ''), 1, 67),
                updated_at
            FROM bulletins_old;
            DROP TABLE bulletins_old;
            """
        )
    elif bulletins_sql and "message_kind IN ('bulletin', 'announcement', 'group_bulletin')" not in bulletins_sql:
        connection.executescript(
            """
            ALTER TABLE bulletins RENAME TO bulletins_old;
            CREATE TABLE bulletins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_kind TEXT NOT NULL DEFAULT 'bulletin' CHECK (message_kind IN ('bulletin', 'announcement', 'group_bulletin')),
                addressee TEXT,
                bulletin_code TEXT,
                group_name TEXT,
                is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0, 1)),
                interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (interval_minutes IN (5, 10, 15, 30, 45, 60)),
                path TEXT,
                message_text TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO bulletins (
                id, message_kind, addressee, bulletin_code, group_name, is_enabled, interval_minutes, path, message_text, updated_at
            )
            SELECT
                id,
                CASE
                    WHEN message_kind IN ('bulletin', 'announcement', 'group_bulletin') THEN message_kind
                    ELSE 'bulletin'
                END,
                NULL,
                COALESCE(bulletin_code, '0'),
                COALESCE(group_name, ''),
                COALESCE(is_enabled, 0),
                CASE
                    WHEN interval_minutes IN (5, 10, 15, 30, 45, 60) THEN interval_minutes
                    ELSE 30
                END,
                COALESCE(path, NULL),
                SUBSTR(COALESCE(message_text, ''), 1, 67),
                updated_at
            FROM bulletins_old;
            DROP TABLE bulletins_old;
            """
        )


def _migrate_digi_flows_table(connection: sqlite3.Connection) -> None:
    flows_sql = _table_sql(connection, "digi_flows")
    if not flows_sql:
        return
    has_legacy_unique = "UNIQUE (source_kind, source_ref, target_kind, target_ref)" in flows_sql
    has_local_tx_source = "'receiver_local_tx'" in flows_sql
    if not has_legacy_unique and has_local_tx_source:
        return
    connection.executescript(
        """
        ALTER TABLE digi_flows RENAME TO digi_flows_old;
        CREATE TABLE digi_flows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            source_kind TEXT NOT NULL CHECK (source_kind IN ('receiver_rf', 'receiver_aprsis', 'receiver_local_tx')),
            source_ref TEXT NOT NULL,
            target_kind TEXT NOT NULL CHECK (target_kind IN ('tx_rf', 'tx_aprsis', 'action_drop', 'action_log')),
            target_ref TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO digi_flows (
            id, name, description, source_kind, source_ref, target_kind, target_ref, enabled, sort_order, created_at, updated_at
        )
        SELECT
            id,
            name,
            description,
            CASE
                WHEN source_kind IN ('receiver_rf', 'receiver_aprsis', 'receiver_local_tx') THEN source_kind
                ELSE 'receiver_rf'
            END,
            COALESCE(source_ref, ''),
            CASE
                WHEN target_kind IN ('tx_rf', 'tx_aprsis', 'action_drop', 'action_log') THEN target_kind
                ELSE 'action_log'
            END,
            COALESCE(target_ref, ''),
            CASE
                WHEN enabled IN (0, 1) THEN enabled
                ELSE 0
            END,
            0,
            COALESCE(created_at, updated_at, '1970-01-01T00:00:00+00:00'),
            COALESCE(updated_at, created_at, '1970-01-01T00:00:00+00:00')
        FROM digi_flows_old;
        CREATE INDEX IF NOT EXISTS idx_digi_flows_route_pair ON digi_flows(source_kind, source_ref, target_kind, target_ref);
        """
    )


def _migrate_digi_flow_steps_table(connection: sqlite3.Connection) -> None:
    steps_sql = _table_sql(connection, "digi_flow_steps")
    if not steps_sql:
        return
    required_step_types = (
        "receiver_local_tx",
        "filter_direct_only",
        "filter_digi",
        "filter_icon",
        "filter_rate_limit_per_callsign",
        "filter_strict",
    )
    foreign_keys = list(connection.execute("PRAGMA foreign_key_list(digi_flow_steps)").fetchall())
    references_legacy_flows = any(str(row["table"] or "") == "digi_flows_old" for row in foreign_keys)
    if all(step_type in steps_sql for step_type in required_step_types) and not references_legacy_flows:
        return
    connection.executescript(
        """
        ALTER TABLE digi_flow_steps RENAME TO digi_flow_steps_old;
        CREATE TABLE digi_flow_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flow_id INTEGER NOT NULL,
            step_order INTEGER NOT NULL,
            step_type TEXT NOT NULL CHECK (step_type IN (
                'receiver_rf',
                'receiver_aprsis',
                'receiver_local_tx',
                'filter_dupe',
                'filter_direct_only',
                'filter_digi',
                'filter_path',
                'filter_strict',
                'filter_callsign',
                'filter_packet_type',
                'filter_icon',
                'filter_distance',
                'filter_rate_limit',
                'filter_rate_limit_per_callsign',
                'tx_rf',
                'tx_aprsis',
                'action_drop',
                'action_log'
            )),
            title TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (flow_id) REFERENCES digi_flows(id) ON DELETE CASCADE,
            UNIQUE (flow_id, step_order)
        );
        INSERT INTO digi_flow_steps (
            id, flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
        )
        SELECT
            id, flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
        FROM digi_flow_steps_old;
        DROP TABLE digi_flow_steps_old;
        """
    )


def _migrate_digi_flow_event_log_table(connection: sqlite3.Connection) -> None:
    event_log_sql = _table_sql(connection, "digi_flow_event_log")
    if not event_log_sql:
        return
    foreign_keys = list(connection.execute("PRAGMA foreign_key_list(digi_flow_event_log)").fetchall())
    if not any(str(row["table"] or "") in {"digi_flow_steps_old", "digi_flows_old"} for row in foreign_keys):
        return
    connection.executescript(
        """
        ALTER TABLE digi_flow_event_log RENAME TO digi_flow_event_log_old;
        CREATE TABLE digi_flow_event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            frame_uid TEXT NOT NULL,
            flow_id INTEGER NOT NULL,
            step_id INTEGER,
            event_type TEXT NOT NULL,
            decision TEXT,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (flow_id) REFERENCES digi_flows(id) ON DELETE CASCADE,
            FOREIGN KEY (step_id) REFERENCES digi_flow_steps(id) ON DELETE SET NULL
        );
        INSERT INTO digi_flow_event_log (
            id, frame_uid, flow_id, step_id, event_type, decision, message, created_at
        )
        SELECT
            id, frame_uid, flow_id, step_id, event_type, decision, message, created_at
        FROM digi_flow_event_log_old;
        DROP TABLE digi_flow_event_log_old;
        """
    )


def _cleanup_legacy_digi_flow_tables(connection: sqlite3.Connection) -> None:
    legacy_flows_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'digi_flows_old' LIMIT 1"
    ).fetchone()
    if legacy_flows_exists is None:
        return
    step_fk = list(connection.execute("PRAGMA foreign_key_list(digi_flow_steps)").fetchall())
    event_log_fk = list(connection.execute("PRAGMA foreign_key_list(digi_flow_event_log)").fetchall())
    if any(str(row["table"] or "") == "digi_flows_old" for row in step_fk + event_log_fk):
        return
    connection.execute("DROP TABLE digi_flows_old")


def _table_sql(connection: sqlite3.Connection, table_name: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return str(row["sql"] or "") if row else ""


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(query, params).fetchone()


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with get_connection() as connection:
        return list(connection.execute(query, params).fetchall())


def execute(query: str, params: tuple[Any, ...] = ()) -> None:
    with get_connection() as connection:
        connection.execute(query, params)


def create_system_job(kind: str, *, message: str = "", log_file: str | None = None) -> int:
    now = utc_now()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO system_jobs(kind, status, message, log_file, created_at, updated_at)
            VALUES (?, 'queued', ?, ?, ?, ?)
            """,
            (kind, str(message or ""), str(log_file) if log_file else None, now, now),
        )
        return int(cursor.lastrowid)


def mark_system_job_running(
    job_id: int,
    *,
    pid: int | None = None,
    log_file: str | None = None,
    message: str = "",
) -> None:
    now = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE system_jobs
            SET status = 'running',
                message = ?,
                pid = COALESCE(?, pid),
                log_file = COALESCE(?, log_file),
                started_at = COALESCE(started_at, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (str(message or ""), pid, str(log_file) if log_file else None, now, now, int(job_id)),
        )


def mark_system_job_error(job_id: int, *, message: str) -> None:
    now = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE system_jobs
            SET status = 'error',
                message = ?,
                finished_at = COALESCE(finished_at, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (str(message or ""), now, now, int(job_id)),
        )


def fetch_system_job(job_id: int) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT
            id, kind, status, message, log_file, pid, exit_code,
            created_at, started_at, finished_at, updated_at
        FROM system_jobs
        WHERE id = ?
        """,
        (int(job_id),),
    )
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def get_app_setting(key: str) -> str | None:
    row = fetch_one("SELECT value FROM app_settings WHERE key = ?", (key,))
    if row is None:
        return None
    return str(row["value"])


def set_app_setting(key: str, value: str) -> None:
    global _event_log_min_level_cache, _event_log_debug_enabled_cache
    execute(
        """
        INSERT INTO app_settings(key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, value, utc_now()),
    )
    if key == EVENT_LOG_MIN_LEVEL_SETTING_KEY:
        _event_log_min_level_cache = normalize_event_log_level(value, default=DEFAULT_EVENT_LOG_MIN_LEVEL)
    elif key == EVENT_LOG_DEBUG_ENABLED_SETTING_KEY:
        _event_log_debug_enabled_cache = _normalize_app_setting_bool(value)


def normalize_event_log_level(value: Any, *, default: str = DEFAULT_EVENT_LOG_MIN_LEVEL) -> str:
    normalized_default = str(default or DEFAULT_EVENT_LOG_MIN_LEVEL).strip().upper()
    if normalized_default not in _EVENT_LOG_LEVEL_RANK:
        normalized_default = DEFAULT_EVENT_LOG_MIN_LEVEL
    normalized = str(value or "").strip().upper()
    if normalized in _EVENT_LOG_LEVEL_RANK:
        return normalized
    return normalized_default


def event_log_levels_at_or_above(min_level: str) -> tuple[str, ...]:
    normalized = normalize_event_log_level(min_level)
    minimum_rank = _EVENT_LOG_LEVEL_RANK.get(normalized, _EVENT_LOG_LEVEL_RANK[DEFAULT_EVENT_LOG_MIN_LEVEL])
    return tuple(level for level in EVENT_LOG_LEVELS if _EVENT_LOG_LEVEL_RANK[level] >= minimum_rank)


def get_event_log_min_level() -> str:
    global _event_log_min_level_cache
    if _event_log_min_level_cache is not None:
        return _event_log_min_level_cache
    stored = get_app_setting(EVENT_LOG_MIN_LEVEL_SETTING_KEY)
    _event_log_min_level_cache = normalize_event_log_level(stored, default=DEFAULT_EVENT_LOG_MIN_LEVEL)
    return _event_log_min_level_cache


def get_event_log_debug_enabled() -> bool:
    global _event_log_debug_enabled_cache
    if _event_log_debug_enabled_cache is not None:
        return _event_log_debug_enabled_cache
    _event_log_debug_enabled_cache = _normalize_app_setting_bool(get_app_setting(EVENT_LOG_DEBUG_ENABLED_SETTING_KEY))
    return _event_log_debug_enabled_cache


def _normalize_app_setting_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


def prune_event_logs(*, keep_rows: int) -> int:
    normalized_keep_rows = max(0, int(keep_rows))
    with get_connection() as connection:
        before_row = connection.execute("SELECT COUNT(*) AS total FROM event_logs").fetchone()
        before_total = int(before_row["total"]) if before_row is not None else 0
        if normalized_keep_rows == 0:
            connection.execute("DELETE FROM event_logs")
        else:
            connection.execute(
                """
                DELETE FROM event_logs
                WHERE id NOT IN (
                    SELECT id
                    FROM event_logs
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                )
                """,
                (normalized_keep_rows,),
            )
        after_row = connection.execute("SELECT COUNT(*) AS total FROM event_logs").fetchone()
        after_total = int(after_row["total"]) if after_row is not None else 0
    return before_total - after_total


def vacuum_database() -> None:
    connection = connect()
    try:
        connection.isolation_level = None
        connection.execute("VACUUM")
    finally:
        connection.close()


def database_maintenance_snapshot(*, tracked_tables: tuple[str, ...] = RUNTIME_MAINTENANCE_RESET_TABLES) -> dict[str, Any]:
    database_path = settings.database_path
    wal_path = Path(f"{database_path}-wal")
    shm_path = Path(f"{database_path}-shm")

    db_file_bytes = database_path.stat().st_size if database_path.exists() else 0
    wal_file_bytes = wal_path.stat().st_size if wal_path.exists() else 0
    shm_file_bytes = shm_path.stat().st_size if shm_path.exists() else 0

    with get_connection() as connection:
        page_size_row = connection.execute("PRAGMA page_size").fetchone()
        page_count_row = connection.execute("PRAGMA page_count").fetchone()
        freelist_row = connection.execute("PRAGMA freelist_count").fetchone()
        quick_check_row = connection.execute("PRAGMA quick_check").fetchone()

        page_size = int(page_size_row[0]) if page_size_row else 0
        page_count = int(page_count_row[0]) if page_count_row else 0
        freelist_count = int(freelist_row[0]) if freelist_row else 0
        quick_check = str(quick_check_row[0]) if quick_check_row else "unknown"

        existing_tables = {
            str(row["name"])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        tracked_row_counts: dict[str, int] = {}
        for table_name in tracked_tables:
            if table_name not in existing_tables:
                continue
            row = connection.execute(f'SELECT COUNT(*) AS total FROM "{table_name}"').fetchone()
            tracked_row_counts[table_name] = int(row["total"]) if row is not None else 0

    allocated_bytes = page_size * page_count
    reclaimable_bytes = page_size * freelist_count
    reclaimable_ratio = (reclaimable_bytes / allocated_bytes) if allocated_bytes > 0 else 0.0
    vacuum_recommended = (
        reclaimable_bytes >= VACUUM_RECOMMEND_FREE_BYTES_MIN
        and reclaimable_ratio >= VACUUM_RECOMMEND_FREE_RATIO_MIN
    )

    return {
        "database_path": str(database_path),
        "database_exists": database_path.exists(),
        "database_file_bytes": db_file_bytes,
        "wal_file_bytes": wal_file_bytes,
        "shm_file_bytes": shm_file_bytes,
        "page_size": page_size,
        "page_count": page_count,
        "freelist_count": freelist_count,
        "allocated_bytes": allocated_bytes,
        "reclaimable_bytes": reclaimable_bytes,
        "reclaimable_ratio": reclaimable_ratio,
        "quick_check": quick_check,
        "vacuum_recommended": vacuum_recommended,
        "tracked_row_counts": tracked_row_counts,
    }


def reset_runtime_operational_data(*, table_names: tuple[str, ...] = RUNTIME_MAINTENANCE_RESET_TABLES) -> dict[str, int]:
    deleted_by_table: dict[str, int] = {}
    with get_connection() as connection:
        existing_tables = {
            str(row["name"])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        for table_name in table_names:
            if table_name not in existing_tables:
                continue
            before_row = connection.execute(f'SELECT COUNT(*) AS total FROM "{table_name}"').fetchone()
            before_total = int(before_row["total"]) if before_row is not None else 0
            if before_total > 0:
                connection.execute(f'DELETE FROM "{table_name}"')
            deleted_by_table[table_name] = before_total
    return deleted_by_table


def log_event(level: str, category: str, message: str) -> None:
    normalized_level = normalize_event_log_level(level)
    if normalized_level == "DEBUG":
        if not get_event_log_debug_enabled():
            return
    else:
        minimum_level = get_event_log_min_level()
        if _EVENT_LOG_LEVEL_RANK[normalized_level] < _EVENT_LOG_LEVEL_RANK[minimum_level]:
            return
    execute(
        "INSERT INTO event_logs(level, category, message, created_at) VALUES (?, ?, ?, ?)",
        (normalized_level, category, message, utc_now()),
    )


def traffic_retention_cutoff() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat()
