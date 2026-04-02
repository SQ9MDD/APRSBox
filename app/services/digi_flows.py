from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.db import fetch_all, fetch_one, get_connection, log_event, utc_now

SOURCE_STEP_TYPES = ("receiver_rf", "receiver_aprsis")
FILTER_STEP_TYPES = (
    "filter_dupe",
    "filter_digi",
    "filter_path",
    "filter_callsign",
    "filter_packet_type",
    "filter_icon",
    "filter_distance",
    "filter_rate_limit",
    "filter_rate_limit_per_callsign",
)
TARGET_STEP_TYPES = ("tx_rf", "tx_aprsis", "action_drop", "action_log")
ALL_STEP_TYPES = SOURCE_STEP_TYPES + FILTER_STEP_TYPES + TARGET_STEP_TYPES

STEP_TYPE_META: dict[str, dict[str, Any]] = {
    "receiver_rf": {
        "category": "source",
        "label": "Receiver RF",
        "badge": "Source",
        "description": "Receives packets from an RF input identifier.",
        "config_fields": (
            {"name": "rf_port", "label": "RF Port / Radio", "type": "text", "required": True},
        ),
    },
    "receiver_aprsis": {
        "category": "source",
        "label": "Receiver APRS-IS",
        "badge": "Source",
        "description": "Receives packets from an APRS-IS input identifier.",
        "config_fields": (
            {"name": "aprsis_source", "label": "APRS-IS Source", "type": "text", "required": True},
        ),
    },
    "filter_dupe": {
        "category": "filter",
        "label": "Duplicate Filter",
        "badge": "Filter",
        "description": "Stores a duplicate suppression window.",
        "config_fields": (
            {"name": "window_sec", "label": "Window (sec)", "type": "number", "required": True},
        ),
    },
    "filter_path": {
        "category": "filter",
        "label": "Path Filter",
        "badge": "Filter",
        "description": "Stores path allow or deny rules.",
        "config_fields": (
            {"name": "mode", "label": "Mode", "type": "select", "required": True, "options": ("allow", "deny")},
            {"name": "paths", "label": "Paths (one per line)", "type": "textarea", "required": False},
        ),
    },
    "filter_digi": {
        "category": "filter",
        "label": "DIGI Filter",
        "badge": "Filter",
        "description": "Allows or denies packets repeated by specific digi callsigns.",
        "config_fields": (
            {"name": "mode", "label": "Mode", "type": "select", "required": True, "options": ("allow", "deny")},
            {"name": "digis", "label": "DIGI Callsigns (one per line)", "type": "textarea", "required": False},
        ),
    },
    "filter_callsign": {
        "category": "filter",
        "label": "Callsign Filter",
        "badge": "Filter",
        "description": "Stores callsign allow or deny rules.",
        "config_fields": (
            {"name": "mode", "label": "Mode", "type": "select", "required": True, "options": ("allow", "deny")},
            {"name": "callsigns", "label": "Callsigns (one per line)", "type": "textarea", "required": False},
        ),
    },
    "filter_packet_type": {
        "category": "filter",
        "label": "Packet Type Filter",
        "badge": "Filter",
        "description": "Allows or denies selected APRS packet types.",
        "config_fields": (
            {"name": "mode", "label": "Mode", "type": "select", "required": True, "options": ("allow", "deny")},
            {"name": "packet_types", "label": "Packet Types (one per line)", "type": "textarea", "required": False},
        ),
    },
    "filter_icon": {
        "category": "filter",
        "label": "Icon Filter",
        "badge": "Filter",
        "description": "Allows or denies selected APRS icons.",
        "config_fields": (
            {"name": "mode", "label": "Mode", "type": "select", "required": True, "options": ("allow", "deny")},
            {"name": "icons", "label": "Icons (one per line)", "type": "textarea", "required": False},
        ),
    },
    "filter_distance": {
        "category": "filter",
        "label": "Distance Filter",
        "badge": "Filter",
        "description": "Stores a maximum packet distance.",
        "config_fields": (
            {"name": "max_km", "label": "Max Distance (km)", "type": "number", "required": True},
        ),
    },
    "filter_rate_limit": {
        "category": "filter",
        "label": "Rate Limit Filter",
        "badge": "Filter",
        "description": "Stores a packet rate limit.",
        "config_fields": (
            {"name": "packets_per_minute", "label": "Packets / Minute", "type": "number", "required": True},
        ),
    },
    "filter_rate_limit_per_callsign": {
        "category": "filter",
        "label": "Rate Limit Per Callsign",
        "badge": "Filter",
        "description": "Stores a packet rate limit applied separately for each callsign.",
        "config_fields": (
            {"name": "packets_per_minute", "label": "Packets / Minute", "type": "number", "required": True},
        ),
    },
    "tx_rf": {
        "category": "target",
        "label": "TX RF",
        "badge": "Target",
        "description": "Sends packets to an RF output identifier.",
        "config_fields": (
            {"name": "rf_target", "label": "RF Target", "type": "text", "required": True},
        ),
    },
    "tx_aprsis": {
        "category": "target",
        "label": "TX APRS-IS",
        "badge": "Target",
        "description": "Sends packets to an APRS-IS output identifier.",
        "config_fields": (
            {"name": "aprsis_target", "label": "APRS-IS Target", "type": "text", "required": True},
        ),
    },
    "action_drop": {
        "category": "target",
        "label": "Action Drop",
        "badge": "Target",
        "description": "Drops the packet at the end of the flow.",
        "config_fields": (
            {"name": "note", "label": "Note", "type": "text", "required": False},
        ),
    },
    "action_log": {
        "category": "target",
        "label": "Log Only",
        "badge": "Target",
        "description": "Logs the packet at the end of the flow.",
        "config_fields": (
            {"name": "log_tag", "label": "Log Tag", "type": "text", "required": False},
            {"name": "note", "label": "Note", "type": "text", "required": False},
        ),
    },
}

