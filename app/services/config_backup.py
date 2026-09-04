from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app import get_version
from app.db import connect, log_event, utc_now

CONFIG_BACKUP_FORMAT = "aprsbox-config-backup"
CONFIG_BACKUP_VERSION = 2
_FILENAME_TOKEN_RE = re.compile(r"[^A-Z0-9_-]+")

CONFIG_BACKUP_TABLES: tuple[str, ...] = (
    "map_sources",
    "modems",
    "aprsis_servers",
    "station_settings",
    "wx_config",
    "wx_sources",
    "wx_mappings",
    "notification_transports",
    "notification_radar_rules",
    "igate_rules",
    "digi_rules",
    "digi_flows",
    "digi_flow_steps",
    "aprs_objects",
    "aprs_items",
    "bulletins",
)

CONFIG_BACKUP_APP_SETTING_KEYS: tuple[str, ...] = (
    "app_language",
    "aprs_symbol_set",
    "ui_palette",
    "traffic_retention_minutes",
    "event_log_min_level",
    "event_log_debug_enabled",
    "map_coverage_fill_opacity",
    "map_marker_clustering_enabled",
    "map_marker_spiderfy_enabled",
    "map_marker_spiderfy_zoom_levels_before_max",
    "map_marker_spiderfy_nearby_distance_px",
    "map_station_label_hide_at_zoom",
    "gui_update_branch",
    "aprsis_server",
    "aprsis_port",
    "aprsis_login",
    "aprsis_passcode",
    "aprs.alarm_groups",
    "aprs.alarm_enabled",
    "aprs.map_alarm_level_threshold",
    "aprs.global_alarm_level_threshold",
    "aprs.alarm_category_thresholds",
    "messages.default_path",
    "messages.receive_any_ssid",
    "messages.target_groups",
    "messages.aprsis_target_groups",
    "station.tx.internal_mode",
    "messages_enabled",
    "messages_include_content",
    "radar_enabled",
    "radar_ignored_patterns",
)

CONFIG_BACKUP_OPTIONAL_APP_SETTING_DEFAULTS: dict[str, str | None] = {
    # Added during backup format v2; accepting absent newer keys keeps older v2 files importable.
    "map_marker_clustering_enabled": "0",
    "map_marker_spiderfy_enabled": "0",
    "map_marker_spiderfy_zoom_levels_before_max": "2",
    "map_marker_spiderfy_nearby_distance_px": "20",
    "map_station_label_hide_at_zoom": "10",
    # Older backups predate separate RF and APRS-IS message groups.  None
    # preserves the first-use fallback to the saved RF group list.
    "messages.aprsis_target_groups": None,
}

# These columns describe transient counters or the result of a connectivity
# test. They are deliberately not restored as configuration.
CONFIG_BACKUP_EXCLUDED_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "map_sources": ("cache_tile_count", "cache_size_bytes"),
    "wx_sources": ("last_test_status", "last_test_error", "last_test_at"),
    "notification_transports": ("last_test_status", "last_test_error", "last_test_at"),
}


def build_configuration_backup_filename() -> str:
    station_identity = _station_identity_slug()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"aprsbox-config-backup-{station_identity}-{timestamp}.json"


def export_configuration_backup() -> dict[str, Any]:
    with connect() as connection:
        connection.execute("BEGIN")
        tables_payload = {
            table: _export_table_rows(connection, table)
            for table in CONFIG_BACKUP_TABLES
        }
        placeholders = ", ".join("?" for _ in CONFIG_BACKUP_APP_SETTING_KEYS)
        app_settings_rows = connection.execute(
            f"""
            SELECT key, value
            FROM app_settings
            WHERE key IN ({placeholders})
            ORDER BY key ASC
            """,
            CONFIG_BACKUP_APP_SETTING_KEYS,
        ).fetchall()

    app_settings_payload: dict[str, str | None] = {
        key: None
        for key in CONFIG_BACKUP_APP_SETTING_KEYS
    }
    app_settings_payload.update({str(row["key"]): str(row["value"]) for row in app_settings_rows})
    payload = {
        "format": CONFIG_BACKUP_FORMAT,
        "backup_version": CONFIG_BACKUP_VERSION,
        "created_at": utc_now(),
        "app_version": get_version(),
        "app_settings": app_settings_payload,
        "tables": tables_payload,
    }
    log_event("INFO", "settings", "Exported configuration backup snapshot")
    return payload


