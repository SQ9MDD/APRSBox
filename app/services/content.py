from __future__ import annotations

import sqlite3
from typing import Any

from app.db import fetch_all, fetch_one, get_connection, log_event, utc_now
from app.sections import SECTION_DEFINITIONS


def get_section_rows(slug: str) -> list[dict[str, Any]]:
    definition = SECTION_DEFINITIONS[slug]
    rows = fetch_all(f"SELECT * FROM {definition.table_name} ORDER BY id DESC")
    return [dict(row) for row in rows]


def create_section_row(slug: str, payload: dict[str, Any]) -> None:
    definition = SECTION_DEFINITIONS[slug]
    timestamp = utc_now()
    values: dict[str, Any] = {}
    for field in definition.fields:
        name = field["name"]
        if field["type"] == "checkbox":
            values[name] = int(bool(payload.get(name)))
        else:
            values[name] = payload.get(name)
    if slug in {"modems", "servers"}:
        values.setdefault("notes", "")
        columns = list(values.keys()) + ["created_at", "updated_at"]
        params = list(values.values()) + [timestamp, timestamp]
    else:
        columns = list(values.keys()) + ["updated_at"]
        params = list(values.values()) + [timestamp]
    placeholders = ", ".join("?" for _ in columns)
    column_list = ", ".join(columns)
    with get_connection() as connection:
        connection.execute(
            f"INSERT INTO {definition.table_name} ({column_list}) VALUES ({placeholders})",
            tuple(params),
        )
    log_event("INFO", "config", f"Created record in {definition.table_name}")


def get_station_settings() -> dict[str, Any]:
    row = fetch_one("SELECT * FROM station_settings WHERE id = 1")
    return dict(row) if row else {}


def update_station_settings(payload: dict[str, Any]) -> None:
    values = {
        "callsign": payload.get("callsign", ""),
        "ssid": payload.get("ssid", ""),
        "beacon_comment": payload.get("beacon_comment", ""),
        "latitude": payload.get("latitude", ""),
        "longitude": payload.get("longitude", ""),
        "symbol_table": payload.get("symbol_table", "/"),
        "symbol_code": payload.get("symbol_code", ">"),
        "tx_enabled": int(bool(payload.get("tx_enabled"))),
        "updated_at": utc_now(),
    }
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE station_settings
            SET callsign = :callsign,
                ssid = :ssid,
                beacon_comment = :beacon_comment,
                latitude = :latitude,
                longitude = :longitude,
                symbol_table = :symbol_table,
                symbol_code = :symbol_code,
                tx_enabled = :tx_enabled,
                updated_at = :updated_at
            WHERE id = 1
            """,
            values,
        )
    log_event("INFO", "config", "Updated station settings")


def recent_event_logs(limit: int = 100) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id, level, category, message, created_at FROM event_logs ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return [dict(row) for row in rows]


def dashboard_summary() -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for slug, definition in SECTION_DEFINITIONS.items():
        row = fetch_one(f"SELECT COUNT(*) AS total FROM {definition.table_name}")
        metrics[slug] = row["total"] if row else 0
    metrics["users"] = fetch_one("SELECT COUNT(*) AS total FROM users")["total"]
    metrics["logs"] = fetch_one("SELECT COUNT(*) AS total FROM event_logs")["total"]
    return metrics


def safe_create_section_row(slug: str, payload: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        create_section_row(slug, payload)
    except sqlite3.IntegrityError as exc:
        return False, str(exc)
    return True, None

