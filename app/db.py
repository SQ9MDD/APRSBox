from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import settings

DEFAULT_EVENT_LOG_KEEP_ROWS = 5000


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

CREATE TABLE IF NOT EXISTS modems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    modem_type TEXT NOT NULL,
    band TEXT NOT NULL DEFAULT '',
    device_path TEXT,
    baud_rate INTEGER,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    expose_port_enabled INTEGER NOT NULL DEFAULT 0 CHECK (expose_port_enabled IN (0, 1)),
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
    beacon_comment TEXT,
    beacon_interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (beacon_interval_minutes IN (15, 30, 45, 60)),
    beacon_path TEXT,
    status_enabled INTEGER NOT NULL DEFAULT 0 CHECK (status_enabled IN (0, 1)),
    status_text TEXT,
    status_interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (status_interval_minutes IN (15, 30, 45, 60)),
    latitude TEXT,
    longitude TEXT,
    symbol_table TEXT,
    symbol_code TEXT,
    default_units TEXT NOT NULL DEFAULT 'metric' CHECK (default_units IN ('metric', 'imperial')),
    tx_enabled INTEGER NOT NULL DEFAULT 0 CHECK (tx_enabled IN (0, 1)),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wx_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    callsign TEXT NOT NULL DEFAULT '',
    ssid TEXT NOT NULL DEFAULT '',
    refresh_interval_s INTEGER NOT NULL DEFAULT 300 CHECK (refresh_interval_s BETWEEN 15 AND 3600),
    allow_cache_fallback INTEGER NOT NULL DEFAULT 1 CHECK (allow_cache_fallback IN (0, 1)),
    default_cache_max_age_s INTEGER NOT NULL DEFAULT 900 CHECK (default_cache_max_age_s BETWEEN 1 AND 86400),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
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
    status TEXT NOT NULL CHECK (status IN ('queued', 'sent', 'acked', 'failed', 'received')),
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
    source_kind TEXT NOT NULL CHECK (source_kind IN ('receiver_rf', 'receiver_aprsis')),
    source_ref TEXT NOT NULL,
    target_kind TEXT NOT NULL CHECK (target_kind IN ('tx_rf', 'tx_aprsis', 'action_drop', 'action_log')),
    target_ref TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (source_kind, source_ref, target_kind, target_ref)
);

