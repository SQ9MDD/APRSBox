from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.db import fetch_one, get_connection, utc_now
from app.services import content
from app.services.traffic_source import APRSIS_SOURCE_KIND, APRSIS_TO_RF_SOURCE_KIND, normalize_source_kind


MAP_STATION_LIMIT = 500
MAP_STATION_ROW_LIMIT = max(
    content.STATION_SNAPSHOT_ROW_LIMIT_MIN,
    MAP_STATION_LIMIT * content.STATION_SNAPSHOT_ROW_LIMIT_FACTOR,
)


def _json_load(value: Any) -> dict[str, Any] | None:
    if not value:
        return None
    loaded = json.loads(str(value))
    return dict(loaded) if isinstance(loaded, dict) else None


def _json_dump(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _snapshot_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("display_callsign") or "").casefold(): row
        for row in rows
        if str(row.get("display_callsign") or "").strip()
    }


def _compose_snapshot(
    rf_snapshot: dict[str, Any] | None,
    aprsis_snapshot: dict[str, Any] | None,
    tx_snapshot: dict[str, Any] | None,
) -> dict[str, Any] | None:
    rf_snapshot = rf_snapshot if str((rf_snapshot or {}).get("display_callsign") or "").strip() else None
    aprsis_snapshot = aprsis_snapshot if str((aprsis_snapshot or {}).get("display_callsign") or "").strip() else None
    tx_snapshot = tx_snapshot if str((tx_snapshot or {}).get("display_callsign") or "").strip() else None
    if rf_snapshot is not None and aprsis_snapshot is not None:
        snapshot = content._merge_station_snapshots(
            rf_snapshot,
            aprsis_snapshot,
            prefer_primary_activity=True,
        )
    else:
        snapshot = rf_snapshot or aprsis_snapshot
    if snapshot is not None and tx_snapshot is not None:
        return content._merge_station_snapshots(snapshot, tx_snapshot)
    return snapshot or tx_snapshot


def _projection_ready(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT is_ready FROM map_station_state_meta WHERE id = 1"
    ).fetchone()
    return bool(row and int(row["is_ready"] or 0))


def ensure_map_station_state() -> None:
    row = fetch_one("SELECT is_ready FROM map_station_state_meta WHERE id = 1")
    if row is None or not bool(int(row["is_ready"] or 0)):
        rebuild_map_station_state()


