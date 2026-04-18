import contextlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db import connect, init_db


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        try:
            yield database_path
        finally:
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


class TrafficSchemaMigrationTests(unittest.TestCase):
    def test_init_db_migrates_legacy_traffic_frames_before_creating_interface_index(self) -> None:
        with temporary_database() as database_path:
            connection = sqlite3.connect(database_path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE app_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE modems (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        modem_type TEXT NOT NULL,
                        device_path TEXT,
                        baud_rate INTEGER,
                        enabled INTEGER NOT NULL DEFAULT 0,
                        notes TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE aprsis_servers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        host TEXT NOT NULL,
                        port INTEGER NOT NULL,
                        use_tls INTEGER NOT NULL DEFAULT 0,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        notes TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE station_settings (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        callsign TEXT,
                        ssid TEXT,
                        beacon_comment TEXT,
                        latitude TEXT,
                        longitude TEXT,
                        symbol_table TEXT,
                        symbol_code TEXT,
                        tx_enabled INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE outbound_jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        kind TEXT NOT NULL,
                        interface_id INTEGER,
                        payload_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        scheduled_at TEXT NOT NULL,
                        locked_at TEXT,
                        started_at TEXT,
                        sent_at TEXT,
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        last_error TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE aprs_objects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        lifetime TEXT NOT NULL DEFAULT 'temporary',
                        state TEXT NOT NULL DEFAULT 'live',
                        is_enabled INTEGER NOT NULL DEFAULT 0,
                        interval_minutes INTEGER NOT NULL DEFAULT 30,
                        latitude TEXT,
                        longitude TEXT,
                        symbol_table TEXT,
                        symbol_code TEXT,
                        path TEXT,
                        comment TEXT,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE aprs_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        state TEXT NOT NULL DEFAULT 'live',
                        is_enabled INTEGER NOT NULL DEFAULT 0,
                        interval_minutes INTEGER NOT NULL DEFAULT 30,
                        latitude TEXT,
                        longitude TEXT,
                        symbol_table TEXT,
                        symbol_code TEXT,
                        path TEXT,
                        comment TEXT,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE bulletins (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_kind TEXT NOT NULL DEFAULT 'bulletin',
                        addressee TEXT,
                        bulletin_code TEXT,
                        group_name TEXT,
                        is_enabled INTEGER NOT NULL DEFAULT 0,
                        interval_minutes INTEGER NOT NULL DEFAULT 30,
                        path TEXT,
                        message_text TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE digi_flows (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT NOT NULL DEFAULT '',
                        source_kind TEXT NOT NULL,
                        source_ref TEXT NOT NULL,
                        target_kind TEXT NOT NULL,
                        target_ref TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE (source_kind, source_ref, target_kind, target_ref)
                    );
                    CREATE TABLE digi_flow_steps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        flow_id INTEGER NOT NULL,
                        step_order INTEGER NOT NULL,
                        step_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        config_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (flow_id) REFERENCES digi_flows(id) ON DELETE CASCADE,
                        UNIQUE (flow_id, step_order)
                    );
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
                        FOREIGN KEY (step_id) REFERENCES digi_flow_steps(id) ON DELETE CASCADE
                    );
                    CREATE TABLE aprs_message_conversations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        remote_callsign TEXT NOT NULL,
                        remote_ssid TEXT NOT NULL DEFAULT '',
                        path TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE (remote_callsign, remote_ssid)
                    );
                    CREATE TABLE aprs_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id INTEGER NOT NULL,
                        direction TEXT NOT NULL,
                        sender TEXT NOT NULL,
                        addressee TEXT NOT NULL,
                        path TEXT NOT NULL DEFAULT '',
                        message_text TEXT NOT NULL,
                        message_number TEXT,
                        status TEXT NOT NULL DEFAULT 'queued',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (conversation_id) REFERENCES aprs_message_conversations(id) ON DELETE CASCADE
                    );
                    CREATE TABLE event_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        level TEXT NOT NULL,
                        category TEXT NOT NULL,
                        message TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE traffic_frames (
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
                    CREATE TABLE traffic_runtime_state (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        status TEXT NOT NULL,
                        status_detail TEXT NOT NULL,
                        active_modem_name TEXT,
                        active_modem_endpoint TEXT,
                        last_error TEXT,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE band_condition_reference_stations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        band TEXT NOT NULL,
                        callsign TEXT NOT NULL,
                        ssid TEXT NOT NULL DEFAULT '',
                        station_type TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        weight REAL NOT NULL DEFAULT 1.0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE (band, callsign, ssid)
                    );
                    CREATE TABLE band_condition_audibility_buckets (
                        bucket_start_utc TEXT NOT NULL,
                        band TEXT NOT NULL,
                        station_key TEXT NOT NULL,
                        heard_flag INTEGER NOT NULL DEFAULT 0,
                        frame_count INTEGER NOT NULL DEFAULT 0,
                        baseline_processed_at TEXT,
                        PRIMARY KEY (bucket_start_utc, band, station_key)
                    );
                    CREATE TABLE band_condition_activity_station_buckets (
                        bucket_start_utc TEXT NOT NULL,
                        band TEXT NOT NULL,
                        station_key TEXT NOT NULL,
                        is_mobile INTEGER NOT NULL DEFAULT 0,
                        is_fixed INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (bucket_start_utc, band, station_key)
                    );
                    CREATE TABLE band_condition_activity_buckets (
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
                    CREATE TABLE band_condition_audibility_baseline (
                        band TEXT NOT NULL,
                        station_key TEXT NOT NULL,
                        hour_of_day INTEGER NOT NULL,
                        sample_count INTEGER NOT NULL DEFAULT 0,
                        heard_sum REAL NOT NULL DEFAULT 0,
                        heard_ratio REAL NOT NULL DEFAULT 0,
                        ema_heard_ratio REAL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (band, station_key, hour_of_day)
                    );
                    CREATE TABLE band_condition_activity_baseline (
                        band TEXT NOT NULL,
                        hour_of_day INTEGER NOT NULL,
                        sample_count INTEGER NOT NULL DEFAULT 0,
                        total_frames_sum REAL NOT NULL DEFAULT 0,
                        total_unique_stations_sum REAL NOT NULL DEFAULT 0,
                        mobile_frames_sum REAL NOT NULL DEFAULT 0,
                        mobile_unique_stations_sum REAL NOT NULL DEFAULT 0,
                        fixed_frames_sum REAL NOT NULL DEFAULT 0,
                        fixed_unique_stations_sum REAL NOT NULL DEFAULT 0,
                        ema_total_frames REAL,
                        ema_total_unique_stations REAL,
                        ema_mobile_frames REAL,
                        ema_mobile_unique_stations REAL,
                        ema_fixed_frames REAL,
                        ema_fixed_unique_stations REAL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (band, hour_of_day)
                    );
                    CREATE TABLE band_condition_fixed_station_baseline (
                        band TEXT NOT NULL,
                        station_key TEXT NOT NULL,
                        hour_of_day INTEGER NOT NULL,
                        heard_count INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (band, station_key, hour_of_day)
                    );
                    """
                )
                connection.commit()
            finally:
                connection.close()

            init_db()

            connection = connect()
            try:
                columns = {row["name"] for row in connection.execute("PRAGMA table_info(traffic_frames)").fetchall()}
                self.assertIn("interface_id", columns)
                self.assertIn("direction", columns)
                self.assertIn("band", columns)
                modem_columns = {row["name"] for row in connection.execute("PRAGMA table_info(modems)").fetchall()}
                self.assertIn("tx_blocked", modem_columns)
                station_columns = {row["name"] for row in connection.execute("PRAGMA table_info(station_settings)").fetchall()}
                self.assertIn("symbol_overlay", station_columns)
                object_columns = {row["name"] for row in connection.execute("PRAGMA table_info(aprs_objects)").fetchall()}
                item_columns = {row["name"] for row in connection.execute("PRAGMA table_info(aprs_items)").fetchall()}
                self.assertIn("symbol_overlay", object_columns)
                self.assertIn("symbol_overlay", item_columns)
                index_row = connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'index' AND name = 'idx_traffic_frames_interface_created_at'
                    """
                ).fetchone()
                self.assertIsNotNone(index_row)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