def export_configuration_backup_bytes() -> bytes:
    payload = export_configuration_backup()
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def import_configuration_backup(raw_payload: bytes) -> None:
    payload = _parse_backup_payload(raw_payload)
    _apply_backup_payload(payload)
    log_event("INFO", "settings", "Imported configuration backup snapshot")


def safe_import_configuration_backup(raw_payload: bytes) -> tuple[bool, str | None]:
    try:
        import_configuration_backup(raw_payload)
        return True, None
    except ValueError as exc:
        return False, str(exc)
    except sqlite3.DatabaseError as exc:
        return False, f"Failed to apply configuration backup: {exc}"


def _parse_backup_payload(raw_payload: bytes) -> dict[str, Any]:
    if not raw_payload:
        raise ValueError("Backup file is empty.")
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("Backup file must be UTF-8 encoded JSON.") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Backup file is not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Backup payload must be a JSON object.")
    if str(payload.get("format") or "") != CONFIG_BACKUP_FORMAT:
        raise ValueError("Unsupported backup format.")
    backup_version = payload.get("backup_version")
    if isinstance(backup_version, bool) or not isinstance(backup_version, int) or backup_version != CONFIG_BACKUP_VERSION:
        raise ValueError("Unsupported backup version.")

    tables_payload = payload.get("tables")
    if not isinstance(tables_payload, dict):
        raise ValueError("Backup payload does not contain configuration tables.")
    missing_tables = [table for table in CONFIG_BACKUP_TABLES if table not in tables_payload]
    if missing_tables:
        missing = ", ".join(missing_tables)
        raise ValueError(f"Backup payload is missing table data: {missing}.")
    unexpected_tables = [table for table in tables_payload if table not in CONFIG_BACKUP_TABLES]
    if unexpected_tables:
        unexpected = ", ".join(sorted(str(table) for table in unexpected_tables))
        raise ValueError(f"Backup payload contains unsupported table data: {unexpected}.")

    for table in CONFIG_BACKUP_TABLES:
        rows = tables_payload.get(table)
        if not isinstance(rows, list):
            raise ValueError(f"Backup payload contains invalid rows for table '{table}'.")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"Backup payload contains invalid row shape for table '{table}'.")

    app_settings_payload = payload.get("app_settings")
    if not isinstance(app_settings_payload, dict):
        raise ValueError("Backup payload contains invalid app settings.")
    normalized_app_settings = dict(app_settings_payload)
    missing_settings = [
        key
        for key in CONFIG_BACKUP_APP_SETTING_KEYS
        if key not in app_settings_payload and key not in CONFIG_BACKUP_OPTIONAL_APP_SETTING_DEFAULTS
    ]
    if missing_settings:
        missing = ", ".join(missing_settings)
        raise ValueError(f"Backup payload is missing app settings: {missing}.")
    unexpected_settings = [key for key in app_settings_payload if key not in CONFIG_BACKUP_APP_SETTING_KEYS]
    if unexpected_settings:
        unexpected = ", ".join(sorted(str(key) for key in unexpected_settings))
        raise ValueError(f"Backup payload contains unsupported app settings: {unexpected}.")
    for key, default_value in CONFIG_BACKUP_OPTIONAL_APP_SETTING_DEFAULTS.items():
        normalized_app_settings.setdefault(key, default_value)
    for key, value in normalized_app_settings.items():
        if value is not None and not isinstance(value, str):
            raise ValueError(f"Backup payload contains invalid value for app setting '{key}'.")

    return {
        "app_settings": normalized_app_settings,
        "tables": tables_payload,
    }