STEP_TYPE_TO_REF_FIELD = {
    "receiver_rf": "rf_port",
    "receiver_aprsis": "aprsis_source",
    "tx_rf": "rf_target",
    "tx_aprsis": "aprsis_target",
    "action_drop": "note",
    "action_log": "log_tag",
}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _step_category(step_type: str) -> str:
    meta = STEP_TYPE_META.get(step_type)
    if not meta:
        raise ValueError(f"Unsupported flow step type: {step_type}.")
    return str(meta["category"])


def _normalize_enabled(value: Any) -> int:
    return 1 if bool(value) else 0


def _normalize_number(value: Any, *, label: str, minimum: int = 0) -> int:
    text = _normalize_text(value)
    if not text:
        raise ValueError(f"{label} is required.")
    try:
        parsed = int(text)
    except ValueError as exc:
        raise ValueError(f"{label} must be a whole number.") from exc
    if parsed < minimum:
        raise ValueError(f"{label} must be at least {minimum}.")
    return parsed


def _normalize_multiline_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    lines = []
    for raw_line in str(value or "").splitlines():
        item = raw_line.strip()
        if item:
            lines.append(item)
    return lines


def _default_step_title(step_type: str) -> str:
    return str(STEP_TYPE_META[step_type]["label"])


def _default_step_config(step_type: str, ref_value: str = "") -> dict[str, Any]:
    if step_type == "receiver_rf":
        return {"rf_port": ref_value}
    if step_type == "receiver_aprsis":
        return {"aprsis_source": ref_value}
    if step_type == "filter_dupe":
        return {"window_sec": 30}
    if step_type == "filter_digi":
        return {"mode": "allow", "digis": []}
    if step_type == "filter_path":
        return {"mode": "allow", "paths": []}
    if step_type == "filter_callsign":
        return {"mode": "allow", "callsigns": []}
    if step_type == "filter_packet_type":
        return {"mode": "allow", "packet_types": []}
    if step_type == "filter_icon":
        return {"mode": "allow", "icons": []}
    if step_type == "filter_distance":
        return {"max_km": 50}
    if step_type == "filter_rate_limit":
        return {"packets_per_minute": 60}
    if step_type == "filter_rate_limit_per_callsign":
        return {"packets_per_minute": 30}
    if step_type == "tx_rf":
        return {"rf_target": ref_value}
    if step_type == "tx_aprsis":
        return {"aprsis_target": ref_value}
    if step_type == "action_drop":
        return {"note": ""}
    if step_type == "action_log":
        return {"log_tag": "", "note": ""}
    raise ValueError(f"Unsupported flow step type: {step_type}.")