def rebuild_map_station_state(*, force: bool = False) -> dict[str, int]:
    """Rebuild the durable projection from traffic history under one write lock."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if not force and _projection_ready(connection):
            row = connection.execute(
                "SELECT revision FROM map_station_state_meta WHERE id = 1"
            ).fetchone()
            return {"revision": int(row["revision"] or 0) if row else 0, "station_count": 0}

        def load_rows(format_name: str, source_clause: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
            rows = connection.execute(
                f"""
                SELECT source, source_kind, interface_id, line, created_at
                FROM traffic_frames
                WHERE format = ? {source_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (format_name, *params, MAP_STATION_ROW_LIMIT),
            ).fetchall()
            return [dict(row) for row in rows]

        rf_rows = load_rows(
            "TNC2",
            "AND LOWER(COALESCE(source_kind, 'rf')) NOT IN ('aprsis', 'aprsis_to_rf')",
        )
        aprsis_rows = load_rows(
            "TNC2",
            "AND LOWER(COALESCE(source_kind, 'rf')) = ?",
            (APRSIS_SOURCE_KIND,),
        )
        tx_rows = load_rows("TNC2-TX")
        rf = _snapshot_map(content._build_station_snapshots_from_rows(
            rf_rows, origin="heard", limit=MAP_STATION_LIMIT, materialize_display=False
        ))
        aprsis = _snapshot_map(content._build_station_snapshots_from_rows(
            aprsis_rows, origin="heard", limit=MAP_STATION_LIMIT, materialize_display=False
        ))
        tx = _snapshot_map(content._build_station_snapshots_from_rows(
            tx_rows, origin="local_tx", limit=MAP_STATION_LIMIT, materialize_display=False
        ))
        heard = _snapshot_map(content._merge_rf_primary_station_snapshots(
            list(rf.values()), list(aprsis.values()), limit=MAP_STATION_LIMIT
        ))

        revision_row = connection.execute(
            "SELECT COALESCE(MAX(id), 0) AS revision FROM traffic_frames WHERE format IN ('TNC2', 'TNC2-TX')"
        ).fetchone()
        revision = int(revision_row["revision"] or 0)
        timestamp = utc_now()
        connection.execute("DELETE FROM map_station_state")
        station_count = 0
        for key in sorted(set(heard) | set(tx)):
            snapshot = _compose_snapshot(rf.get(key), aprsis.get(key), tx.get(key))
            if snapshot is None:
                continue
            station_count += 1
            connection.execute(
                """
                INSERT INTO map_station_state(
                    station_key, snapshot_json, rf_snapshot_json, aprsis_snapshot_json,
                    tx_snapshot_json, is_deleted, revision, last_heard_at, last_seen_any_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                """,
                (
                    str(snapshot.get("display_callsign") or key),
                    _json_dump(snapshot),
                    _json_dump(rf.get(key)),
                    _json_dump(aprsis.get(key)),
                    _json_dump(tx.get(key)),
                    revision,
                    str(snapshot.get("last_heard_at") or ""),
                    str(snapshot.get("last_seen_any_at") or snapshot.get("last_heard_at") or ""),
                    timestamp,
                ),
            )
        connection.execute(
            """
            UPDATE map_station_state_meta
            SET revision = ?, is_ready = 1, rebuilt_at = ?
            WHERE id = 1
            """,
            (revision, timestamp),
        )
    return {"revision": revision, "station_count": station_count}


