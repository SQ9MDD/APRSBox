from __future__ import annotations

import json
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
TRAFFIC_RETENTION_MINUTES_SETTING_KEY = "traffic_retention_minutes"
DEFAULT_EVENT_LOG_MIN_LEVEL = "INFO"
DEFAULT_TRAFFIC_RETENTION_MINUTES = 60
TRAFFIC_RETENTION_ALLOWED_MINUTES: tuple[int, ...] = (*range(60, 361, 30), 720, 1440)
DATABASE_INDEX_REPAIR_SETTING_KEY = "database.index_repair.version"
DATABASE_INDEX_REPAIR_VERSION = "2026-07-index-repair-v1"
DEFAULT_OUTBOUND_JOB_PRUNE_BATCH_SIZE = 500
DEFAULT_OUTBOUND_SENT_RETENTION_DAYS = 7
DEFAULT_OUTBOUND_FAILURE_RETENTION_DAYS = 30
DEFAULT_OUTBOUND_RETENTION_MIN_ROWS_PER_GROUP = 200
OUTBOUND_RETENTION_KINDS: tuple[str, ...] = ("beacon", "status", "object", "wx", "digi_tx")
OUTBOUND_RETENTION_FAILURE_STATUSES: tuple[str, ...] = ("failed", "cancelled")
_EVENT_LOG_LEVEL_RANK = {level: index for index, level in enumerate(EVENT_LOG_LEVELS)}

_event_log_min_level_cache: str | None = None
_event_log_debug_enabled_cache: bool | None = None

RUNTIME_MAINTENANCE_RESET_TABLES: tuple[str, ...] = (
    "event_logs",
    "traffic_frames",
    "digi_flow_event_log",
    "aprsis_igate_rf_heard",
    "aprsis_igate_station_state",
    "aprsis_igate_pending_position",
    "traffic_device_station_device_hourly",
    "radio_activity_5m",
    "aprsis_uplink_minute_stats",
    "aprsis_uplink_stats",
    "wx_runtime_cache",
    "notification_radar_state",
    "band_condition_audibility_buckets",
    "band_condition_activity_station_buckets",
    "band_condition_activity_buckets",
    "band_condition_station_hours",
    "band_condition_station_profiles",
    "band_condition_hourly",
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
    progress_percent INTEGER NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),
    stage TEXT NOT NULL DEFAULT '',
    protocol_comment TEXT NOT NULL DEFAULT '',
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