def _normalize_step_config(step_type: str, raw_config: dict[str, Any]) -> dict[str, Any]:
    config = dict(raw_config or {})
    if step_type == "receiver_rf":
        value = _normalize_text(config.get("rf_port"))
        if not value:
            raise ValueError("Receiver RF step requires an RF Port / Radio value.")
        return {"rf_port": value}
    if step_type == "receiver_aprsis":
        value = _normalize_text(config.get("aprsis_source"))
        if not value:
            raise ValueError("Receiver APRS-IS step requires an APRS-IS Source value.")
        return {"aprsis_source": value}
    if step_type == "filter_dupe":
        return {"window_sec": _normalize_number(config.get("window_sec"), label="Duplicate window", minimum=1)}
    if step_type == "filter_path":
        mode = _normalize_text(config.get("mode")).lower() or "allow"
        if mode not in {"allow", "deny"}:
            raise ValueError("Path filter mode must be allow or deny.")
        return {"mode": mode, "paths": _normalize_multiline_list(config.get("paths"))}
    if step_type == "filter_digi":
        mode = _normalize_text(config.get("mode")).lower() or "allow"
        if mode not in {"allow", "deny"}:
            raise ValueError("DIGI filter mode must be allow or deny.")
        return {"mode": mode, "digis": _normalize_multiline_list(config.get("digis"))}
    if step_type == "filter_callsign":
        mode = _normalize_text(config.get("mode")).lower() or "allow"
        if mode not in {"allow", "deny"}:
            raise ValueError("Callsign filter mode must be allow or deny.")
        return {"mode": mode, "callsigns": _normalize_multiline_list(config.get("callsigns"))}
    if step_type == "filter_packet_type":
        mode = _normalize_text(config.get("mode")).lower() or "allow"
        if mode not in {"allow", "deny"}:
            raise ValueError("Packet type filter mode must be allow or deny.")
        return {"mode": mode, "packet_types": _normalize_multiline_list(config.get("packet_types"))}
    if step_type == "filter_icon":
        mode = _normalize_text(config.get("mode")).lower() or "allow"
        if mode not in {"allow", "deny"}:
            raise ValueError("Icon filter mode must be allow or deny.")
        return {"mode": mode, "icons": _normalize_multiline_list(config.get("icons"))}
    if step_type == "filter_distance":
        return {"max_km": _normalize_number(config.get("max_km"), label="Max distance", minimum=1)}
    if step_type == "filter_rate_limit":
        return {"packets_per_minute": _normalize_number(config.get("packets_per_minute"), label="Packets per minute", minimum=1)}
    if step_type == "filter_rate_limit_per_callsign":
        return {"packets_per_minute": _normalize_number(config.get("packets_per_minute"), label="Packets per minute", minimum=1)}
    if step_type == "tx_rf":
        value = _normalize_text(config.get("rf_target"))
        if not value:
            raise ValueError("TX RF step requires an RF Target value.")
        return {"rf_target": value}
    if step_type == "tx_aprsis":
        value = _normalize_text(config.get("aprsis_target"))
        if not value:
            raise ValueError("TX APRS-IS step requires an APRS-IS Target value.")
        return {"aprsis_target": value}
    if step_type == "action_drop":
        return {"note": _normalize_text(config.get("note"))}
    if step_type == "action_log":
        return {"log_tag": _normalize_text(config.get("log_tag")), "note": _normalize_text(config.get("note"))}
    raise ValueError(f"Unsupported flow step type: {step_type}.")


