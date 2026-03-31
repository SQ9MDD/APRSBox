from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import settings


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
    latitude TEXT,
    longitude TEXT,
    symbol_table TEXT,
    symbol_code TEXT,
    default_units TEXT NOT NULL DEFAULT 'metric' CHECK (default_units IN ('metric', 'imperial')),
    tx_enabled INTEGER NOT NULL DEFAULT 0 CHECK (tx_enabled IN (0, 1)),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbound_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    interface_id INTEGER,
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

CREATE TABLE IF NOT EXISTS aprs_objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0, 1)),
    latitude TEXT,
    longitude TEXT,
    symbol_table TEXT,
    symbol_code TEXT,
    comment TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aprs_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0, 1)),
    latitude TEXT,
    longitude TEXT,
    symbol_table TEXT,
    symbol_code TEXT,
    comment TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bulletins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0, 1)),
    body TEXT NOT NULL,
    cadence_minutes INTEGER,
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
    last_error TEXT,
    updated_at TEXT NOT NULL
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
CREATE INDEX IF NOT EXISTS idx_outbound_jobs_status_scheduled_at ON outbound_jobs(status, scheduled_at, id);
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
        station_columns = {row["name"] for row in connection.execute("PRAGMA table_info(station_settings)").fetchall()}
        user_columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()}
        modem_columns = {row["name"] for row in connection.execute("PRAGMA table_info(modems)").fetchall()}
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
        connection.execute(
            """
            INSERT INTO station_settings (
                id, callsign, ssid, beacon_interface_id, beacon_comment, beacon_interval_minutes, beacon_path, latitude, longitude,
                symbol_table, symbol_code, default_units, tx_enabled, updated_at
            )
            VALUES (1, '', '', NULL, '', 30, '', '', '', '/', '>', 'metric', 0, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (utc_now(),),
        )
        connection.execute(
            """
            INSERT INTO traffic_runtime_state (
                id, status, status_detail, active_modem_name, active_modem_endpoint, last_error, updated_at
            )
            VALUES (1, 'idle', 'Traffic monitor is starting.', NULL, NULL, NULL, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (utc_now(),),
        )


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


def log_event(level: str, category: str, message: str) -> None:
    execute(
        "INSERT INTO event_logs(level, category, message, created_at) VALUES (?, ?, ?, ?)",
        (level, category, message, utc_now()),
    )


def traffic_retention_cutoff() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat()