CREATE TABLE IF NOT EXISTS digi_flow_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flow_id INTEGER NOT NULL,
    step_order INTEGER NOT NULL,
    step_type TEXT NOT NULL CHECK (step_type IN (
        'receiver_rf',
        'receiver_aprsis',
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
    latitude TEXT,
    longitude TEXT,
    symbol_table TEXT,
    symbol_code TEXT,
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

CREATE INDEX IF NOT EXISTS idx_event_logs_created_at ON event_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_traffic_frames_created_at ON traffic_frames(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_traffic_frames_format_created_at ON traffic_frames(format, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_traffic_runtime_interfaces_status_updated_at ON traffic_runtime_interfaces(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_digi_flow_event_log_flow_created_at ON digi_flow_event_log(flow_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_digi_flow_event_log_frame_uid ON digi_flow_event_log(frame_uid);
CREATE INDEX IF NOT EXISTS idx_outbound_jobs_status_scheduled_at ON outbound_jobs(status, scheduled_at, id);
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
"""


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(SCHEMA)
        _migrate_entity_interval_constraints(connection)
        _migrate_bulletin_table(connection)
        _migrate_digi_flow_steps_table(connection)
        _migrate_digi_flow_event_log_table(connection)
        station_columns = {row["name"] for row in connection.execute("PRAGMA table_info(station_settings)").fetchall()}
        user_columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()}
        modem_columns = {row["name"] for row in connection.execute("PRAGMA table_info(modems)").fetchall()}
        object_columns = {row["name"] for row in connection.execute("PRAGMA table_info(aprs_objects)").fetchall()}
        item_columns = {row["name"] for row in connection.execute("PRAGMA table_info(aprs_items)").fetchall()}
        outbound_columns = {row["name"] for row in connection.execute("PRAGMA table_info(outbound_jobs)").fetchall()}
        traffic_frame_columns = {row["name"] for row in connection.execute("PRAGMA table_info(traffic_frames)").fetchall()}
        traffic_runtime_columns = {row["name"] for row in connection.execute("PRAGMA table_info(traffic_runtime_state)").fetchall()}
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
        if "band" not in modem_columns:
            connection.execute(
                """
                ALTER TABLE modems
                ADD COLUMN band TEXT NOT NULL DEFAULT ''
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
        if "aprs_message_id" not in outbound_columns:
            connection.execute(
                """
                ALTER TABLE outbound_jobs
                ADD COLUMN aprs_message_id INTEGER
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
        connection.execute(
            """
CREATE INDEX IF NOT EXISTS idx_outbound_jobs_aprs_message_id
    ON outbound_jobs(aprs_message_id, status, scheduled_at, id)
"""
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
        connection.execute(
            """
            INSERT INTO station_settings (
                id, callsign, ssid, beacon_interface_id, beacon_comment, beacon_interval_minutes, beacon_path,
                status_enabled, status_text, status_interval_minutes, latitude, longitude,
                symbol_table, symbol_code, default_units, tx_enabled, updated_at
            )
            VALUES (1, '', '', NULL, '', 30, '', 0, '', 30, '', '', '/', '>', 'metric', 0, ?)
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
                id, enabled, callsign, ssid, refresh_interval_s,
                allow_cache_fallback, default_cache_max_age_s, created_at, updated_at
            )
            VALUES (1, 0, '', '', 300, 1, 900, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (utc_now(), utc_now()),
        )


def _migrate_entity_interval_constraints(connection: sqlite3.Connection) -> None:
    objects_sql = _table_sql(connection, "aprs_objects")
    if objects_sql and "interval_minutes IN (5, 10, 15, 30, 45, 60)" not in objects_sql:
        connection.executescript(
            """
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
                path TEXT,
                comment TEXT,
                updated_at TEXT NOT NULL
            );
            INSERT INTO aprs_objects (
                id, name, lifetime, state, is_enabled, interval_minutes, latitude, longitude, symbol_table, symbol_code, path, comment, updated_at
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
                path,
                comment,
                updated_at
            FROM aprs_objects_old;
            DROP TABLE aprs_objects_old;
            """
        )
    items_sql = _table_sql(connection, "aprs_items")
    if items_sql and "interval_minutes IN (5, 10, 15, 30, 45, 60)" not in items_sql:
        connection.executescript(
            """
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
                path TEXT,
                comment TEXT,
                updated_at TEXT NOT NULL
            );
            INSERT INTO aprs_items (
                id, name, state, is_enabled, interval_minutes, latitude, longitude, symbol_table, symbol_code, path, comment, updated_at
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
                path,
                comment,
                updated_at
            FROM aprs_items_old;
            DROP TABLE aprs_items_old;
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


def _migrate_digi_flow_steps_table(connection: sqlite3.Connection) -> None:
    steps_sql = _table_sql(connection, "digi_flow_steps")
    if not steps_sql:
        return
    required_step_types = (
        "filter_direct_only",
        "filter_digi",
        "filter_icon",
        "filter_rate_limit_per_callsign",
        "filter_strict",
    )
    if all(step_type in steps_sql for step_type in required_step_types):
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
    if not any(str(row["table"] or "") == "digi_flow_steps_old" for row in foreign_keys):
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


def get_app_setting(key: str) -> str | None:
    row = fetch_one("SELECT value FROM app_settings WHERE key = ?", (key,))
    if row is None:
        return None
    return str(row["value"])


def set_app_setting(key: str, value: str) -> None:
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


def log_event(level: str, category: str, message: str) -> None:
    execute(
        "INSERT INTO event_logs(level, category, message, created_at) VALUES (?, ?, ?, ?)",
        (level, category, message, utc_now()),
    )


def traffic_retention_cutoff() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat()