def _step_ref_value(step_type: str, config: dict[str, Any]) -> str:
    field_name = STEP_TYPE_TO_REF_FIELD.get(step_type, "")
    if not field_name:
        return ""
    value = config.get(field_name, "")
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip())
    return _normalize_text(value)


def _step_summary(step_type: str, config: dict[str, Any]) -> str:
    if step_type == "receiver_rf":
        return f"RF port: {_normalize_text(config.get('rf_port')) or '-'}"
    if step_type == "receiver_aprsis":
        return f"APRS-IS source: {_normalize_text(config.get('aprsis_source')) or '-'}"
    if step_type == "filter_dupe":
        return f"Window: {config.get('window_sec', '-')!s} sec"
    if step_type == "filter_digi":
        digis = config.get("digis") or []
        return f"Mode: {config.get('mode', 'allow')}, digis: {len(digis)}"
    if step_type == "filter_path":
        paths = config.get("paths") or []
        return f"Mode: {config.get('mode', 'allow')}, paths: {len(paths)}"
    if step_type == "filter_callsign":
        callsigns = config.get("callsigns") or []
        return f"Mode: {config.get('mode', 'allow')}, callsigns: {len(callsigns)}"
    if step_type == "filter_packet_type":
        packet_types = config.get("packet_types") or []
        return f"Mode: {config.get('mode', 'allow')}, packet types: {', '.join(packet_types) if packet_types else 'none'}"
    if step_type == "filter_icon":
        icons = config.get("icons") or []
        return f"Mode: {config.get('mode', 'allow')}, icons: {', '.join(icons) if icons else 'none'}"
    if step_type == "filter_distance":
        return f"Max distance: {config.get('max_km', '-')!s} km"
    if step_type == "filter_rate_limit":
        return f"Rate: {config.get('packets_per_minute', '-')!s} pkt/min"
    if step_type == "filter_rate_limit_per_callsign":
        return f"Per callsign: {config.get('packets_per_minute', '-')!s} pkt/min"
    if step_type == "tx_rf":
        return f"RF target: {_normalize_text(config.get('rf_target')) or '-'}"
    if step_type == "tx_aprsis":
        return f"APRS-IS target: {_normalize_text(config.get('aprsis_target')) or '-'}"
    if step_type == "action_drop":
        note = _normalize_text(config.get("note"))
        return note or "Drop packet"
    if step_type == "action_log":
        log_tag = _normalize_text(config.get("log_tag"))
        note = _normalize_text(config.get("note"))
        parts = [part for part in (f"Tag: {log_tag}" if log_tag else "", note) if part]
        return " | ".join(parts) if parts else "Log packet"
    return ""


def get_digi_flow_type_meta() -> dict[str, dict[str, Any]]:
    return {
        step_type: {
            "category": meta["category"],
            "label": meta["label"],
            "badge": meta["badge"],
            "description": meta["description"],
            "config_fields": [dict(field) for field in meta["config_fields"]],
        }
        for step_type, meta in STEP_TYPE_META.items()
    }


def get_digi_flow_reference_options() -> dict[str, list[str]]:
    rf_rows = fetch_all("SELECT name FROM modems ORDER BY name COLLATE NOCASE ASC, id ASC")
    aprsis_rows = fetch_all("SELECT name FROM aprsis_servers ORDER BY name COLLATE NOCASE ASC, id ASC")
    return {
        "receiver_rf": [str(row["name"]) for row in rf_rows if row["name"]],
        "tx_rf": [str(row["name"]) for row in rf_rows if row["name"]],
        "receiver_aprsis": [str(row["name"]) for row in aprsis_rows if row["name"]],
        "tx_aprsis": [str(row["name"]) for row in aprsis_rows if row["name"]],
        "action_drop": ["drop"],
        "action_log": ["log-only"],
    }