def _apply_backup_payload(payload: dict[str, Any]) -> None:
    app_settings_payload = dict(payload["app_settings"])
    table_payload = dict(payload["tables"])

    connection = connect()
    transaction_started = False
    try:
        _validate_table_payload(connection, table_payload)
        connection.execute("BEGIN IMMEDIATE")
        transaction_started = True
        connection.execute("PRAGMA defer_foreign_keys = ON")

        _replace_app_settings(connection, app_settings_payload)
        for table in reversed(CONFIG_BACKUP_TABLES):
            _delete_missing_table_rows(connection, table, list(table_payload[table]))
        for table in CONFIG_BACKUP_TABLES:
            rows = list(table_payload[table])
            _neutralize_unique_columns(connection, table, rows)
            _sync_table_rows(connection, table, rows)

        violations = list(connection.execute("PRAGMA foreign_key_check").fetchall())
        if violations:
            raise ValueError(_format_foreign_key_violation_error(violations))

        connection.execute("COMMIT")
        transaction_started = False
    except Exception:
        if transaction_started:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def _replace_app_settings(connection: sqlite3.Connection, app_settings_payload: dict[str, str | None]) -> None:
    placeholders = ", ".join("?" for _ in CONFIG_BACKUP_APP_SETTING_KEYS)
    connection.execute(
        f"DELETE FROM app_settings WHERE key IN ({placeholders})",
        CONFIG_BACKUP_APP_SETTING_KEYS,
    )
    now = utc_now()
    for key in CONFIG_BACKUP_APP_SETTING_KEYS:
        if app_settings_payload[key] is None:
            continue
        connection.execute(
            """
            INSERT INTO app_settings(key, value, updated_at)
            VALUES (?, ?, ?)
            """,
            (key, str(app_settings_payload[key]), now),
        )


def _sync_table_rows(connection: sqlite3.Connection, table_name: str, rows: list[dict[str, Any]]) -> None:
    table_columns = _backup_table_columns(connection, table_name)
    for row in rows:
        row_id = int(row["id"])
        exists = connection.execute(f'SELECT 1 FROM "{table_name}" WHERE id = ?', (row_id,)).fetchone()
        if exists:
            update_columns = [column for column in table_columns if column != "id"]
            assignments = ", ".join(f'"{column}" = ?' for column in update_columns)
            values = tuple(row[column] for column in update_columns)
            connection.execute(
                f'UPDATE "{table_name}" SET {assignments} WHERE id = ?',
                (*values, row_id),
            )
            continue
        quoted_columns = ", ".join(f'"{column}"' for column in table_columns)
        placeholders = ", ".join("?" for _ in table_columns)
        values = tuple(row[column] for column in table_columns)
        connection.execute(f'INSERT INTO "{table_name}" ({quoted_columns}) VALUES ({placeholders})', values)


def _delete_missing_table_rows(connection: sqlite3.Connection, table_name: str, rows: list[dict[str, Any]]) -> None:
    row_ids = [int(row["id"]) for row in rows]
    if not row_ids:
        connection.execute(f'DELETE FROM "{table_name}"')
        return
    placeholders = ", ".join("?" for _ in row_ids)
    connection.execute(f'DELETE FROM "{table_name}" WHERE id NOT IN ({placeholders})', row_ids)


