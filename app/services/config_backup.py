from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app import get_version
from app.db import connect, log_event, utc_now

CONFIG_BACKUP_FORMAT = "aprsbox-config-backup"
CONFIG_BACKUP_VERSION = 1

CONFIG_BACKUP_TABLES: tuple[str, ...] = (
    "map_sources",
    "modems",
    "aprsis_servers",
    "station_settings",
    "wx_config",
    "wx_sources",
    "wx_mappings",
    "igate_rules",
    "digi_rules",
    "digi_flows",
    "digi_flow_steps",
    "aprs_objects",
    "aprs_items",
    "bulletins",
    "band_condition_reference_stations",
)

CONFIG_BACKUP_APP_SETTING_KEYS: tuple[str, ...] = (
    "app_language",
    "ui_palette",
    "gui_update_branch",
    "aprsis_server",
    "aprsis_port",
    "aprsis_login",
    "aprsis_passcode",
)


def build_configuration_backup_filename() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"aprsbox-config-backup-{timestamp}.json"


def export_configuration_backup() -> dict[str, Any]:
    with connect() as connection:
        tables_payload = {
            table: [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid ASC").fetchall()]
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

    app_settings_payload = {
        str(row["key"]): str(row["value"])
        for row in app_settings_rows
    }
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
    except sqlite3.DatabaseError:
        return False, "Failed to apply configuration backup."


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
    if int(payload.get("backup_version") or 0) != CONFIG_BACKUP_VERSION:
        raise ValueError("Unsupported backup version.")

    tables_payload = payload.get("tables")
    if not isinstance(tables_payload, dict):
        raise ValueError("Backup payload does not contain configuration tables.")
    missing_tables = [table for table in CONFIG_BACKUP_TABLES if table not in tables_payload]
    if missing_tables:
        missing = ", ".join(missing_tables)
        raise ValueError(f"Backup payload is missing table data: {missing}.")

    for table in CONFIG_BACKUP_TABLES:
        rows = tables_payload.get(table)
        if not isinstance(rows, list):
            raise ValueError(f"Backup payload contains invalid rows for table '{table}'.")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"Backup payload contains invalid row shape for table '{table}'.")

    app_settings_payload = payload.get("app_settings", {})
    if not isinstance(app_settings_payload, dict):
        raise ValueError("Backup payload contains invalid app settings.")

    return {
        "app_settings": {str(key): str(value) for key, value in app_settings_payload.items()},
        "tables": tables_payload,
    }


def _apply_backup_payload(payload: dict[str, Any]) -> None:
    app_settings_payload = dict(payload["app_settings"])
    table_payload = dict(payload["tables"])

    connection = connect()
    transaction_started = False
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN IMMEDIATE")
        transaction_started = True

        _replace_app_settings(connection, app_settings_payload)
        for table in CONFIG_BACKUP_TABLES:
            _replace_table_rows(connection, table, list(table_payload.get(table) or []))

        violations = list(connection.execute("PRAGMA foreign_key_check").fetchall())
        if violations:
            raise ValueError("Backup payload contains invalid cross-table references.")

        connection.execute("COMMIT")
        transaction_started = False
    except Exception:
        if transaction_started:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.close()


def _replace_app_settings(connection: sqlite3.Connection, app_settings_payload: dict[str, str]) -> None:
    placeholders = ", ".join("?" for _ in CONFIG_BACKUP_APP_SETTING_KEYS)
    connection.execute(
        f"DELETE FROM app_settings WHERE key IN ({placeholders})",
        CONFIG_BACKUP_APP_SETTING_KEYS,
    )
    now = utc_now()
    for key in CONFIG_BACKUP_APP_SETTING_KEYS:
        if key not in app_settings_payload:
            continue
        connection.execute(
            """
            INSERT INTO app_settings(key, value, updated_at)
            VALUES (?, ?, ?)
            """,
            (key, str(app_settings_payload[key]), now),
        )


def _replace_table_rows(connection: sqlite3.Connection, table_name: str, rows: list[dict[str, Any]]) -> None:
    table_columns = _table_columns(connection, table_name)
    connection.execute(f"DELETE FROM {table_name}")
    if not rows:
        return

    for row in rows:
        selected_columns = [column for column in table_columns if column in row]
        if not selected_columns:
            continue
        quoted_columns = ", ".join(f'"{column}"' for column in selected_columns)
        placeholders = ", ".join("?" for _ in selected_columns)
        values = tuple(row[column] for column in selected_columns)
        connection.execute(
            f'INSERT INTO "{table_name}" ({quoted_columns}) VALUES ({placeholders})',
            values,
        )


def _table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    return [str(row["name"]) for row in connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()]