def update_map_station_state_for_frame(
    connection: sqlite3.Connection,
    *,
    frame_id: int,
    frame_format: str,
    frame_row: dict[str, Any],
    parsed: dict[str, Any],
) -> None:
    """Apply one already-parsed APRS frame inside the traffic insert transaction."""
    if not _projection_ready(connection):
        return
    current_revision = connection.execute(
        "SELECT revision FROM map_station_state_meta WHERE id = 1"
    ).fetchone()
    projection_revision = max(
        int(frame_id),
        (int(current_revision["revision"] or 0) if current_revision else 0) + 1,
    )

    aprs_data = dict(parsed.get("aprs_data") or {})
    normalized_source_kind = normalize_source_kind(frame_row.get("source_kind"))
    if frame_format == "TNC2" and normalized_source_kind == APRSIS_TO_RF_SOURCE_KIND:
        connection.execute(
            "UPDATE map_station_state_meta SET revision = ? WHERE id = 1",
            (projection_revision,),
        )
        return
    callsign = str(parsed.get("logical_source_key") or parsed.get("source_key") or "").strip()
    station_key = str(aprs_data.get("entity_name") or callsign).strip()
    if not station_key:
        connection.execute(
            "UPDATE map_station_state_meta SET revision = ? WHERE id = 1",
            (projection_revision,),
        )
        return

    stored = connection.execute(
        "SELECT * FROM map_station_state WHERE station_key = ? COLLATE NOCASE",
        (station_key,),
    ).fetchone()
    rf = _json_load(stored["rf_snapshot_json"]) if stored else None
    aprsis = _json_load(stored["aprsis_snapshot_json"]) if stored else None
    tx = _json_load(stored["tx_snapshot_json"]) if stored else None
    if frame_format == "TNC2-TX":
        slot_name = "tx"
        existing = tx
        origin = "local_tx"
    elif normalized_source_kind == APRSIS_SOURCE_KIND:
        slot_name = "aprsis"
        existing = aprsis
        origin = "heard"
    else:
        slot_name = "rf"
        existing = rf
        origin = "heard"

    packet_group = str(aprs_data.get("packet_group") or "").strip().lower()
    killed = packet_group == "object" and str(aprs_data.get("state") or "").strip().lower() == "killed"
    if killed:
        updated_component = None
    elif packet_group == "status" and str(aprs_data.get("comment") or "").strip():
        updated_component = dict(existing or {})
        updated_component["_pending_status_text"] = str(aprs_data["comment"])
        if existing is not None and not str(existing.get("status_text") or "").strip():
            updated_component["status_text"] = str(aprs_data["comment"])
    else:
        built = content._build_station_snapshots_from_rows(
            [frame_row], origin=origin, limit=1, materialize_display=False
        )
        updated_component = built[0] if built else existing
        if built and existing is not None:
            updated_component = content._merge_station_snapshots(built[0], existing)
        pending_status = str((existing or {}).get("_pending_status_text") or "")
        if updated_component is not None and pending_status and not str(updated_component.get("status_text") or ""):
            updated_component["status_text"] = pending_status
        if updated_component is not None:
            updated_component.pop("_pending_status_text", None)

    if slot_name == "rf":
        rf = updated_component
    elif slot_name == "aprsis":
        aprsis = updated_component
    else:
        tx = updated_component
    snapshot = _compose_snapshot(rf, aprsis, tx)
    timestamp = utc_now()
    if snapshot is None:
        connection.execute(
            """
            INSERT INTO map_station_state(
                station_key, snapshot_json, rf_snapshot_json, aprsis_snapshot_json,
                tx_snapshot_json, is_deleted, revision, last_heard_at, last_seen_any_at, updated_at
            ) VALUES (?, NULL, ?, ?, ?, 1, ?, NULL, NULL, ?)
            ON CONFLICT(station_key) DO UPDATE SET
                snapshot_json = NULL, rf_snapshot_json = excluded.rf_snapshot_json,
                aprsis_snapshot_json = excluded.aprsis_snapshot_json,
                tx_snapshot_json = excluded.tx_snapshot_json, is_deleted = 1,
                revision = excluded.revision, last_heard_at = NULL,
                last_seen_any_at = NULL, updated_at = excluded.updated_at
            """,
            (station_key, _json_dump(rf), _json_dump(aprsis), _json_dump(tx), projection_revision, timestamp),
        )
    else:
        connection.execute(
            """
            INSERT INTO map_station_state(
                station_key, snapshot_json, rf_snapshot_json, aprsis_snapshot_json,
                tx_snapshot_json, is_deleted, revision, last_heard_at, last_seen_any_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            ON CONFLICT(station_key) DO UPDATE SET
                snapshot_json = excluded.snapshot_json, rf_snapshot_json = excluded.rf_snapshot_json,
                aprsis_snapshot_json = excluded.aprsis_snapshot_json,
                tx_snapshot_json = excluded.tx_snapshot_json, is_deleted = 0,
                revision = excluded.revision, last_heard_at = excluded.last_heard_at,
                last_seen_any_at = excluded.last_seen_any_at,
                updated_at = excluded.updated_at
            """,
            (
                str(snapshot.get("display_callsign") or station_key),
                _json_dump(snapshot), _json_dump(rf), _json_dump(aprsis), _json_dump(tx),
                projection_revision,
                str(snapshot.get("last_heard_at") or ""),
                str(snapshot.get("last_seen_any_at") or snapshot.get("last_heard_at") or ""),
                timestamp,
            ),
        )
    connection.execute(
        "UPDATE map_station_state_meta SET revision = ? WHERE id = 1",
        (projection_revision,),
    )