def get_digi_flow_endpoint_options() -> dict[str, list[dict[str, str]]]:
    rf_rows = fetch_all("SELECT name FROM modems ORDER BY name COLLATE NOCASE ASC, id ASC")
    aprsis_rows = fetch_all("SELECT name FROM aprsis_servers ORDER BY name COLLATE NOCASE ASC, id ASC")
    source_options = [
        {"value": f"receiver_rf::{row['name']}", "label": str(row["name"]), "kind": "receiver_rf", "ref": str(row["name"])}
        for row in rf_rows
        if row["name"]
    ]
    source_options.extend(
        {
            "value": f"receiver_aprsis::{row['name']}",
            "label": str(row["name"]),
            "kind": "receiver_aprsis",
            "ref": str(row["name"]),
        }
        for row in aprsis_rows
        if row["name"]
    )
    target_options = [
        {"value": f"tx_rf::{row['name']}", "label": str(row["name"]), "kind": "tx_rf", "ref": str(row["name"])}
        for row in rf_rows
        if row["name"]
    ]
    target_options.extend(
        {
            "value": f"tx_aprsis::{row['name']}",
            "label": str(row["name"]),
            "kind": "tx_aprsis",
            "ref": str(row["name"]),
        }
        for row in aprsis_rows
        if row["name"]
    )
    target_options.append({"value": "action_log::log-only", "label": "Log Only", "kind": "action_log", "ref": "log-only"})
    return {"source": source_options, "target": target_options}


def _serialize_step_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    step = dict(row)
    try:
        config = json.loads(step.get("config_json") or "{}")
    except json.JSONDecodeError:
        config = {}
    step_type = _normalize_text(step.get("step_type"))
    step["config"] = config
    step["step_category"] = _step_category(step_type)
    step["step_label"] = STEP_TYPE_META[step_type]["label"]
    step["step_badge"] = STEP_TYPE_META[step_type]["badge"]
    step["config_summary"] = _step_summary(step_type, config)
    return step


def _serialize_flow_row(row: sqlite3.Row | dict[str, Any], steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    flow = dict(row)
    flow["enabled"] = int(flow.get("enabled") or 0)
    if steps is None:
        steps = get_digi_flow_steps(int(flow["id"]))
    flow["steps"] = steps
    flow["step_count"] = len(steps)
    flow["source_display"] = f"{flow.get('source_kind')}: {flow.get('source_ref')}"
    flow["target_display"] = f"{flow.get('target_kind')}: {flow.get('target_ref')}"
    return flow


def list_digi_flows() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT id, name, description, source_kind, source_ref, target_kind, target_ref, enabled, created_at, updated_at
        FROM digi_flows
        ORDER BY updated_at DESC, id DESC
        """
    )
    return [_serialize_flow_row(row, steps=get_digi_flow_steps(int(row["id"]))) for row in rows]


def get_digi_flow_steps(flow_id: int) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT id, flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
        FROM digi_flow_steps
        WHERE flow_id = ?
        ORDER BY step_order ASC, id ASC
        """,
        (flow_id,),
    )
    return [_serialize_step_row(row) for row in rows]