def _neutralize_unique_columns(connection: sqlite3.Connection, table_name: str, rows: list[dict[str, Any]]) -> None:
    """Avoid transient UNIQUE conflicts while retained rows exchange values."""
    if not rows:
        return
    incoming_ids = [int(row["id"]) for row in rows]
    id_placeholders = ", ".join("?" for _ in incoming_ids)
    column_types = {
        str(row["name"]): str(row["type"] or "").upper()
        for row in connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    }
    unique_columns: set[str] = set()
    for index_row in connection.execute(f'PRAGMA index_list("{table_name}")').fetchall():
        if not bool(index_row["unique"]):
            continue
        index_name = str(index_row["name"])
        index_columns = [
            str(row["name"])
            for row in connection.execute(f'PRAGMA index_info("{index_name}")').fetchall()
            if row["name"] is not None
        ]
        candidates = [column for column in reversed(index_columns) if column != "id"]
        if candidates:
            unique_columns.add(candidates[0])
    if not unique_columns:
        return

    connection.execute("PRAGMA ignore_check_constraints = ON")
    try:
        for column in sorted(unique_columns):
            column_type = column_types.get(column, "")
            if any(token in column_type for token in ("INT", "REAL", "NUM", "DEC", "FLOAT", "DOUBLE")):
                temporary_value = "(-9000000000000000000 + id)"
            else:
                temporary_value = f"'__APRSBOX_BACKUP_V2_{table_name}_' || id"
            connection.execute(
                f'UPDATE "{table_name}" SET "{column}" = {temporary_value} WHERE id IN ({id_placeholders})',
                incoming_ids,
            )
    finally:
        connection.execute("PRAGMA ignore_check_constraints = OFF")


def _validate_table_payload(connection: sqlite3.Connection, table_payload: dict[str, Any]) -> None:
    for table_name in CONFIG_BACKUP_TABLES:
        expected_columns = set(_backup_table_columns(connection, table_name))
        seen_ids: set[int] = set()
        for row in table_payload[table_name]:
            actual_columns = set(row)
            if actual_columns != expected_columns:
                missing = sorted(expected_columns - actual_columns)
                unexpected = sorted(actual_columns - expected_columns)
                details: list[str] = []
                if missing:
                    details.append(f"missing columns: {', '.join(missing)}")
                if unexpected:
                    details.append(f"unsupported columns: {', '.join(unexpected)}")
                raise ValueError(f"Backup row for table '{table_name}' has an invalid schema ({'; '.join(details)}).")
            row_id = row.get("id")
            if isinstance(row_id, bool) or not isinstance(row_id, int) or row_id < 1:
                raise ValueError(f"Backup row for table '{table_name}' contains an invalid id.")
            if row_id in seen_ids:
                raise ValueError(f"Backup table '{table_name}' contains duplicate id {row_id}.")
            seen_ids.add(row_id)


def _export_table_rows(connection: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
    columns = _backup_table_columns(connection, table_name)
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    return [
        dict(row)
        for row in connection.execute(f'SELECT {quoted_columns} FROM "{table_name}" ORDER BY id ASC').fetchall()
    ]


def _backup_table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    excluded = set(CONFIG_BACKUP_EXCLUDED_TABLE_COLUMNS.get(table_name, ()))
    return [column for column in _table_columns(connection, table_name) if column not in excluded]


def _table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    return [str(row["name"]) for row in connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()]


def _format_foreign_key_violation_error(violations: list[sqlite3.Row]) -> str:
    first = violations[0]
    table_name = str(first["table"] if "table" in first.keys() else first[0])
    rowid_value = first["rowid"] if "rowid" in first.keys() else first[1]
    parent_table = str(first["parent"] if "parent" in first.keys() else first[2])
    fk_index = first["fkid"] if "fkid" in first.keys() else first[3]
    extra = ""
    if len(violations) > 1:
        extra = f" (+{len(violations) - 1} more)"
    return (
        "Backup payload contains invalid cross-table references. "
        f"First violation: child_table={table_name}, rowid={rowid_value}, parent_table={parent_table}, fk_index={fk_index}{extra}."
    )


def _station_identity_slug() -> str:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT callsign, ssid
            FROM station_settings
            WHERE id = 1
            """
        ).fetchone()
    callsign = _normalize_filename_token(str((row["callsign"] if row else "") or ""), fallback="NOCALL")
    ssid_raw = str((row["ssid"] if row else "") or "").strip()
    if ssid_raw:
        ssid = _normalize_filename_token(ssid_raw, fallback="0")
        return f"{callsign}-{ssid}"
    return callsign


def _normalize_filename_token(value: str, *, fallback: str) -> str:
    normalized = _FILENAME_TOKEN_RE.sub("_", value.strip().upper()).strip("_-")
    return normalized or fallback