def expire_map_station_state(*, cutoff: str) -> int:
    """Expire projection rows together with the configured traffic-history window."""
    with get_connection() as connection:
        if not _projection_ready(connection):
            return 0
        rows = connection.execute(
            """
            SELECT station_key, rf_snapshot_json, aprsis_snapshot_json, tx_snapshot_json
            FROM map_station_state
            WHERE is_deleted = 0
            """
        ).fetchall()
        updates: list[tuple[str, dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]] = []
        for row in rows:
            components = [
                _json_load(row["rf_snapshot_json"]),
                _json_load(row["aprsis_snapshot_json"]),
                _json_load(row["tx_snapshot_json"]),
            ]
            retained = [
                component
                if component is not None and str(
                    component.get("last_seen_any_at") or component.get("last_heard_at") or ""
                ) >= str(cutoff)
                else None
                for component in components
            ]
            if retained != components:
                updates.append((str(row["station_key"]), retained[0], retained[1], retained[2]))
        if not updates:
            return 0
        meta = connection.execute(
            "SELECT revision FROM map_station_state_meta WHERE id = 1"
        ).fetchone()
        revision = int(meta["revision"] or 0) + 1
        timestamp = utc_now()
        for station_key, rf, aprsis, tx in updates:
            snapshot = _compose_snapshot(rf, aprsis, tx)
            connection.execute(
                """
                UPDATE map_station_state
                SET snapshot_json = ?, rf_snapshot_json = ?, aprsis_snapshot_json = ?,
                    tx_snapshot_json = ?, is_deleted = ?, revision = ?,
                    last_heard_at = ?, last_seen_any_at = ?, updated_at = ?
                WHERE station_key = ? COLLATE NOCASE
                """,
                (
                    _json_dump(snapshot), _json_dump(rf), _json_dump(aprsis), _json_dump(tx),
                    0 if snapshot is not None else 1, revision,
                    str((snapshot or {}).get("last_heard_at") or "") or None,
                    str((snapshot or {}).get("last_seen_any_at") or (snapshot or {}).get("last_heard_at") or "") or None,
                    timestamp, station_key,
                ),
            )
        connection.execute(
            "UPDATE map_station_state_meta SET revision = ? WHERE id = 1",
            (revision,),
        )
        return len(updates)


def read_map_station_state(
    *,
    since_revision: int | None = None,
    station_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_map_station_state()
    with get_connection() as connection:
        meta = connection.execute(
            "SELECT revision FROM map_station_state_meta WHERE id = 1"
        ).fetchone()
        revision = int(meta["revision"] or 0) if meta else 0
        full_snapshot = since_revision is None or int(since_revision) < 0 or int(since_revision) > revision
        if full_snapshot:
            rows = connection.execute(
                """
                SELECT station_key, snapshot_json, is_deleted
                FROM map_station_state
                WHERE is_deleted = 0
                ORDER BY last_heard_at DESC, station_key
                LIMIT ?
                """,
                (MAP_STATION_LIMIT,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT station_key, snapshot_json, is_deleted
                FROM map_station_state
                WHERE revision > ?
                ORDER BY revision ASC, station_key
                """,
                (int(since_revision),),
            ).fetchall()
    snapshots = [_json_load(row["snapshot_json"]) for row in rows if not int(row["is_deleted"] or 0)]
    return {
        "revision": revision,
        "full_snapshot": full_snapshot,
        "snapshots": content.prepare_station_snapshots_for_display(
            [item for item in snapshots if item is not None],
            station_settings=station_settings,
        ),
        "removed_station_keys": [str(row["station_key"]) for row in rows if int(row["is_deleted"] or 0)],
    }


def read_map_station_rf_snapshots() -> list[dict[str, Any]]:
    ensure_map_station_state()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT rf_snapshot_json
            FROM map_station_state
            WHERE is_deleted = 0 AND rf_snapshot_json IS NOT NULL
            ORDER BY last_heard_at DESC, station_key
            LIMIT ?
            """,
            (MAP_STATION_LIMIT,),
        ).fetchall()
    return [snapshot for row in rows if (snapshot := _json_load(row["rf_snapshot_json"])) is not None]