def get_digi_flow(flow_id: int) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT id, name, description, source_kind, source_ref, target_kind, target_ref, enabled, created_at, updated_at
        FROM digi_flows
        WHERE id = ?
        """,
        (flow_id,),
    )
    if row is None:
        return None
    return _serialize_flow_row(row)


def build_digi_flow_editor_payload(flow: dict[str, Any] | None = None) -> dict[str, Any]:
    if flow:
        return {
            "name": flow.get("name", ""),
            "description": flow.get("description", ""),
            "source_selector": f"{flow.get('source_kind')}::{flow.get('source_ref')}",
            "target_selector": f"{flow.get('target_kind')}::{flow.get('target_ref')}",
            "source_kind": flow.get("source_kind", "receiver_rf"),
            "source_ref": flow.get("source_ref", ""),
            "target_kind": flow.get("target_kind", "tx_rf"),
            "target_ref": flow.get("target_ref", ""),
            "enabled": int(flow.get("enabled") or 0),
            "steps": [
                {
                    "id": step.get("id"),
                    "step_type": step.get("step_type"),
                    "title": step.get("title"),
                    "enabled": int(step.get("enabled") or 0),
                    "config": dict(step.get("config") or {}),
                }
                for step in flow.get("steps", [])
            ],
        }
    return {
        "name": "",
        "description": "",
        "source_selector": "",
        "target_selector": "action_log::log-only",
        "source_kind": "receiver_rf",
        "source_ref": "",
        "target_kind": "action_log",
        "target_ref": "log-only",
        "enabled": 1,
        "steps": [
            {
                "step_type": "receiver_rf",
                "title": _default_step_title("receiver_rf"),
                "enabled": 1,
                "config": _default_step_config("receiver_rf"),
            },
            {
                "step_type": "action_log",
                "title": _default_step_title("action_log"),
                "enabled": 1,
                "config": _default_step_config("action_log", "log-only"),
            },
        ],
    }


def normalize_digi_flow_payload(payload: dict[str, Any], *, existing_flow_id: int | None = None) -> dict[str, Any]:
    name = _normalize_text(payload.get("name"))
    if not name:
        raise ValueError("Flow name is required.")
    description = _normalize_text(payload.get("description"))
    source_kind = _normalize_text(payload.get("source_kind"))
    target_kind = _normalize_text(payload.get("target_kind"))
    if source_kind not in SOURCE_STEP_TYPES:
        raise ValueError("Flow source must be one of the supported source step types.")
    if target_kind not in TARGET_STEP_TYPES:
        raise ValueError("Flow target must be one of the supported target step types.")
    source_ref = _normalize_text(payload.get("source_ref"))
    target_ref = _normalize_text(payload.get("target_ref"))
    if not source_ref:
        raise ValueError("Flow source reference is required.")
    if target_kind in {"tx_rf", "tx_aprsis"} and not target_ref:
        raise ValueError("Flow target reference is required.")

    raw_steps = payload.get("steps") or []
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("Flow must contain at least one source step and one target step.")

    normalized_steps: list[dict[str, Any]] = []
    source_count = 0
    target_count = 0
    for index, raw_step in enumerate(raw_steps, start=1):
        if not isinstance(raw_step, dict):
            raise ValueError("Invalid flow step payload.")
        step_type = _normalize_text(raw_step.get("step_type"))
        if step_type not in ALL_STEP_TYPES:
            raise ValueError(f"Unsupported flow step type: {step_type}.")
        category = _step_category(step_type)
        if category == "source":
            source_count += 1
        elif category == "target":
            target_count += 1

        config = _normalize_step_config(step_type, dict(raw_step.get("config") or {}))
        title = _normalize_text(raw_step.get("title")) or _default_step_title(step_type)
        normalized_steps.append(
            {
                "step_order": index,
                "step_type": step_type,
                "title": title,
                "enabled": _normalize_enabled(raw_step.get("enabled", 1)),
                "config": config,
            }
        )

    if source_count != 1:
        raise ValueError("Flow must contain exactly one source step.")
    if target_count != 1:
        raise ValueError("Flow must contain exactly one target step.")

    first_step = normalized_steps[0]
    last_step = normalized_steps[-1]
    if _step_category(first_step["step_type"]) != "source":
        raise ValueError("First flow step must be a source step.")
    if _step_category(last_step["step_type"]) != "target":
        raise ValueError("Last flow step must be a target step.")
    for middle_step in normalized_steps[1:-1]:
        if _step_category(middle_step["step_type"]) != "filter":
            raise ValueError("All middle flow steps must be filter steps.")

    first_ref = _step_ref_value(first_step["step_type"], first_step["config"])
    last_ref = _step_ref_value(last_step["step_type"], last_step["config"])
    if source_kind != first_step["step_type"] or source_ref != first_ref:
        raise ValueError("Flow source must match the first step type and reference.")
    if target_kind != last_step["step_type"] or target_ref != last_ref:
        raise ValueError("Flow target must match the last step type and reference.")

    duplicate = fetch_one(
        """
        SELECT id
        FROM digi_flows
        WHERE source_kind = ?
          AND source_ref = ?
          AND target_kind = ?
          AND target_ref = ?
          AND (? IS NULL OR id <> ?)
        LIMIT 1
        """,
        (source_kind, source_ref, target_kind, target_ref, existing_flow_id, existing_flow_id),
    )
    if duplicate is not None:
        raise ValueError("A DIGI Flow with the same source and target already exists.")

    return {
        "name": name,
        "description": description,
        "source_kind": source_kind,
        "source_ref": source_ref,
        "target_kind": target_kind,
        "target_ref": target_ref,
        "enabled": _normalize_enabled(payload.get("enabled", 0)),
        "steps": normalized_steps,
    }


def create_digi_flow(payload: dict[str, Any]) -> int:
    normalized = normalize_digi_flow_payload(payload)
    timestamp = utc_now()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO digi_flows (
                name, description, source_kind, source_ref, target_kind, target_ref, enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["name"],
                normalized["description"],
                normalized["source_kind"],
                normalized["source_ref"],
                normalized["target_kind"],
                normalized["target_ref"],
                normalized["enabled"],
                timestamp,
                timestamp,
            ),
        )
        flow_id = int(cursor.lastrowid)
        for step in normalized["steps"]:
            connection.execute(
                """
                INSERT INTO digi_flow_steps (
                    flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    flow_id,
                    step["step_order"],
                    step["step_type"],
                    step["title"],
                    step["enabled"],
                    json.dumps(step["config"], separators=(",", ":"), ensure_ascii=True),
                    timestamp,
                    timestamp,
                ),
            )
    log_event("INFO", "config", f"Created DIGI Flow #{flow_id}")
    return flow_id