CREATE TABLE IF NOT EXISTS notification_transports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    transport_type TEXT NOT NULL CHECK (transport_type IN ('webhook', 'telegram')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    url TEXT NOT NULL DEFAULT '',
    secret_header_name TEXT NOT NULL DEFAULT '',
    secret_token TEXT NOT NULL DEFAULT '',
    bot_token TEXT NOT NULL DEFAULT '',
    chat_id TEXT NOT NULL DEFAULT '',
    timeout_s INTEGER NOT NULL DEFAULT 5 CHECK (timeout_s BETWEEN 1 AND 60),
    last_test_status TEXT NOT NULL DEFAULT '' CHECK (last_test_status IN ('', 'ok', 'error')),
    last_test_error TEXT NOT NULL DEFAULT '',
    last_test_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_radar_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    pattern TEXT NOT NULL,
    distance_m INTEGER NOT NULL DEFAULT 0 CHECK (distance_m >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_radar_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    station_key TEXT NOT NULL,
    is_inside INTEGER NOT NULL DEFAULT 0 CHECK (is_inside IN (0, 1)),
    last_matched_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (rule_id) REFERENCES notification_radar_rules(id) ON DELETE CASCADE,
    UNIQUE (rule_id, station_key)
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
    conversation_kind TEXT NOT NULL DEFAULT 'direct' CHECK (conversation_kind IN ('direct', 'group')),
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
        'filter_rf_guard',
        'filter_aprsis_message_delivery',
        'filter_rf_tx_guard',
        'filter_allow_rules',
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

CREATE TABLE IF NOT EXISTS aprsis_rf_stats (
    flow_id INTEGER PRIMARY KEY,
    received_from_aprsis INTEGER NOT NULL DEFAULT 0,
    matched_message_rule INTEGER NOT NULL DEFAULT 0,
    matched_associated_position INTEGER NOT NULL DEFAULT 0,
    matched_allow_rule INTEGER NOT NULL DEFAULT 0,
    dropped_no_allow_rule INTEGER NOT NULL DEFAULT 0,
    dropped_recipient_not_local INTEGER NOT NULL DEFAULT 0,
    dropped_recipient_seen_internet INTEGER NOT NULL DEFAULT 0,
    dropped_sender_heard_rf INTEGER NOT NULL DEFAULT 0,
    dropped_safety_guard INTEGER NOT NULL DEFAULT 0,
    dropped_duplicate INTEGER NOT NULL DEFAULT 0,
    cancelled_during_viscous_delay INTEGER NOT NULL DEFAULT 0,
    dropped_rate_limit INTEGER NOT NULL DEFAULT 0,
    dropped_oversize INTEGER NOT NULL DEFAULT 0,
    queued_to_rf INTEGER NOT NULL DEFAULT 0,
    transmitted_to_rf INTEGER NOT NULL DEFAULT 0,
    tx_failed INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (flow_id) REFERENCES digi_flows(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS aprsis_igate_rf_heard (
    station_key TEXT NOT NULL,
    interface_id INTEGER NOT NULL,
    last_heard_at TEXT NOT NULL,
    last_path TEXT NOT NULL DEFAULT '',
    consumed_hops INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (station_key, interface_id),
    FOREIGN KEY (interface_id) REFERENCES modems(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS aprsis_igate_station_state (
    station_key TEXT PRIMARY KEY,
    last_internet_origin_at TEXT
);

CREATE TABLE IF NOT EXISTS aprsis_igate_pending_position (
    flow_id INTEGER NOT NULL,
    sender_key TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (flow_id, sender_key),
    FOREIGN KEY (flow_id) REFERENCES digi_flows(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS aprs_objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    lifetime TEXT NOT NULL DEFAULT 'temporary' CHECK (lifetime IN ('temporary', 'permanent')),
    state TEXT NOT NULL DEFAULT 'live' CHECK (state IN ('live', 'killed')),
    is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0, 1)),
    interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (interval_minutes IN (5, 10, 15, 30, 45, 60)),
    valid_until_utc TEXT,
    activation_mode TEXT NOT NULL DEFAULT 'manual' CHECK (activation_mode IN ('manual', 'scheduled', 'recurring')),
    active_from_utc TEXT,
    active_until_utc TEXT,
    first_activation_utc TEXT,
    recurrence_duration_minutes INTEGER,
    recurrence_interval_value INTEGER,
    recurrence_interval_unit TEXT,
    recurrence_until_utc TEXT,
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
    valid_until_utc TEXT,
    activation_mode TEXT NOT NULL DEFAULT 'manual' CHECK (activation_mode IN ('manual', 'scheduled', 'recurring')),
    active_from_utc TEXT,
    active_until_utc TEXT,
    first_activation_utc TEXT,
    recurrence_duration_minutes INTEGER,
    recurrence_interval_value INTEGER,
    recurrence_interval_unit TEXT,
    recurrence_until_utc TEXT,
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
    activation_mode TEXT NOT NULL DEFAULT 'manual' CHECK (activation_mode IN ('manual', 'scheduled', 'recurring')),
    active_from_utc TEXT,
    active_until_utc TEXT,
    first_activation_utc TEXT,
    recurrence_duration_minutes INTEGER,
    recurrence_interval_value INTEGER,
    recurrence_interval_unit TEXT,
    recurrence_until_utc TEXT,
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
    source_kind TEXT NOT NULL DEFAULT 'rf',
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

CREATE TABLE IF NOT EXISTS aprs_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_key TEXT NOT NULL,
    source_callsign TEXT NOT NULL COLLATE NOCASE,
    alert_type TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    alarm_group TEXT,
    expiry TEXT,
    expires_at TEXT,
    event_code TEXT,
    area_code TEXT,
    message_id TEXT,
    logical_alert_id TEXT,
    severity_level INTEGER,
    received_parts INTEGER NOT NULL DEFAULT 0 CHECK (received_parts >= 0),
    parts_total INTEGER CHECK (parts_total IS NULL OR parts_total >= 1),
    completion_status TEXT NOT NULL DEFAULT 'incomplete'
        CHECK (completion_status IN ('incomplete', 'complete')),
    superseded_by_alert_id INTEGER,
    area_codes_json TEXT NOT NULL DEFAULT '[]',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    cancelled_at TEXT,
    valid_until_utc TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    frame_count INTEGER NOT NULL DEFAULT 1 CHECK (frame_count >= 1),
    initial_frame_id INTEGER,
    last_frame_id INTEGER,
    latitude REAL,
    longitude REAL,
    muted_until TEXT,
    muted_indefinitely INTEGER NOT NULL DEFAULT 0 CHECK (muted_indefinitely IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (initial_frame_id) REFERENCES traffic_frames(id) ON DELETE SET NULL,
    FOREIGN KEY (last_frame_id) REFERENCES traffic_frames(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS aprs_alert_parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER NOT NULL,
    part_identity_key TEXT NOT NULL,
    part_number INTEGER,
    parts_total INTEGER,
    aprs_message_id TEXT,
    area_codes_json TEXT NOT NULL DEFAULT '[]',
    raw_message TEXT NOT NULL DEFAULT '',
    comment_fragment TEXT NOT NULL DEFAULT '',
    first_received_at TEXT NOT NULL,
    last_received_at TEXT NOT NULL,
    received_count INTEGER NOT NULL DEFAULT 1 CHECK (received_count >= 1),
    initial_frame_id INTEGER,
    last_frame_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (alert_id) REFERENCES aprs_alerts(id) ON DELETE CASCADE,
    FOREIGN KEY (initial_frame_id) REFERENCES traffic_frames(id) ON DELETE SET NULL,
    FOREIGN KEY (last_frame_id) REFERENCES traffic_frames(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS aprs_alert_frames (
    alert_id INTEGER NOT NULL,
    frame_id INTEGER NOT NULL UNIQUE,
    part_id INTEGER,
    received_at TEXT NOT NULL,
    PRIMARY KEY (alert_id, frame_id),
    FOREIGN KEY (alert_id) REFERENCES aprs_alerts(id) ON DELETE CASCADE,
    FOREIGN KEY (frame_id) REFERENCES traffic_frames(id) ON DELETE CASCADE,
    FOREIGN KEY (part_id) REFERENCES aprs_alert_parts(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS own_aprs_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL,
    sender_callsign TEXT NOT NULL COLLATE NOCASE,
    target_group TEXT NOT NULL COLLATE NOCASE,
    area_code TEXT NOT NULL,
    area_name TEXT NOT NULL,
    area_parent TEXT NOT NULL DEFAULT '',
    event_code TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    repeat_interval_minutes INTEGER NOT NULL
        CHECK (repeat_interval_minutes IN (15, 30, 60)),
    next_transmission_at TEXT,
    last_transmission_at TEXT,
    transmission_count INTEGER NOT NULL DEFAULT 0 CHECK (transmission_count >= 0),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'expired', 'cancelled', 'error')),
    cancelled_at TEXT,
    message_ids_json TEXT NOT NULL DEFAULT '[]',
    cancel_message_id TEXT,
    parts_total INTEGER NOT NULL DEFAULT 1 CHECK (parts_total BETWEEN 1 AND 9),
    tx_path TEXT NOT NULL DEFAULT '',
    last_error TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (sender_callsign, target_group, alert_id)
);

CREATE TABLE IF NOT EXISTS own_aprs_alert_tx_jobs (
    own_alert_id INTEGER NOT NULL,
    outbound_job_id INTEGER NOT NULL UNIQUE,
    dispatch_token TEXT NOT NULL,
    dispatch_kind TEXT NOT NULL CHECK (dispatch_kind IN ('alert', 'cancel')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (own_alert_id, outbound_job_id),
    FOREIGN KEY (own_alert_id) REFERENCES own_aprs_alerts(id) ON DELETE CASCADE,
    FOREIGN KEY (outbound_job_id) REFERENCES outbound_jobs(id) ON DELETE CASCADE
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

CREATE TABLE IF NOT EXISTS band_condition_station_hours (
    hour_start_utc TEXT NOT NULL,
    interface_id INTEGER NOT NULL,
    interface_name TEXT NOT NULL DEFAULT '',
    band TEXT NOT NULL CHECK (band IN ('2m', '70cm')),
    station_key TEXT NOT NULL,
    segment_mask INTEGER NOT NULL DEFAULT 0,
    direct_segment_mask INTEGER NOT NULL DEFAULT 0,
    fixed_hint INTEGER NOT NULL DEFAULT 0 CHECK (fixed_hint IN (0, 1)),
    mobile_hint INTEGER NOT NULL DEFAULT 0 CHECK (mobile_hint IN (0, 1)),
    latitude REAL,
    longitude REAL,
    distance_km REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (hour_start_utc, interface_id, band, station_key)
);

CREATE TABLE IF NOT EXISTS band_condition_station_profiles (
    interface_id INTEGER NOT NULL,
    band TEXT NOT NULL CHECK (band IN ('2m', '70cm')),
    station_key TEXT NOT NULL,
    first_heard_at TEXT NOT NULL,
    last_heard_at TEXT NOT NULL,
    observed_hours INTEGER NOT NULL DEFAULT 0,
    direct_hours INTEGER NOT NULL DEFAULT 0,
    positioned_hours INTEGER NOT NULL DEFAULT 0,
    fixed_hours INTEGER NOT NULL DEFAULT 0,
    mobile_hours INTEGER NOT NULL DEFAULT 0,
    latitude REAL,
    longitude REAL,
    distance_km REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (interface_id, band, station_key)
);

CREATE TABLE IF NOT EXISTS band_condition_hourly (
    hour_start_utc TEXT NOT NULL,
    interface_id INTEGER NOT NULL,
    interface_name TEXT NOT NULL DEFAULT '',
    band TEXT NOT NULL CHECK (band IN ('2m', '70cm')),
    condition_index INTEGER CHECK (condition_index BETWEEN 0 AND 5),
    confidence_score REAL NOT NULL DEFAULT 0 CHECK (confidence_score BETWEEN 0 AND 1),
    fixed_station_count INTEGER NOT NULL DEFAULT 0,
    positioned_station_count INTEGER NOT NULL DEFAULT 0,
    direct_station_count INTEGER NOT NULL DEFAULT 0,
    median_distance_km REAL,
    p90_distance_km REAL,
    max_confirmed_distance_km REAL,
    normal_station_count REAL NOT NULL DEFAULT 0,
    normal_p90_distance_km REAL,
    far_station_count INTEGER NOT NULL DEFAULT 0,
    very_far_station_count INTEGER NOT NULL DEFAULT 0,
    new_area_count INTEGER NOT NULL DEFAULT 0,
    history_hours INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    PRIMARY KEY (hour_start_utc, interface_id, band)
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
CREATE INDEX IF NOT EXISTS idx_aprs_alerts_last_seen_at ON aprs_alerts(last_seen_at DESC, id DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_aprs_alert_parts_identity
    ON aprs_alert_parts(part_identity_key);
CREATE INDEX IF NOT EXISTS idx_aprs_alert_parts_alert_part
    ON aprs_alert_parts(alert_id, part_number, id);
CREATE INDEX IF NOT EXISTS idx_aprs_alert_frames_alert_received_at
    ON aprs_alert_frames(alert_id, received_at DESC, frame_id DESC);
CREATE INDEX IF NOT EXISTS idx_own_aprs_alerts_status_next
    ON own_aprs_alerts(status, next_transmission_at, id);
CREATE INDEX IF NOT EXISTS idx_own_aprs_alert_tx_jobs_dispatch
    ON own_aprs_alert_tx_jobs(dispatch_token, outbound_job_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_modems_single_aprsis
    ON modems(UPPER(modem_type))
    WHERE UPPER(modem_type) = 'APRSIS';
CREATE INDEX IF NOT EXISTS idx_traffic_device_station_device_hourly_bucket
    ON traffic_device_station_device_hourly(bucket_start_utc, station_key);
CREATE INDEX IF NOT EXISTS idx_traffic_runtime_interfaces_status_updated_at ON traffic_runtime_interfaces(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_digi_flow_event_log_flow_created_at ON digi_flow_event_log(flow_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_map_sources_enabled_sort ON map_sources(enabled DESC, sort_order ASC, id ASC);
CREATE INDEX IF NOT EXISTS idx_digi_flow_event_log_frame_uid ON digi_flow_event_log(frame_uid);
CREATE INDEX IF NOT EXISTS idx_digi_flows_route_pair ON digi_flows(source_kind, source_ref, target_kind, target_ref);
CREATE INDEX IF NOT EXISTS idx_outbound_jobs_status_scheduled_at ON outbound_jobs(status, scheduled_at, id);
CREATE INDEX IF NOT EXISTS idx_outbound_jobs_kind_status_scheduled_at ON outbound_jobs(kind, status, scheduled_at, id);
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
CREATE INDEX IF NOT EXISTS idx_band_condition_station_hours_interface_time
    ON band_condition_station_hours(interface_id, band, hour_start_utc);
CREATE INDEX IF NOT EXISTS idx_band_condition_station_hours_station_time
    ON band_condition_station_hours(interface_id, band, station_key, hour_start_utc);
CREATE INDEX IF NOT EXISTS idx_band_condition_profiles_interface_band
    ON band_condition_station_profiles(interface_id, band, observed_hours DESC);
CREATE INDEX IF NOT EXISTS idx_band_condition_hourly_interface_time
    ON band_condition_hourly(interface_id, band, hour_start_utc);
CREATE INDEX IF NOT EXISTS idx_radio_activity_5m_bucket_start
    ON radio_activity_5m(bucket_start_utc);
CREATE INDEX IF NOT EXISTS idx_radio_activity_5m_bucket_interface
    ON radio_activity_5m(bucket_start_utc, interface_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_radio_activity_5m_bucket_source
    ON radio_activity_5m(bucket_start_utc, source_name);
CREATE INDEX IF NOT EXISTS idx_aprsis_igate_rf_heard_time
    ON aprsis_igate_rf_heard(last_heard_at DESC);
CREATE INDEX IF NOT EXISTS idx_aprsis_igate_station_state_time
    ON aprsis_igate_station_state(last_internet_origin_at DESC);
CREATE INDEX IF NOT EXISTS idx_aprsis_igate_pending_position_expiry
    ON aprsis_igate_pending_position(expires_at);
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
        _migrate_aprsis_rf_guard_steps(connection)
        _migrate_aprsis_rf_stats_table(connection)
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
        message_conversation_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(aprs_message_conversations)").fetchall()
        }
        traffic_frame_columns = {row["name"] for row in connection.execute("PRAGMA table_info(traffic_frames)").fetchall()}
        alert_columns = {row["name"] for row in connection.execute("PRAGMA table_info(aprs_alerts)").fetchall()}
        alert_part_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(aprs_alert_parts)").fetchall()
        }
        alert_frame_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(aprs_alert_frames)").fetchall()
        }
        traffic_runtime_columns = {row["name"] for row in connection.execute("PRAGMA table_info(traffic_runtime_state)").fetchall()}
        traffic_runtime_interface_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(traffic_runtime_interfaces)").fetchall()
        }
        digi_flow_columns = {row["name"] for row in connection.execute("PRAGMA table_info(digi_flows)").fetchall()}
        radio_activity_columns = {row["name"] for row in connection.execute("PRAGMA table_info(radio_activity_5m)").fetchall()}
        if "conversation_kind" not in message_conversation_columns:
            connection.execute(
                """
                ALTER TABLE aprs_message_conversations
                ADD COLUMN conversation_kind TEXT NOT NULL DEFAULT 'direct'
                CHECK (conversation_kind IN ('direct', 'group'))
                """
            )
        if "last_login_at" not in user_columns:
            connection.execute(
                """
                ALTER TABLE users
                ADD COLUMN last_login_at TEXT
                """
            )
        if "alarm_group" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN alarm_group TEXT
                """
            )
        if "identity_key" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN identity_key TEXT
                """
            )
        if "expiry" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN expiry TEXT
                """
            )
        if "expires_at" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN expires_at TEXT
                """
            )
        if "event_code" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN event_code TEXT
                """
            )
        if "area_code" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN area_code TEXT
                """
            )
        if "message_id" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN message_id TEXT
                """
            )
        if "logical_alert_id" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN logical_alert_id TEXT
                """
            )
        if "severity_level" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN severity_level INTEGER
                """
            )
        if "received_parts" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN received_parts INTEGER NOT NULL DEFAULT 0
                CHECK (received_parts >= 0)
                """
            )
        if "parts_total" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN parts_total INTEGER
                CHECK (parts_total IS NULL OR parts_total >= 1)
                """
            )
        if "completion_status" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN completion_status TEXT NOT NULL DEFAULT 'incomplete'
                CHECK (completion_status IN ('incomplete', 'complete'))
                """
            )
        if "superseded_by_alert_id" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN superseded_by_alert_id INTEGER
                """
            )
        if "area_codes_json" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN area_codes_json TEXT NOT NULL DEFAULT '[]'
                """
            )
        if "is_active" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1
                CHECK (is_active IN (0, 1))
                """
            )
        if "valid_until_utc" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN valid_until_utc TEXT
                """
            )
        if "protocol_comment" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN protocol_comment TEXT NOT NULL DEFAULT ''
                """
            )
        if "cancelled_at" not in alert_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alerts
                ADD COLUMN cancelled_at TEXT
                """
            )
        if "comment_fragment" not in alert_part_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alert_parts
                ADD COLUMN comment_fragment TEXT NOT NULL DEFAULT ''
                """
            )
        if "part_id" not in alert_frame_columns:
            connection.execute(
                """
                ALTER TABLE aprs_alert_frames
                ADD COLUMN part_id INTEGER
                """
            )
        _migrate_aprs_alert_identity(connection)
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
        if "source_kind" not in traffic_frame_columns:
            connection.execute(
                """
                ALTER TABLE traffic_frames
                ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'rf'
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
        connection.execute(
            """
CREATE INDEX IF NOT EXISTS idx_traffic_frames_source_kind_created_at
    ON traffic_frames(source_kind, created_at DESC, id DESC)
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
CREATE INDEX IF NOT EXISTS idx_outbound_jobs_kind_status_scheduled_at
    ON outbound_jobs(kind, status, scheduled_at, id)
"""
        )
        connection.execute(
            """
CREATE INDEX IF NOT EXISTS idx_aprs_messages_direction_status_last_attempt_at
    ON aprs_messages(direction, status, last_attempt_at, id)
"""
        )
        connection.execute(
            """
CREATE INDEX IF NOT EXISTS idx_aprs_messages_direction_unread_conversation
    ON aprs_messages(direction, is_unread, conversation_id)
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
        if "valid_until_utc" not in item_columns:
            connection.execute(
                """
                ALTER TABLE aprs_items
                ADD COLUMN valid_until_utc TEXT
                """
            )
        if "valid_until_utc" not in bulletin_columns:
            connection.execute(
                """
                ALTER TABLE bulletins
                ADD COLUMN valid_until_utc TEXT
                """
            )
        for table_name in ("aprs_objects", "aprs_items", "bulletins"):
            _ensure_activation_schedule_columns(connection, table_name)
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
        connection.commit()
        _run_database_index_repair_for_update(connection)


def _migrate_aprs_alert_identity(connection: sqlite3.Connection) -> None:
    from app.services.aprs_warning_identity import (
        build_aprs_alert_identity_key,
        build_aprs_alert_part_identity_key,
        parse_aprs_group_warning_content,
        resolve_aprs_expiry_utc,
    )

    connection.execute("DROP INDEX IF EXISTS idx_aprs_alerts_identity_key")
    rows = connection.execute(
        """
        SELECT
            id, identity_key, source_callsign, alert_type, message,
            alarm_group, expiry, expires_at, event_code, area_code, message_id,
            logical_alert_id, severity_level,
            area_codes_json, frame_count,
            initial_frame_id, last_frame_id,
            first_seen_at, last_seen_at
        FROM aprs_alerts
        WHERE superseded_by_alert_id IS NULL
        ORDER BY id ASC
        """
    ).fetchall()
    for row in rows:
        message = str(row["message"] or "")
        parsed_candidate = parse_aprs_group_warning_content(message)
        alarm_group = str(row["alarm_group"] or "").strip().upper()
        alert_type = str(row["alert_type"] or "").strip().upper()
        looks_like_country_warning_group = (
            len(alert_type) == 7
            and alert_type[2:] == "-WARN"
            and alert_type[:2].isascii()
            and alert_type[:2].isalpha()
        )
        if (
            not alarm_group
            and looks_like_country_warning_group
            and parsed_candidate["area_code"]
        ):
            alarm_group = alert_type
        parsed = (
            parsed_candidate
            if alarm_group
            else {
                "expiry": "",
                "event_code": "",
                "severity_level": None,
                "logical_alert_id": "",
                "part_number": None,
                "parts_total": None,
                "area_code": "",
                "area_codes": [],
                "message_id": "",
            }
        )

        expiry = str(row["expiry"] or parsed["expiry"] or "").strip()
        resolved_expiry = resolve_aprs_expiry_utc(
            expiry,
            row["first_seen_at"],
        )
        expires_at = str(row["expires_at"] or "").strip() or (
            resolved_expiry.replace(microsecond=0).isoformat()
            if resolved_expiry is not None
            else ""
        )
        event_code = str(row["event_code"] or parsed["event_code"] or "").strip()
        message_id = str(row["message_id"] or parsed["message_id"] or "").strip()
        logical_alert_id = str(
            row["logical_alert_id"] or parsed["logical_alert_id"] or ""
        ).strip().upper()
        has_stored_parts = (
            connection.execute(
                """
                SELECT 1
                FROM aprs_alert_parts
                WHERE alert_id = ?
                LIMIT 1
                """,
                (int(row["id"]),),
            ).fetchone()
            is not None
        )
        area_code = str(
            parsed["area_code"]
            if logical_alert_id and not has_stored_parts
            else row["area_code"] or parsed["area_code"] or ""
        ).strip()
        severity_level = (
            int(row["severity_level"])
            if row["severity_level"] is not None
            else parsed["severity_level"]
        )
        area_codes_json = str(row["area_codes_json"] or "").strip()
        try:
            stored_area_codes = json.loads(area_codes_json) if area_codes_json else []
        except (TypeError, ValueError, json.JSONDecodeError):
            stored_area_codes = []
        if logical_alert_id and parsed["area_codes"] and not has_stored_parts:
            area_codes_json = json.dumps(
                parsed["area_codes"],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        elif not stored_area_codes and parsed["area_codes"]:
            area_codes_json = json.dumps(
                parsed["area_codes"],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        elif not area_codes_json:
            area_codes_json = "[]"

        identity_key = str(row["identity_key"] or "").strip()
        if logical_alert_id:
            identity_key = build_aprs_alert_identity_key(
                source_callsign=row["source_callsign"],
                alarm_group=alarm_group,
                logical_alert_id=logical_alert_id,
                message_id=message_id,
                raw_content=message,
            )
        elif not identity_key:
            identity_key = build_aprs_alert_identity_key(
                source_callsign=row["source_callsign"],
                alarm_group=alarm_group,
                logical_alert_id=logical_alert_id,
                message_id=message_id,
                raw_content=message,
            )
        connection.execute(
            """
            UPDATE aprs_alerts
            SET identity_key = ?,
                alarm_group = ?,
                expiry = ?,
                expires_at = ?,
                event_code = ?,
                area_code = ?,
                message_id = ?,
                logical_alert_id = ?,
                severity_level = ?,
                area_codes_json = ?
            WHERE id = ?
            """,
            (
                identity_key,
                alarm_group or None,
                expiry or None,
                expires_at or None,
                event_code or None,
                area_code or None,
                message_id or None,
                logical_alert_id or None,
                severity_level,
                area_codes_json,
                int(row["id"]),
            ),
        )
        if alarm_group:
            part_identity_key = build_aprs_alert_part_identity_key(
                source_callsign=row["source_callsign"],
                alarm_group=alarm_group,
                message_id=message_id,
                raw_content=message,
            )
            part_number = parsed["part_number"] or 1
            parts_total = parsed["parts_total"] or 1
            part_cursor = connection.execute(
                """
                INSERT INTO aprs_alert_parts(
                    alert_id, part_identity_key,
                    part_number, parts_total, aprs_message_id,
                    area_codes_json, raw_message,
                    first_received_at, last_received_at, received_count,
                    initial_frame_id, last_frame_id,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(part_identity_key) DO NOTHING
                """,
                (
                    int(row["id"]),
                    part_identity_key,
                    part_number,
                    parts_total,
                    message_id or None,
                    area_codes_json,
                    message,
                    row["first_seen_at"],
                    row["last_seen_at"],
                    max(1, int(row["frame_count"] or 1)),
                    row["initial_frame_id"],
                    row["last_frame_id"],
                    row["first_seen_at"],
                    row["last_seen_at"],
                ),
            )
            if int(part_cursor.rowcount or 0) == 1:
                part_id = int(part_cursor.lastrowid)
            else:
                part_row = connection.execute(
                    """
                    SELECT id
                    FROM aprs_alert_parts
                    WHERE part_identity_key = ?
                    """,
                    (part_identity_key,),
                ).fetchone()
                part_id = int(part_row["id"]) if part_row is not None else None
            if part_id is not None:
                connection.execute(
                    """
                    UPDATE aprs_alert_frames
                    SET part_id = ?
                    WHERE alert_id = ?
                    """,
                    (part_id, int(row["id"])),
                )
            received_part_numbers = {
                int(part_row["part_number"])
                for part_row in connection.execute(
                    """
                    SELECT part_number
                    FROM aprs_alert_parts
                    WHERE alert_id = ?
                      AND part_number IS NOT NULL
                    """,
                    (int(row["id"]),),
                ).fetchall()
            }
            aggregate_parts_total = max(
                [
                    int(part_row["parts_total"])
                    for part_row in connection.execute(
                        """
                        SELECT parts_total
                        FROM aprs_alert_parts
                        WHERE alert_id = ?
                          AND parts_total IS NOT NULL
                        """,
                        (int(row["id"]),),
                    ).fetchall()
                ]
                or [1]
            )
            completion_status = (
                "complete"
                if set(range(1, aggregate_parts_total + 1)).issubset(
                    received_part_numbers
                )
                else "incomplete"
            )
            connection.execute(
                """
                UPDATE aprs_alerts
                SET received_parts = ?,
                    parts_total = ?,
                    completion_status = ?
                WHERE id = ?
                """,
                (
                    len(
                        {
                            number
                            for number in received_part_numbers
                            if 1 <= number <= aggregate_parts_total
                        }
                    ),
                    aggregate_parts_total,
                    completion_status,
                    int(row["id"]),
                ),
            )

    duplicate_logical_groups = connection.execute(
        """
        SELECT
            UPPER(source_callsign) AS source_key,
            UPPER(alarm_group) AS group_key,
            UPPER(logical_alert_id) AS logical_key
        FROM aprs_alerts
        WHERE alarm_group IS NOT NULL
          AND TRIM(alarm_group) != ''
          AND logical_alert_id IS NOT NULL
          AND TRIM(logical_alert_id) != ''
          AND superseded_by_alert_id IS NULL
        GROUP BY
            UPPER(source_callsign),
            UPPER(alarm_group),
            UPPER(logical_alert_id)
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    for duplicate_group in duplicate_logical_groups:
        logical_rows = connection.execute(
            """
            SELECT *
            FROM aprs_alerts
            WHERE UPPER(source_callsign) = ?
              AND UPPER(alarm_group) = ?
              AND UPPER(logical_alert_id) = ?
              AND superseded_by_alert_id IS NULL
            ORDER BY first_seen_at ASC, id ASC
            """,
            (
                duplicate_group["source_key"],
                duplicate_group["group_key"],
                duplicate_group["logical_key"],
            ),
        ).fetchall()
        if len(logical_rows) < 2:
            continue

        canonical = logical_rows[0]
        canonical_id = int(canonical["id"])
        newest = max(
            logical_rows,
            key=lambda candidate: (
                str(candidate["last_seen_at"] or ""),
                int(candidate["id"]),
            ),
        )
        for duplicate in logical_rows[1:]:
            duplicate_id = int(duplicate["id"])
            connection.execute(
                "UPDATE aprs_alert_parts SET alert_id = ? WHERE alert_id = ?",
                (canonical_id, duplicate_id),
            )
            connection.execute(
                "UPDATE aprs_alert_frames SET alert_id = ? WHERE alert_id = ?",
                (canonical_id, duplicate_id),
            )
            superseded_identity = json.dumps(
                [
                    "aprs-alert-superseded",
                    duplicate_id,
                    str(duplicate["identity_key"] or ""),
                ],
                ensure_ascii=True,
                separators=(",", ":"),
            )
            connection.execute(
                """
                UPDATE aprs_alerts
                SET identity_key = ?,
                    superseded_by_alert_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    superseded_identity,
                    canonical_id,
                    newest["updated_at"],
                    duplicate_id,
                ),
            )

        part_rows = connection.execute(
            """
            SELECT part_number, parts_total, area_codes_json
            FROM aprs_alert_parts
            WHERE alert_id = ?
            ORDER BY
                CASE WHEN part_number IS NULL THEN 1 ELSE 0 END,
                part_number ASC,
                id ASC
            """,
            (canonical_id,),
        ).fetchall()
        aggregate_area_codes: list[str] = []
        seen_area_codes: set[str] = set()
        received_part_numbers: set[int] = set()
        declared_totals: list[int] = []
        for part_row in part_rows:
            if part_row["part_number"] is not None:
                part_number = int(part_row["part_number"])
                if part_number >= 1:
                    received_part_numbers.add(part_number)
            if part_row["parts_total"] is not None:
                declared_total = int(part_row["parts_total"])
                if declared_total >= 1:
                    declared_totals.append(declared_total)
            try:
                stored_codes = json.loads(part_row["area_codes_json"] or "[]")
            except (TypeError, ValueError, json.JSONDecodeError):
                stored_codes = []
            for value in stored_codes if isinstance(stored_codes, list) else []:
                area_code = str(value).strip()
                comparison_key = area_code.casefold()
                if not area_code or comparison_key in seen_area_codes:
                    continue
                seen_area_codes.add(comparison_key)
                aggregate_area_codes.append(area_code)

        aggregate_parts_total = max(declared_totals) if declared_totals else None
        valid_part_numbers = {
            number
            for number in received_part_numbers
            if aggregate_parts_total is None or number <= aggregate_parts_total
        }
        complete = bool(aggregate_parts_total) and set(
            range(1, aggregate_parts_total + 1)
        ).issubset(valid_part_numbers)
        relation_count_row = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM aprs_alert_frames
            WHERE alert_id = ?
            """,
            (canonical_id,),
        ).fetchone()
        relation_count = int(relation_count_row["total"] or 0)
        preserved_frame_count = sum(
            max(1, int(candidate["frame_count"] or 1))
            for candidate in logical_rows
        )
        connection.execute(
            """
            UPDATE aprs_alerts
            SET message = ?,
                expiry = ?,
                expires_at = ?,
                event_code = ?,
                area_code = ?,
                message_id = ?,
                severity_level = ?,
                area_codes_json = ?,
                received_parts = ?,
                parts_total = ?,
                completion_status = ?,
                is_active = ?,
                valid_until_utc = ?,
                first_seen_at = ?,
                last_seen_at = ?,
                frame_count = ?,
                initial_frame_id = ?,
                last_frame_id = ?,
                latitude = ?,
                longitude = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                newest["message"],
                newest["expiry"],
                newest["expires_at"],
                newest["event_code"],
                aggregate_area_codes[0] if aggregate_area_codes else None,
                newest["message_id"],
                newest["severity_level"],
                json.dumps(
                    aggregate_area_codes,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                len(valid_part_numbers),
                aggregate_parts_total,
                "complete" if complete else "incomplete",
                max(int(candidate["is_active"] or 0) for candidate in logical_rows),
                newest["valid_until_utc"],
                min(str(candidate["first_seen_at"]) for candidate in logical_rows),
                max(str(candidate["last_seen_at"]) for candidate in logical_rows),
                max(1, relation_count or preserved_frame_count),
                canonical["initial_frame_id"],
                newest["last_frame_id"],
                newest["latitude"],
                newest["longitude"],
                newest["updated_at"],
                canonical_id,
            ),
        )

    connection.execute("DROP INDEX IF EXISTS idx_aprs_alerts_source_callsign")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_aprs_alerts_source_callsign
        ON aprs_alerts(source_callsign COLLATE NOCASE)
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_aprs_alerts_identity_key
        ON aprs_alerts(identity_key)
        """
    )


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


def _run_database_index_repair_for_update(connection: sqlite3.Connection) -> None:
    try:
        marker = _get_app_setting_on_connection(connection, DATABASE_INDEX_REPAIR_SETTING_KEY)
        if marker == DATABASE_INDEX_REPAIR_VERSION:
            return

        check_messages = _database_check_messages(connection, "quick_check")
        if _database_check_ok(check_messages):
            _set_app_setting_on_connection(
                connection,
                DATABASE_INDEX_REPAIR_SETTING_KEY,
                DATABASE_INDEX_REPAIR_VERSION,
            )
            return

        if not _is_reindex_repairable_check_messages(check_messages):
            _insert_event_log_on_connection(
                connection,
                "WARNING",
                "database",
                "Skipped automatic database index repair; quick_check reported non-index issues: "
                f"{_format_database_check_messages(check_messages)}",
            )
            return

        connection.execute("REINDEX")
        integrity_messages = _database_check_messages(connection, "integrity_check")
        if _database_check_ok(integrity_messages):
            _set_app_setting_on_connection(
                connection,
                DATABASE_INDEX_REPAIR_SETTING_KEY,
                DATABASE_INDEX_REPAIR_VERSION,
            )
            _insert_event_log_on_connection(
                connection,
                "INFO",
                "database",
                "Automatic database index repair completed after quick_check reported index inconsistencies.",
            )
            return

        _insert_event_log_on_connection(
            connection,
            "WARNING",
            "database",
            "Automatic database index repair ran, but integrity_check still reports issues: "
            f"{_format_database_check_messages(integrity_messages)}",
        )
    except sqlite3.DatabaseError as exc:
        message = str(exc).strip() or exc.__class__.__name__
        try:
            connection.rollback()
        except sqlite3.DatabaseError:
            pass
        try:
            _insert_event_log_on_connection(
                connection,
                "WARNING",
                "database",
                f"Automatic database index repair failed: {message}",
            )
        except sqlite3.DatabaseError:
            pass


def _database_check_messages(connection: sqlite3.Connection, pragma_name: str) -> list[str]:
    if pragma_name not in {"quick_check", "integrity_check"}:
        raise ValueError(f"Unsupported database check pragma: {pragma_name}")
    rows = connection.execute(f"PRAGMA {pragma_name}").fetchall()
    return [str(row[0]) for row in rows]


def _database_check_ok(messages: list[str]) -> bool:
    return len(messages) == 1 and messages[0].strip().lower() == "ok"


def _is_reindex_repairable_check_messages(messages: list[str]) -> bool:
    if not messages or _database_check_ok(messages):
        return False
    for message in messages:
        normalized = str(message or "").strip()
        if normalized.startswith("wrong # of entries in index "):
            continue
        if normalized.startswith("row ") and " missing from index " in normalized:
            continue
        return False
    return True


def _format_database_check_messages(messages: list[str], *, max_messages: int = 3) -> str:
    visible_messages = [str(message or "").strip() for message in messages[:max(1, max_messages)]]
    suffix = ""
    if len(messages) > len(visible_messages):
        suffix = f" and {len(messages) - len(visible_messages)} more"
    return "; ".join(visible_messages) + suffix


def _get_app_setting_on_connection(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return str(row["value"])


def _set_app_setting_on_connection(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO app_settings(key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, value, utc_now()),
    )


def _insert_event_log_on_connection(connection: sqlite3.Connection, level: str, category: str, message: str) -> None:
    connection.execute(
        "INSERT INTO event_logs(level, category, message, created_at) VALUES (?, ?, ?, ?)",
        (normalize_event_log_level(level), str(category or "").strip(), str(message or ""), utc_now()),
    )


def _migrate_system_jobs_table(connection: sqlite3.Connection) -> None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'system_jobs' LIMIT 1"
    ).fetchone()
    if exists is None:
        connection.execute(
            """
            CREATE TABLE system_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'success', 'error')),
                message TEXT NOT NULL DEFAULT '',
                progress_percent INTEGER NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),
                stage TEXT NOT NULL DEFAULT '',
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
    else:
        columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(system_jobs)").fetchall()}
        if "progress_percent" not in columns:
            connection.execute(
                "ALTER TABLE system_jobs ADD COLUMN progress_percent INTEGER NOT NULL DEFAULT 0 "
                "CHECK (progress_percent BETWEEN 0 AND 100)"
            )
        if "stage" not in columns:
            connection.execute("ALTER TABLE system_jobs ADD COLUMN stage TEXT NOT NULL DEFAULT ''")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_system_jobs_created_at ON system_jobs(created_at DESC, id DESC)")


def _ensure_activation_schedule_columns(connection: sqlite3.Connection, table_name: str) -> None:
    columns = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}
    definitions = {
        "activation_mode": "TEXT NOT NULL DEFAULT 'manual' CHECK (activation_mode IN ('manual', 'scheduled', 'recurring'))",
        "active_from_utc": "TEXT",
        "active_until_utc": "TEXT",
        "first_activation_utc": "TEXT",
        "recurrence_duration_minutes": "INTEGER",
        "recurrence_interval_value": "INTEGER",
        "recurrence_interval_unit": "TEXT",
        "recurrence_until_utc": "TEXT",
    }
    for column_name, definition in definitions.items():
        if column_name in columns:
            continue
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _migrate_entity_interval_constraints(connection: sqlite3.Connection) -> None:
    objects_sql = _table_sql(connection, "aprs_objects")
    if objects_sql and "interval_minutes IN (5, 10, 15, 30, 45, 60)" not in objects_sql:
        object_columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(aprs_objects)").fetchall()}
        object_overlay_select = "symbol_overlay" if "symbol_overlay" in object_columns else "NULL"
        object_valid_until_select = "valid_until_utc" if "valid_until_utc" in object_columns else "NULL"
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
            INSERT INTO aprs_objects (
                id, name, lifetime, state, is_enabled, interval_minutes, valid_until_utc, latitude, longitude, symbol_table, symbol_code, symbol_overlay, path, comment, updated_at
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
                {object_valid_until_select},
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
        item_valid_until_select = "valid_until_utc" if "valid_until_utc" in item_columns else "NULL"
        connection.executescript(
            f"""
            ALTER TABLE aprs_items RENAME TO aprs_items_old;
            CREATE TABLE aprs_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
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
            INSERT INTO aprs_items (
                id, name, state, is_enabled, interval_minutes, valid_until_utc, latitude, longitude, symbol_table, symbol_code, symbol_overlay, path, comment, updated_at
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
                {item_valid_until_select},
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
        CREATE INDEX IF NOT EXISTS idx_aprs_messages_direction_status_last_attempt_at
            ON aprs_messages(direction, status, last_attempt_at, id);
        CREATE INDEX IF NOT EXISTS idx_aprs_messages_direction_unread_conversation
            ON aprs_messages(direction, is_unread, conversation_id);
        """
    )


def _migrate_bulletin_table(connection: sqlite3.Connection) -> None:
    bulletins_sql = _table_sql(connection, "bulletins")
    bulletin_columns = {row["name"] for row in connection.execute("PRAGMA table_info(bulletins)").fetchall()}
    bulletin_valid_until_select = "valid_until_utc" if "valid_until_utc" in bulletin_columns else "NULL"
    if bulletins_sql and "message_kind" not in bulletins_sql:
        connection.executescript(
            f"""
            ALTER TABLE bulletins RENAME TO bulletins_old;
            CREATE TABLE bulletins (
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
            INSERT INTO bulletins (
                id, message_kind, addressee, bulletin_code, group_name, is_enabled, interval_minutes, valid_until_utc, path, message_text, updated_at
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
                {bulletin_valid_until_select},
                NULL,
                SUBSTR(COALESCE(body, ''), 1, 67),
                updated_at
            FROM bulletins_old;
            DROP TABLE bulletins_old;
            """
        )
    elif bulletins_sql and "path" not in bulletin_columns:
        connection.executescript(
            f"""
            ALTER TABLE bulletins RENAME TO bulletins_old;
            CREATE TABLE bulletins (
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
            INSERT INTO bulletins (
                id, message_kind, addressee, bulletin_code, group_name, is_enabled, interval_minutes, valid_until_utc, path, message_text, updated_at
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
                {bulletin_valid_until_select},
                NULL,
                SUBSTR(COALESCE(message_text, ''), 1, 67),
                updated_at
            FROM bulletins_old;
            DROP TABLE bulletins_old;
            """
        )
    elif bulletins_sql and "message_kind IN ('bulletin', 'announcement', 'group_bulletin')" not in bulletins_sql:
        connection.executescript(
            f"""
            ALTER TABLE bulletins RENAME TO bulletins_old;
            CREATE TABLE bulletins (
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
            INSERT INTO bulletins (
                id, message_kind, addressee, bulletin_code, group_name, is_enabled, interval_minutes, valid_until_utc, path, message_text, updated_at
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
                {bulletin_valid_until_select},
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
        "filter_rf_guard",
        "filter_aprsis_message_delivery",
        "filter_rf_tx_guard",
        "filter_allow_rules",
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
                'filter_rf_guard',
                'filter_aprsis_message_delivery',
                'filter_rf_tx_guard',
                'filter_allow_rules',
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


def _migrate_aprsis_rf_guard_steps(connection: sqlite3.Connection) -> None:
    rows = list(
        connection.execute(
            """
            SELECT id, source_kind, target_kind
            FROM digi_flows
            WHERE source_kind = 'receiver_aprsis'
            """
        ).fetchall()
    )
    for flow in rows:
        flow_id = int(flow["id"])
        steps = list(
            connection.execute(
                """
                SELECT id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                FROM digi_flow_steps
                WHERE flow_id = ?
                ORDER BY step_order ASC, id ASC
                """,
                (flow_id,),
            ).fetchall()
        )
        if len(steps) < 2:
            continue

        input_guard = next((step for step in steps if step["step_type"] == "filter_rf_guard"), None)
        message_delivery = next(
            (step for step in steps if step["step_type"] == "filter_aprsis_message_delivery"),
            None,
        )
        allow_rule = next(
            (step for step in steps if step["step_type"] == "filter_allow_rules"),
            None,
        )
        output_guard = next((step for step in steps if step["step_type"] == "filter_rf_tx_guard"), None)
        target_step = next(
            (
                step
                for step in reversed(steps)
                if step["step_type"] == str(flow["target_kind"] or "")
            ),
            steps[-1],
        )
        changed = False
        timestamp = utc_now()

        if input_guard is None:
            source_step = steps[0]
            connection.execute(
                "UPDATE digi_flow_steps SET step_order = step_order + 1000 WHERE flow_id = ? AND step_order > ?",
                (flow_id, int(source_step["step_order"])),
            )
            connection.execute(
                """
                INSERT INTO digi_flow_steps(
                    flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                )
                VALUES (?, ?, 'filter_rf_guard', 'APRS-IS Input Safety Rule', 1, '{}', ?, ?)
                """,
                (flow_id, int(source_step["step_order"]) + 1, timestamp, timestamp),
            )
            changed = True
        else:
            legacy_config = str(input_guard["config_json"] or "{}")
            input_changed = (
                str(input_guard["title"] or "") != "APRS-IS Input Safety Rule"
                or int(input_guard["enabled"] or 0) != 1
                or legacy_config.strip() != "{}"
            )
            if input_changed:
                connection.execute(
                    """
                    UPDATE digi_flow_steps
                    SET title = 'APRS-IS Input Safety Rule', enabled = 1, config_json = '{}', updated_at = ?
                    WHERE id = ?
                    """,
                    (timestamp, int(input_guard["id"])),
                )
                changed = True

        if str(flow["target_kind"] or "") == "tx_rf" and output_guard is None:
            guard_config = (
                str(input_guard["config_json"] or "{}")
                if input_guard is not None and str(input_guard["config_json"] or "").strip() not in {"", "{}"}
                else (
                    '{"viscous_delay_sec":5,"flow_rate_per_minute":6,"flow_burst":3,'
                    '"source_rate_per_minute":2,"source_burst":2,"duplicate_window_sec":30}'
                )
            )
            target_order = int(target_step["step_order"])
            connection.execute(
                "UPDATE digi_flow_steps SET step_order = ? WHERE id = ?",
                (target_order + 1000, int(target_step["id"])),
            )
            connection.execute(
                """
                INSERT INTO digi_flow_steps(
                    flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                )
                VALUES (?, ?, 'filter_rf_tx_guard', 'APRS-IS to RF TX Safety Rule', 1, ?, ?, ?)
                """,
                (flow_id, target_order, guard_config, timestamp, timestamp),
            )
            changed = True
        elif output_guard is not None:
            output_changed = (
                str(output_guard["title"] or "") != "APRS-IS to RF TX Safety Rule"
                or int(output_guard["enabled"] or 0) != 1
            )
            if output_changed:
                connection.execute(
                    """
                    UPDATE digi_flow_steps
                    SET title = 'APRS-IS to RF TX Safety Rule', enabled = 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (timestamp, int(output_guard["id"])),
                )
                changed = True

        if str(flow["target_kind"] or "") == "tx_rf" and message_delivery is None:
            connection.execute(
                """
                INSERT INTO digi_flow_steps(
                    flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                )
                VALUES (
                    ?,
                    (SELECT COALESCE(MAX(step_order), 0) + 1000 FROM digi_flow_steps WHERE flow_id = ?),
                    'filter_aprsis_message_delivery',
                    'APRS-IS Message Delivery Rule', 1, '{}',
                    ?, ?
                )
                """,
                (flow_id, flow_id, timestamp, timestamp),
            )
            changed = True
        elif message_delivery is not None:
            message_changed = (
                str(message_delivery["title"] or "") != "APRS-IS Message Delivery Rule"
                or int(message_delivery["enabled"] or 0) != 1
                or str(message_delivery["config_json"] or "").strip() != "{}"
            )
            if message_changed:
                connection.execute(
                    """
                    UPDATE digi_flow_steps
                    SET title = 'APRS-IS Message Delivery Rule',
                        enabled = 1,
                        config_json = '{}',
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (timestamp, int(message_delivery["id"])),
                )
                changed = True

        if str(flow["target_kind"] or "") == "tx_rf" and allow_rule is None:
            connection.execute(
                """
                INSERT INTO digi_flow_steps(
                    flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                )
                VALUES (
                    ?,
                    (SELECT COALESCE(MAX(step_order), 0) + 1000 FROM digi_flow_steps WHERE flow_id = ?),
                    'filter_allow_rules',
                    'APRS-IS Callsign and Radius Rule', 1,
                    '{"callsigns":[],"radius_km":""}',
                    ?, ?
                )
                """,
                (flow_id, flow_id, timestamp, timestamp),
            )
            changed = True
        elif allow_rule is not None:
            allow_changed = (
                str(allow_rule["title"] or "") != "APRS-IS Callsign and Radius Rule"
                or int(allow_rule["enabled"] or 0) != 1
            )
            if allow_changed:
                connection.execute(
                    """
                    UPDATE digi_flow_steps
                    SET title = 'APRS-IS Callsign and Radius Rule', enabled = 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (timestamp, int(allow_rule["id"])),
                )
                changed = True

        if input_guard is not None and int(steps[1]["id"]) != int(input_guard["id"]):
            changed = True
        if str(flow["target_kind"] or "") == "tx_rf":
            system_order = [
                str(step["step_type"] or "")
                for step in steps[1:-1]
                if str(step["step_type"] or "")
                in {
                    "filter_rf_guard",
                    "filter_aprsis_message_delivery",
                    "filter_allow_rules",
                    "filter_rf_tx_guard",
                }
            ]
            if system_order != [
                "filter_rf_guard",
                "filter_aprsis_message_delivery",
                "filter_allow_rules",
                "filter_rf_tx_guard",
            ]:
                changed = True
        if (
            str(flow["target_kind"] or "") == "tx_rf"
            and output_guard is not None
            and int(steps[-2]["id"]) != int(output_guard["id"])
        ):
            changed = True

        if not changed:
            continue

        reordered = list(
            connection.execute(
                """
                SELECT id, step_type
                FROM digi_flow_steps
                WHERE flow_id = ?
                ORDER BY step_order ASC, id ASC
                """,
                (flow_id,),
            ).fetchall()
        )
        source = next(
            (step for step in reordered if step["step_type"] == str(flow["source_kind"] or "")),
            reordered[0],
        )
        target = next(
            (
                step
                for step in reversed(reordered)
                if step["step_type"] == str(flow["target_kind"] or "")
            ),
            reordered[-1],
        )
        endpoint_ids = {int(source["id"]), int(target["id"])}
        middle = [step for step in reordered if int(step["id"]) not in endpoint_ids]
        input_steps = [step for step in middle if step["step_type"] == "filter_rf_guard"]
        message_steps = [
            step for step in middle if step["step_type"] == "filter_aprsis_message_delivery"
        ]
        allow_steps = [step for step in middle if step["step_type"] == "filter_allow_rules"]
        output_steps = [step for step in middle if step["step_type"] == "filter_rf_tx_guard"]
        ordinary_steps = [
            step
            for step in middle
            if step["step_type"]
            not in {
                "filter_rf_guard",
                "filter_aprsis_message_delivery",
                "filter_allow_rules",
                "filter_rf_tx_guard",
            }
        ]
        ordered = [
            source,
            *input_steps,
            *message_steps,
            *allow_steps,
            *ordinary_steps,
            *output_steps,
            target,
        ]
        connection.execute(
            "UPDATE digi_flow_steps SET step_order = -id WHERE flow_id = ?",
            (flow_id,),
        )
        for step_order, step in enumerate(ordered, start=1):
            connection.execute(
                "UPDATE digi_flow_steps SET step_order = ?, updated_at = ? WHERE id = ?",
                (step_order, timestamp, int(step["id"])),
            )
        connection.execute(
            "UPDATE digi_flows SET updated_at = ? WHERE id = ?",
            (timestamp, flow_id),
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


def _migrate_aprsis_rf_stats_table(connection: sqlite3.Connection) -> None:
    stats_sql = _table_sql(connection, "aprsis_rf_stats")
    if not stats_sql:
        return
    stats_columns = {
        str(row["name"] or "")
        for row in connection.execute("PRAGMA table_info(aprsis_rf_stats)").fetchall()
    }
    for column in (
        "matched_message_rule",
        "matched_associated_position",
        "dropped_recipient_not_local",
        "dropped_recipient_seen_internet",
        "dropped_sender_heard_rf",
    ):
        if column not in stats_columns:
            connection.execute(
                f"ALTER TABLE aprsis_rf_stats ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
            )
    foreign_keys = list(connection.execute("PRAGMA foreign_key_list(aprsis_rf_stats)").fetchall())
    if not any(str(row["table"] or "") == "digi_flows_old" for row in foreign_keys):
        return
    connection.executescript(
        """
        ALTER TABLE aprsis_rf_stats RENAME TO aprsis_rf_stats_old;
        CREATE TABLE aprsis_rf_stats (
            flow_id INTEGER PRIMARY KEY,
            received_from_aprsis INTEGER NOT NULL DEFAULT 0,
            matched_message_rule INTEGER NOT NULL DEFAULT 0,
            matched_associated_position INTEGER NOT NULL DEFAULT 0,
            matched_allow_rule INTEGER NOT NULL DEFAULT 0,
            dropped_no_allow_rule INTEGER NOT NULL DEFAULT 0,
            dropped_recipient_not_local INTEGER NOT NULL DEFAULT 0,
            dropped_recipient_seen_internet INTEGER NOT NULL DEFAULT 0,
            dropped_sender_heard_rf INTEGER NOT NULL DEFAULT 0,
            dropped_safety_guard INTEGER NOT NULL DEFAULT 0,
            dropped_duplicate INTEGER NOT NULL DEFAULT 0,
            cancelled_during_viscous_delay INTEGER NOT NULL DEFAULT 0,
            dropped_rate_limit INTEGER NOT NULL DEFAULT 0,
            dropped_oversize INTEGER NOT NULL DEFAULT 0,
            queued_to_rf INTEGER NOT NULL DEFAULT 0,
            transmitted_to_rf INTEGER NOT NULL DEFAULT 0,
            tx_failed INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (flow_id) REFERENCES digi_flows(id) ON DELETE CASCADE
        );
        INSERT INTO aprsis_rf_stats (
            flow_id, received_from_aprsis, matched_message_rule, matched_associated_position,
            matched_allow_rule, dropped_no_allow_rule, dropped_recipient_not_local,
            dropped_recipient_seen_internet, dropped_sender_heard_rf,
            dropped_safety_guard, dropped_duplicate, cancelled_during_viscous_delay,
            dropped_rate_limit, dropped_oversize, queued_to_rf, transmitted_to_rf,
            tx_failed, updated_at
        )
        SELECT
            flow_id, received_from_aprsis, matched_message_rule, matched_associated_position,
            matched_allow_rule, dropped_no_allow_rule, dropped_recipient_not_local,
            dropped_recipient_seen_internet, dropped_sender_heard_rf,
            dropped_safety_guard, dropped_duplicate, cancelled_during_viscous_delay,
            dropped_rate_limit, dropped_oversize, queued_to_rf, transmitted_to_rf,
            tx_failed, updated_at
        FROM aprsis_rf_stats_old;
        DROP TABLE aprsis_rf_stats_old;
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
    stats_fk = list(connection.execute("PRAGMA foreign_key_list(aprsis_rf_stats)").fetchall())
    if any(str(row["table"] or "") == "digi_flows_old" for row in step_fk + event_log_fk + stats_fk):
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
            INSERT INTO system_jobs(
                kind, status, message, progress_percent, stage, log_file, created_at, updated_at
            )
            VALUES (?, 'queued', ?, 0, 'queued', ?, ?, ?)
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
                message = CASE WHEN status = 'queued' THEN ? ELSE message END,
                progress_percent = MAX(progress_percent, 1),
                stage = CASE WHEN status = 'queued' THEN 'starting' ELSE stage END,
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
                stage = 'failed',
                finished_at = COALESCE(finished_at, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (str(message or ""), now, now, int(job_id)),
        )


def mark_unreported_system_job_error(
    job_id: int,
    *,
    message: str,
    stale_after_seconds: int = 60,
) -> bool:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    cutoff = (now - timedelta(seconds=max(1, int(stale_after_seconds)))).isoformat()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE system_jobs
            SET status = 'error',
                message = ?,
                stage = 'failed',
                finished_at = COALESCE(finished_at, ?),
                updated_at = ?
            WHERE id = ?
              AND kind IN ('update-application', 'restart-services')
              AND status = 'running'
              AND progress_percent <= 1
              AND datetime(updated_at) <= datetime(?)
            """,
            (str(message or ""), now.isoformat(), now.isoformat(), int(job_id), cutoff),
        )
        return int(cursor.rowcount or 0) > 0


def fetch_system_job(job_id: int) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT
            id, kind, status, message, progress_percent, stage, log_file, pid, exit_code,
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


def normalize_traffic_retention_minutes(value: Any) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TRAFFIC_RETENTION_MINUTES
    if normalized in TRAFFIC_RETENTION_ALLOWED_MINUTES:
        return normalized
    return DEFAULT_TRAFFIC_RETENTION_MINUTES


def get_traffic_retention_minutes() -> int:
    return normalize_traffic_retention_minutes(get_app_setting(TRAFFIC_RETENTION_MINUTES_SETTING_KEY))


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


def prune_traffic_frames_batch(*, limit: int = 1000) -> int:
    normalized_limit = max(1, int(limit))
    cutoff = traffic_retention_cutoff()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM traffic_frames
            WHERE id IN (
                SELECT id
                FROM (
                    SELECT id
                    FROM traffic_frames
                    WHERE created_at < ?
                    ORDER BY created_at ASC, id ASC
                    LIMIT ?
                )
            )
            """,
            (cutoff, normalized_limit),
        )
        deleted = cursor.rowcount
    return max(int(deleted or 0), 0)


def prune_outbound_jobs_batch(
    *,
    limit: int = DEFAULT_OUTBOUND_JOB_PRUNE_BATCH_SIZE,
    sent_retention_days: int = DEFAULT_OUTBOUND_SENT_RETENTION_DAYS,
    failure_retention_days: int = DEFAULT_OUTBOUND_FAILURE_RETENTION_DAYS,
    min_rows_per_group: int = DEFAULT_OUTBOUND_RETENTION_MIN_ROWS_PER_GROUP,
) -> int:
    normalized_limit = max(1, int(limit))
    normalized_min_rows = max(0, int(min_rows_per_group))
    sent_cutoff = _retention_cutoff_days(sent_retention_days)
    failure_cutoff = _retention_cutoff_days(failure_retention_days)
    deleted_total = 0

    with get_connection() as connection:
        for kind in OUTBOUND_RETENTION_KINDS:
            remaining_limit = normalized_limit - deleted_total
            if remaining_limit <= 0:
                break
            deleted_total += _delete_outbound_jobs_for_policy(
                connection,
                kind=kind,
                status="sent",
                cutoff=sent_cutoff,
                keep_rows=normalized_min_rows,
                limit=remaining_limit,
            )

        for status in OUTBOUND_RETENTION_FAILURE_STATUSES:
            for kind in OUTBOUND_RETENTION_KINDS:
                remaining_limit = normalized_limit - deleted_total
                if remaining_limit <= 0:
                    break
                deleted_total += _delete_outbound_jobs_for_policy(
                    connection,
                    kind=kind,
                    status=status,
                    cutoff=failure_cutoff,
                    keep_rows=normalized_min_rows,
                    limit=remaining_limit,
                )
            if deleted_total >= normalized_limit:
                break

    return deleted_total


def _delete_outbound_jobs_for_policy(
    connection: sqlite3.Connection,
    *,
    kind: str,
    status: str,
    cutoff: str,
    keep_rows: int,
    limit: int,
) -> int:
    cursor = connection.execute(
        """
        DELETE FROM outbound_jobs
        WHERE id IN (
            SELECT id
            FROM (
                SELECT id
                FROM outbound_jobs
                WHERE kind = ?
                  AND status = ?
                  AND aprs_message_id IS NULL
                  AND COALESCE(sent_at, updated_at, started_at, scheduled_at, created_at) < ?
                  AND id NOT IN (
                      SELECT id
                      FROM outbound_jobs
                      WHERE kind = ?
                        AND status = ?
                        AND aprs_message_id IS NULL
                      ORDER BY COALESCE(sent_at, updated_at, started_at, scheduled_at, created_at) DESC, id DESC
                      LIMIT ?
                  )
                ORDER BY COALESCE(sent_at, updated_at, started_at, scheduled_at, created_at) ASC, id ASC
                LIMIT ?
            )
        )
        """,
        (kind, status, cutoff, kind, status, keep_rows, limit),
    )
    return max(int(cursor.rowcount or 0), 0)


def _retention_cutoff_days(days: int) -> str:
    normalized_days = max(1, int(days))
    return (datetime.now(timezone.utc) - timedelta(days=normalized_days)).replace(microsecond=0).isoformat()


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
    retention_minutes = get_traffic_retention_minutes()
    return (datetime.now(timezone.utc) - timedelta(minutes=retention_minutes)).replace(microsecond=0).isoformat()