def update_digi_flow(flow_id: int, payload: dict[str, Any]) -> None:
    if get_digi_flow(flow_id) is None:
        raise ValueError("DIGI Flow not found.")
    normalized = normalize_digi_flow_payload(payload, existing_flow_id=flow_id)
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE digi_flows
            SET name = ?,
                description = ?,
                source_kind = ?,
                source_ref = ?,
                target_kind = ?,
                target_ref = ?,
                enabled = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                normalized["name"],
                normalized["description"],
                normalized["source_kind"],
                normalized["source_ref"],
                normalized["target_kind"],
                normalized["target_ref"],
                normalized["enabled"],
                timestamp,
                flow_id,
            ),
        )
        connection.execute("DELETE FROM digi_flow_steps WHERE flow_id = ?", (flow_id,))
        for step in normalized["steps"]:
            connection.execute(
                """
                INSERT INTO digi_flow_steps (
                    flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    flow_id,
                    step["step_order"],
                    step["step_type"],
                    step["title"],
                    step["enabled"],
                    json.dumps(step["config"], separators=(",", ":"), ensure_ascii=True),
                    timestamp,
                    timestamp,
                ),
            )
    log_event("INFO", "config", f"Updated DIGI Flow #{flow_id}")


def delete_digi_flow(flow_id: int) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM digi_flows WHERE id = ?", (flow_id,))
    log_event("INFO", "config", f"Deleted DIGI Flow #{flow_id}")


def set_digi_flow_enabled(flow_id: int, enabled: bool) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE digi_flows
            SET enabled = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (1 if enabled else 0, utc_now(), flow_id),
        )
    log_event("INFO", "config", f"Set DIGI Flow #{flow_id} enabled={1 if enabled else 0}")


def safe_create_digi_flow(payload: dict[str, Any]) -> tuple[int | None, str | None]:
    try:
        return create_digi_flow(payload), None
    except ValueError as exc:
        return None, str(exc)
    except sqlite3.IntegrityError:
        return None, "A DIGI Flow with the same source and target already exists."


def safe_update_digi_flow(flow_id: int, payload: dict[str, Any]) -> str | None:
    try:
        update_digi_flow(flow_id, payload)
    except ValueError as exc:
        return str(exc)
    except sqlite3.IntegrityError:
        return "A DIGI Flow with the same source and target already exists."
    return None
