from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse

from app.dependencies import get_current_user, require_roles
from app.db import (
    DEFAULT_EVENT_LOG_KEEP_ROWS,
    DEFAULT_TRAFFIC_RETENTION_MINUTES,
    EVENT_LOG_DEBUG_ENABLED_SETTING_KEY,
    EVENT_LOG_MIN_LEVEL_SETTING_KEY,
    RUNTIME_MAINTENANCE_RESET_TABLES,
    TRAFFIC_RETENTION_ALLOWED_MINUTES,
    TRAFFIC_RETENTION_MINUTES_SETTING_KEY,
    VACUUM_RECOMMEND_FREE_BYTES_MIN,
    VACUUM_RECOMMEND_FREE_RATIO_MIN,
    create_system_job,
    database_maintenance_snapshot,
    event_log_levels_at_or_above,
    fetch_one,
    fetch_system_job,
    get_event_log_debug_enabled,
    get_event_log_min_level,
    get_app_setting,
    get_traffic_retention_minutes,
    log_event,
    mark_system_job_error,
    mark_system_job_running,
    mark_unreported_system_job_error,
    normalize_event_log_level,
    normalize_traffic_retention_minutes,
    reset_runtime_operational_data,
    set_app_setting,
    vacuum_database,
)
from app.i18n import get_app_language, get_translator, normalize_language, SUPPORTED_LANGUAGE_CODES
from app.models import UserIdentity
from app.sections import SECTION_DEFINITIONS
from app.services.beacon_pathing import (
    BEACON_INTERVAL_MODE_FIXED,
    BEACON_INTERVAL_MODE_PROPORTIONAL,
    build_proportional_schedule_lines,
    classify_beacon_path,
    evaluate_beacon_health,
    normalize_beacon_interval_mode,
)
from app.services.content import (
    APRS_SYMBOL_SET_LEGACY,
    APRS_SYMBOL_SET_MODERN,
    APRS_SYMBOL_SET_SETTING_KEY,
    dashboard_home_data,
    delete_section_row,
    get_active_tnc_interfaces,
    get_aprs_symbol_icon_path,
    get_aprs_symbol_set,
    get_recent_station_packets,
    heard_stations,
    has_enabled_modem_interface,
    get_section_row,
    get_section_rows,
    get_related_ssids,
    get_rf_heard_station_snapshots,
    get_visible_station_snapshots,
    recent_station_outbound_jobs,
    recent_object_outbound_jobs,
    recent_bulletin_outbound_jobs,
    get_station_detail,
    get_station_settings,
    recent_event_logs,
    safe_update_station_settings,
    station_summary,
    traffic_snapshot as get_traffic_snapshot,
    safe_create_section_row,
    safe_update_section_row,
)
from app.services.tx_scope import ALL_ACTIVE_INTERFACE_OPTION_VALUE, INTERNAL_TX_INTERFACE_OPTION_VALUE
from app.services.mqtt_url import OPENWEBRX_MQTT_MODEM_TYPE, mask_mqtt_url
from app.services.alarm_groups import (
    APRS_ALARM_LEVEL_THRESHOLDS,
    build_automatic_aprsis_alarm_filter,
    get_aprs_alarm_enabled,
    get_aprs_alarm_category_thresholds,
    get_aprs_alarm_groups,
    get_global_alarm_level_threshold,
    get_map_alarm_level_threshold,
    normalize_aprs_alarm_category_thresholds,
    normalize_aprs_alarm_groups,
    normalize_aprs_alarm_level_threshold,
    save_aprs_alarm_category_thresholds,
    save_aprs_alarm_enabled,
    save_aprs_alarm_groups,
    save_global_alarm_level_threshold,
    save_map_alarm_level_threshold,
)
from app.services.alert_event_icons import ALERT_EVENT_CATEGORIES
from app.services.digi_flows import (
    FILTER_STEP_TYPES,
    SOURCE_STEP_TYPES,
    TARGET_STEP_TYPES,
    build_digi_flow_editor_payload,
    delete_digi_flow,
    get_digi_flow_execution_summaries,
    get_digi_flow_event_log,
    get_digi_flow_endpoint_options,
    get_digi_flow,
    get_digi_flow_reference_options,
    get_digi_flow_type_meta,
    has_enabled_local_tx_aprsis_flow,
    list_digi_flows,
    safe_move_digi_flow,
    safe_create_digi_flow,
    safe_update_digi_flow,
    set_digi_flow_enabled,
)
from app.services.messages import (
    clear_message_inbox,
    create_or_update_conversation,
    delete_conversation as delete_message_conversation,
    get_messages_page_data as get_live_messages_page_data,
    get_effective_message_target_groups,
    get_unread_inbox_count,
    mark_conversation_read,
    queue_outgoing_message,
    reconcile_effective_message_group_conversations,
    retry_failed_message,
    save_message_settings,
    update_conversation_path,
)
from app.services.notifications import (
    delete_notification_radar_rule,
    delete_notification_transport,
    get_notifications_page_data,
    safe_save_notification_radar_rule,
    safe_save_notification_settings,
    safe_save_notification_transport,
    test_notification_transport,
)
from app.services.alerts import (
    delete_alert,
    delete_alerts,
    get_alert,
    get_traffic_frame,
    list_alerts,
    mute_alert,
    unmute_alert,
)
from app.services.own_alerts import (
    cancel_station_aprs_alert,
    cancel_own_alert,
    create_own_alert,
    get_own_alert_area_options,
    get_own_alert_compose_context,
    preview_own_alert,
    send_own_alert_now,
)
from app.services.band_condition import (
    get_band_condition_history,
    get_band_condition_page_data,
    get_band_condition_snapshot,
)
from app.services.aprsis import (
    aprsis_runtime_badge,
    get_aprsis_config,
    get_aprsis_diagnostics,
    get_aprsis_runtime_status,
    normalize_aprsis_config_payload,
    save_aprsis_config,
    safe_save_aprsis_config,
)
from app.services.aprs_device_identification import (
    get_aprs_device_identification_status,
    refresh_aprs_device_identification_cache,
)
from app.services.core_client import restart_core_traffic_monitor
from app.services.radio_activity import (
    get_dashboard_radio_activity,
    get_traffic_direct_heard_statistics,
    get_traffic_devices_statistics,
    get_traffic_statistics,
    get_traffic_users_statistics,
)
from app.services.config_backup import (
    build_configuration_backup_filename,
    export_configuration_backup_bytes,
    safe_import_configuration_backup,
)
from app.services.map_service import (
    COVERAGE_FILL_OPACITY_SETTING_KEY,
    DEFAULT_COVERAGE_FILL_OPACITY_PERCENT,
    get_map_source,
    list_map_sources,
    get_coverage_fill_opacity_percent,
    get_map_alert_areas_payload,
    get_map_page_config,
    get_map_mobile_tracks_payload,
    get_map_station_details_payload,
    get_map_station_markers_payload,
    get_map_station_payload,
    get_alert_detail_map_config,
    safe_move_map_source,
    safe_delete_map_source,
    safe_save_map_source,
    safe_set_default_map_source,
    get_station_detail_map_config,
    get_station_detail_track_payload,
    normalize_coverage_fill_opacity_percent,
)
from app.services.map_tile_proxy import MapTileProxyError, resolve_map_tile, safe_clear_map_source_cache
from app.services.outbound import enqueue_beacon_job, enqueue_message_job, enqueue_object_job, enqueue_status_job
from app.services.system import (
    container_system_actions_disabled_message,
    current_update_channel,
    current_gui_version,
    is_container_mode,
    latest_gui_version,
    list_update_channels,
    read_update_log,
    save_update_channel,
    start_application_update_job,
    start_host_poweroff_job,
    start_host_reboot_job,
    start_service_restart_job,
)
from app.services.traffic_stream import TrafficSnapshotBroadcaster, TrafficStreamCapacityError
from app.services.traffic_source import APRSIS_MODEM_TYPE
from app.template_helpers import build_template_context
from app.ui_palette import get_ui_palette_label, get_ui_palette_options, is_supported_ui_palette, normalize_ui_palette
from app.services.wx import (
    delete_wx_source,
    discover_wx_source_items,
    get_wx_page_data,
    refresh_single_wx_mapping,
    safe_enqueue_wx_outbound,
    safe_refresh_wx_runtime,
    safe_save_wx_config,
    safe_save_wx_mappings,
    safe_save_wx_source,
    test_wx_source_connection,
)

router = APIRouter()
_REPO_ROOT_DIR = Path(__file__).resolve().parents[2]
_HELP_ROOT_DIR = _REPO_ROOT_DIR / "help"
_CHANGELOG_FILES_BY_LANGUAGE: dict[str, Path] = {
    "pl": _REPO_ROOT_DIR / "changelog.md",
    "en": _REPO_ROOT_DIR / "changelog.en.md",
    "es": _REPO_ROOT_DIR / "changelog.es.md",
    "de": _REPO_ROOT_DIR / "changelog.de.md",
}
_CHANGELOG_FALLBACK_LANGUAGE_ORDER: tuple[str, ...] = ("pl", "en")
_HELP_FALLBACK_LANGUAGE_ORDER: tuple[str, ...] = ("en",)
_CONFIG_BACKUP_MAX_BYTES = 5 * 1024 * 1024
EVENT_LOG_MIN_LEVEL_OPTIONS: tuple[str, ...] = ("INFO", "WARNING", "ERROR")
EVENT_LOG_VIEW_LEVEL_OPTIONS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR")
DATABASE_MAINTENANCE_TABLE_LABELS: dict[str, str] = {
    "event_logs": "Event logs",
    "traffic_frames": "Traffic frames",
    "digi_flow_event_log": "DIGI flow event log",
    "aprsis_igate_rf_heard": "IGate RF heard state",
    "aprsis_igate_station_state": "IGate Internet station state",
    "aprsis_igate_pending_position": "IGate pending sender positions",
    "traffic_device_station_device_hourly": "Traffic devices hourly stats",
    "radio_activity_5m": "Radio activity buckets",
    "aprsis_uplink_minute_stats": "APRS-IS uplink minute stats",
    "aprsis_uplink_stats": "APRS-IS uplink counters",
    "wx_runtime_cache": "WX runtime cache",
    "band_condition_audibility_buckets": "Band condition audibility buckets",
    "band_condition_activity_station_buckets": "Band condition station buckets",
    "band_condition_activity_buckets": "Band condition activity buckets",
    "band_condition_station_hours": "Band condition hourly station observations",
    "band_condition_station_profiles": "Band condition learned station profiles",
    "band_condition_hourly": "Band condition hourly history",
}


def _translate(message: object) -> str:
    return get_translator(get_app_language())(message)


def _system_job_process_is_running(pid: object) -> bool:
    try:
        normalized_pid = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if normalized_pid <= 0:
        return False
    try:
        os.kill(normalized_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _container_mode_system_action_denied_response() -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": _translate(container_system_actions_disabled_message())},
        status_code=status.HTTP_409_CONFLICT,
    )


def _format_size_bytes(size_bytes: int) -> str:
    value = float(max(0, int(size_bytes)))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024
    return "0 B"


def _format_ratio_percent(ratio: float) -> str:
    normalized = max(0.0, float(ratio))
    return f"{normalized * 100:.1f}%"


def _section_template_context(
    request: Request,
    current_user: UserIdentity,
    slug: str,
    flash: str | None = None,
    edit_row: dict | None = None,
    *,
    flash_success: bool = False,
    form_data: dict[str, object] | None = None,
    initial_modem_type: str | None = None,
) -> dict:
    definition = SECTION_DEFINITIONS[slug]
    context = build_template_context(
        request,
        page_title=definition.title,
        current_user=current_user,
        active_nav=definition.nav_key,
        section=definition,
        rows=get_section_rows(slug),
        flash=flash,
        can_edit=current_user.role in definition.create_roles,
        edit_row=edit_row,
        flash_success=flash_success,
    )
    if slug == "modems":
        aprsis_config = get_aprsis_config()
        modem_form_data: dict[str, object] = dict(edit_row or {})
        if form_data:
            modem_form_data.update(form_data)
        if not edit_row and not form_data and initial_modem_type:
            modem_form_data["modem_type"] = initial_modem_type
        modem_form_data.setdefault("modem_type", "SERIALL")
        modem_form_data.setdefault("aprsis_server", aprsis_config["server"])
        modem_form_data.setdefault("aprsis_port", aprsis_config["port"])
        modem_form_data.setdefault(
            "aprsis_login",
            "" if aprsis_config["login_is_default"] else aprsis_config["login"],
        )
        modem_form_data.setdefault(
            "aprsis_passcode",
            "" if aprsis_config["passcode_is_default"] else aprsis_config["passcode"],
        )
        aprsis_runtime = get_aprsis_runtime_status()
        context.update(
            {
                "modem_form_data": modem_form_data,
                "aprsis_config": aprsis_config,
                "aprsis_runtime": aprsis_runtime,
                "aprsis_diagnostics": get_aprsis_diagnostics(),
                "aprsis_runtime_badge": aprsis_runtime_badge(aprsis_runtime.get("status", "")),
            }
        )
    if slug in {"objects", "items"}:
        context.update(
            {
                "map_picker_config": get_map_page_config(root_path=request.scope.get("root_path", "")),
                "symbol_table_options": [
                    {"value": "/", "label": "Primary (/)"},
                    {"value": "\\", "label": "Alternate (\\)"},
                ],
                "symbol_code_options": [
                    {
                        "value": chr(code),
                        "label": chr(code),
                        "primary_icon": get_aprs_symbol_icon_path(f"/{chr(code)}"),
                        "alternate_icon": get_aprs_symbol_icon_path(f"\\{chr(code)}"),
                    }
                    for code in range(33, 127)
                ],
            }
        )
    if slug == "objects":
        context["section_tx_log_rows"] = recent_object_outbound_jobs(limit=20)
    elif slug == "bulletins":
        context["section_tx_log_rows"] = recent_bulletin_outbound_jobs(limit=20)
    return context


def _section_edit_redirect(request: Request, slug: str, record_id: int) -> RedirectResponse:
    return RedirectResponse(
        url=_path(request, f"/{slug}?edit={record_id}"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _station_detail_context(callsign: str, unit_system: str, *, root_path: str = "") -> dict | None:
    snapshots = get_visible_station_snapshots()
    detail = get_station_detail(callsign, unit_system=unit_system, snapshots=snapshots)
    if detail is None:
        return None
    related_ssids = get_related_ssids(detail["base_callsign"], snapshots=snapshots)
    for item in related_ssids:
        item["is_current"] = item["display_callsign"].casefold() == detail["display_callsign"].casefold()
    station_track = get_station_detail_track_payload(detail["display_callsign"])
    station_map_config = get_station_detail_map_config(detail, root_path=root_path)
    station_map_config["track_points"] = station_track.get("points", [])
    return {
        "station": detail,
        "station_map_config": station_map_config,
        "station_track": station_track,
        "recent_packets": get_recent_station_packets(detail["display_callsign"], snapshot=detail),
        "related_ssids": related_ssids,
    }


def _path(request: Request, suffix: str) -> str:
    return f"{request.scope.get('root_path', '')}{suffix}"


def _aprsis_interface_settings_path() -> str:
    aprsis_interface = fetch_one(
        "SELECT id FROM modems WHERE UPPER(modem_type) = 'APRSIS' ORDER BY id ASC LIMIT 1"
    )
    if aprsis_interface is None:
        return "/settings/modems?new_type=APRSIS"
    return f"/settings/modems?edit={int(aprsis_interface['id'])}"


def _safe_positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed >= 0 else 0


def _read_changelog_markdown(language: str | None = None) -> str:
    resolved_language = normalize_language(language if language is not None else get_app_language())
    language_order = (resolved_language, *_CHANGELOG_FALLBACK_LANGUAGE_ORDER)
    checked_paths: list[Path] = []
    for language_code in language_order:
        path = _CHANGELOG_FILES_BY_LANGUAGE.get(language_code)
        if path is None or path in checked_paths:
            continue
        checked_paths.append(path)
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            continue
    return "# Changelog\n\nUnable to read changelog file."


def _sanitize_help_relative_markdown_path(value: str | None) -> PurePosixPath | None:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return None
    try:
        path = PurePosixPath(text)
    except Exception:
        return None
    if path.is_absolute() or not path.parts:
        return None
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    if path.suffix.lower() != ".md":
        return None
    return PurePosixPath(*path.parts)


def _sanitize_help_page_identifier(value: str | None) -> PurePosixPath | None:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return None
    try:
        path = PurePosixPath(text)
    except Exception:
        return None
    if path.is_absolute() or not path.parts:
        return None
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    if path.suffix:
        return None
    return PurePosixPath(*path.parts)


def _resolve_help_file_path(relative_path: PurePosixPath) -> Path | None:
    candidate = (_HELP_ROOT_DIR / Path(*relative_path.parts)).resolve(strict=False)
    try:
        candidate.relative_to(_HELP_ROOT_DIR.resolve(strict=False))
    except ValueError:
        return None
    if candidate.suffix.lower() != ".md":
        return None
    return candidate


def _read_help_markdown_file(relative_path: PurePosixPath) -> tuple[str, str] | None:
    file_path = _resolve_help_file_path(relative_path)
    if file_path is None or not file_path.is_file():
        return None
    try:
        return relative_path.as_posix(), file_path.read_text(encoding="utf-8")
    except OSError:
        return None


def _build_help_markdown_candidates(page: str | None, language: str | None = None) -> list[PurePosixPath]:
    page_path = _sanitize_help_page_identifier(page)
    if page_path is None:
        return []
    resolved_language = normalize_language(language if language is not None else get_app_language())
    language_order = (resolved_language, *_HELP_FALLBACK_LANGUAGE_ORDER)
    relative_candidates: list[PurePosixPath] = []
    for language_code in language_order:
        relative_path = page_path.parent / f"{page_path.name}.{language_code}.md"
        if relative_path not in relative_candidates:
            relative_candidates.append(relative_path)
    return relative_candidates


def _read_help_markdown(
    *,
    page: str | None = None,
    path: str | None = None,
    language: str | None = None,
) -> tuple[str, str] | None:
    if str(path or "").strip():
        relative_path = _sanitize_help_relative_markdown_path(path)
        if relative_path is None:
            return None
        return _read_help_markdown_file(relative_path)
    for relative_path in _build_help_markdown_candidates(page, language=language):
        resolved = _read_help_markdown_file(relative_path)
        if resolved is not None:
            return resolved
    return None


def _help_markdown_title(markdown: str, fallback: str) -> str:
    for raw_line in str(markdown or "").splitlines():
        line = raw_line.strip()
        if line.startswith("# "):
            return line[2:].strip() or fallback
    return fallback


def _parse_digi_flow_form_payload(form_data: Any) -> dict[str, object]:
    source_selector = str(form_data.get("source_selector") or "").strip()
    target_selector = str(form_data.get("target_selector") or "").strip()
    if "::" not in source_selector:
        raise ValueError("Source interface is required.")
    if "::" not in target_selector:
        raise ValueError("Target interface is required.")
    source_kind, source_ref = source_selector.split("::", 1)
    target_kind, target_ref = target_selector.split("::", 1)
    raw_steps_json = str(form_data.get("steps_json") or "[]")
    try:
        raw_steps = json.loads(raw_steps_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid flow steps payload.") from exc
    if not isinstance(raw_steps, list):
        raise ValueError("Invalid flow steps payload.")
    return {
        "name": str(form_data.get("name") or "").strip(),
        "description": str(form_data.get("description") or "").strip(),
        "source_selector": source_selector,
        "target_selector": target_selector,
        "source_kind": source_kind,
        "source_ref": source_ref,
        "target_kind": target_kind,
        "target_ref": target_ref,
        "enabled": 1 if form_data.get("enabled") else 0,
        "steps": raw_steps,
    }


def _digi_flow_editor_context(
    request: Request,
    current_user: UserIdentity,
    *,
    form_data: dict[str, object],
    flow_id: int | None = None,
    flash: str | None = None,
    flash_success: bool = False,
) -> dict[str, object]:
    station_form_options = _station_form_options()
    return build_template_context(
        request,
        page_title="Packet Routing Editor" if flow_id else "New Packet Routing Flow",
        current_user=current_user,
        active_nav="digi-flows",
        flow_id=flow_id,
        form_data=form_data,
        type_meta=get_digi_flow_type_meta(),
        endpoint_options=get_digi_flow_endpoint_options(
            selected_source_selector=str(form_data.get("source_selector") or "").strip() or None,
            selected_target_selector=str(form_data.get("target_selector") or "").strip() or None,
            current_flow_id=flow_id,
        ),
        reference_options=get_digi_flow_reference_options(),
        source_step_types=SOURCE_STEP_TYPES,
        filter_step_types=FILTER_STEP_TYPES,
        target_step_types=TARGET_STEP_TYPES,
        flow_execution_summaries=get_digi_flow_execution_summaries(flow_id, execution_limit=10) if flow_id is not None else [],
        map_picker_config=get_map_page_config(root_path=request.scope.get("root_path", "")),
        symbol_table_options=station_form_options["symbol_table_options"],
        symbol_code_options=station_form_options["symbol_code_options"],
        flash=flash,
        flash_success=flash_success,
    )


def _dashboard_band_condition_card() -> dict | None:
    snapshot = get_band_condition_snapshot()
    bands = snapshot.get("bands") or []
    if not bands:
        return None
    preferred = next((item for item in bands if item.get("band") == "2m"), None)
    return preferred or bands[0]


def _station_form_options(
) -> dict[str, list[dict[str, str | int]]]:
    interface_options = [
        {
            "value": str(item["id"]),
            "label": f"{item['name']} ({item['modem_type']}, {item['band'] or '-'})",
        }
        for item in get_active_tnc_interfaces()
    ]
    interface_options.append({"value": ALL_ACTIVE_INTERFACE_OPTION_VALUE, "label": "Transmit on all active interfaces"})
    interface_options.append({"value": INTERNAL_TX_INTERFACE_OPTION_VALUE, "label": "Internal TX"})
    return {
        "interface_options": [{"value": "", "label": "Select interface"}] + interface_options,
        "ssid_options": [{"value": "", "label": "Select SSID"}] + [{"value": str(value), "label": str(value)} for value in range(16)],
        "symbol_table_options": [
            {"value": "/", "label": "Primary (/)"},
            {"value": "\\", "label": "Alternate (\\)"},
        ],
        "symbol_overlay_options": (
            [{"value": "", "label": "None"}]
            + [{"value": str(value), "label": str(value)} for value in range(10)]
            + [{"value": chr(code), "label": chr(code)} for code in range(ord("A"), ord("Z") + 1)]
        ),
        "symbol_code_options": [
            {
                "value": chr(code),
                "label": chr(code),
                "primary_icon": get_aprs_symbol_icon_path(f"/{chr(code)}"),
                "alternate_icon": get_aprs_symbol_icon_path(f"\\{chr(code)}"),
            }
            for code in range(33, 127)
        ],
        "beacon_interval_options": [{"value": value, "label": f"{value}m"} for value in (15, 30, 45, 60)],
        "beacon_position_interval_options": (
            [{"value": str(value), "label": f"{value}m"} for value in (15, 30, 45, 60)]
            + [{"value": BEACON_INTERVAL_MODE_PROPORTIONAL, "label": "Proportional Path"}]
        ),
    }


def _station_page_context(
    request: Request,
    current_user: UserIdentity,
    *,
    flash: str | None = None,
    flash_success: bool = True,
    station: dict | None = None,
) -> dict:
    resolved_station = dict(station or get_station_settings())
    station_form_options = _station_form_options()
    internal_tx_routing_active = has_enabled_local_tx_aprsis_flow()
    raw_interval_value = str(resolved_station.get("beacon_interval_minutes") or "").strip().lower()
    interval_mode = normalize_beacon_interval_mode(
        resolved_station.get("beacon_interval_mode"),
        default=BEACON_INTERVAL_MODE_FIXED,
    )
    if raw_interval_value == BEACON_INTERVAL_MODE_PROPORTIONAL:
        interval_mode = BEACON_INTERVAL_MODE_PROPORTIONAL
    resolved_station["beacon_interval_mode"] = interval_mode

    interval_minutes: int | None = None
    try:
        interval_minutes = int(str(resolved_station.get("beacon_interval_minutes") or "").strip())
    except ValueError:
        interval_minutes = None

    beacon_health = evaluate_beacon_health(
        beacon_interval_mode=interval_mode,
        beacon_interval_minutes=interval_minutes,
        beacon_path=str(resolved_station.get("beacon_path") or ""),
    )
    beacon_path_value = str(resolved_station.get("beacon_path") or "")
    beacon_path_classification = classify_beacon_path(beacon_path_value)
    beacon_schedule_lines = build_proportional_schedule_lines(beacon_path_value)

    return build_template_context(
        request,
        page_title="My Settings",
        current_user=current_user,
        active_nav="station",
        station=resolved_station,
        can_edit=current_user.role in {"admin", "operator"},
        flash=flash,
        flash_success=flash_success,
        beacon_log_rows=recent_station_outbound_jobs(limit=20),
        beacon_health=beacon_health,
        beacon_proportional_schedule_lines=beacon_schedule_lines,
        beacon_proportional_schedule_path=beacon_path_classification.get("normalized_path", ""),
        internal_tx_routing_active=internal_tx_routing_active,
        map_picker_config=get_map_page_config(root_path=request.scope.get("root_path", "")),
        **station_form_options,
    )


def _wx_page_context(
    request: Request,
    current_user: UserIdentity,
    *,
    flash: str | None = None,
    flash_success: bool = True,
    edit_source_id: int | None = None,
    source_discovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_template_context(
        request,
        page_title="WX",
        current_user=current_user,
        active_nav="wx",
        flash=flash,
        flash_success=flash_success,
        can_edit=current_user.role in {"admin", "operator"},
        map_picker_config=get_map_page_config(root_path=request.scope.get("root_path", "")),
        interface_options=_station_form_options()["interface_options"],
        **get_wx_page_data(edit_source_id=edit_source_id, source_discovery=source_discovery),
    )


def _notification_transport_form_from_payload(payload: dict[str, Any], *, transport_id: int | None) -> dict[str, Any]:
    timeout_value = payload.get("timeout_s")
    return {
        "id": transport_id,
        "name": str(payload.get("name") or ""),
        "transport_type": str(payload.get("transport_type") or ""),
        "enabled": bool(payload.get("enabled")),
        "url": str(payload.get("url") or ""),
        "secret_header_name": str(payload.get("secret_header_name") or ""),
        "secret_token": "",
        "bot_token": "",
        "chat_id": str(payload.get("chat_id") or ""),
        "timeout_s": str(timeout_value) if timeout_value not in {None, ""} else "5",
    }


def _notification_radar_rule_form_from_payload(payload: dict[str, Any], *, rule_id: int | None) -> dict[str, Any]:
    distance_value = payload.get("distance_m")
    return {
        "id": rule_id,
        "enabled": bool(payload.get("enabled")),
        "pattern": str(payload.get("pattern") or ""),
        "distance_m": str(distance_value) if distance_value not in {None, ""} else "",
    }


def _notifications_page_context(
    request: Request,
    current_user: UserIdentity,
    *,
    flash: str | None = None,
    flash_success: bool = True,
    edit_transport_id: int | None = None,
    edit_rule_id: int | None = None,
    notification_transport_form: dict[str, Any] | None = None,
    notification_radar_rule_form: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = get_notifications_page_data(edit_transport_id=edit_transport_id, edit_rule_id=edit_rule_id)
    if notification_transport_form is not None:
        context["notification_transport_form"] = notification_transport_form
    if notification_radar_rule_form is not None:
        context["notification_radar_rule_form"] = notification_radar_rule_form
    return build_template_context(
        request,
        page_title="Notifications",
        current_user=current_user,
        active_nav="notifications",
        flash=flash,
        flash_success=flash_success,
        can_manage_notifications=current_user.role in {"admin", "operator"},
        **context,
    )


def _map_source_checkbox(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"1", "true", "on", "yes"}


def _normalize_event_log_min_level(value: Any) -> str:
    normalized = normalize_event_log_level(value, default=get_event_log_min_level())
    if normalized not in EVENT_LOG_MIN_LEVEL_OPTIONS:
        return "INFO"
    return normalized


def _normalize_traffic_retention_minutes_option(value: Any) -> int:
    normalized = normalize_traffic_retention_minutes(value)
    if normalized not in TRAFFIC_RETENTION_ALLOWED_MINUTES:
        return DEFAULT_TRAFFIC_RETENTION_MINUTES
    return normalized


def _format_traffic_retention_minutes_option(value: int) -> str:
    hours, minutes = divmod(int(value), 60)
    if minutes == 0:
        return f"{hours}h"
    return f"{hours}h {minutes}m"


def _empty_map_source_form() -> dict[str, Any]:
    return {
        "record_id": None,
        "name": "",
        "url_template": "",
        "attribution": "",
        "min_zoom": 0,
        "max_zoom": 19,
        "enabled": True,
        "local_cache_enabled": False,
        "is_default": False,
        "notes": "",
    }


def _map_source_form_from_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": int(source.get("id") or 0),
        "name": str(source.get("name") or ""),
        "url_template": str(source.get("url_template") or ""),
        "attribution": str(source.get("attribution") or ""),
        "min_zoom": int(source.get("min_zoom") or 0),
        "max_zoom": int(source.get("max_zoom") or 19),
        "enabled": bool(source.get("enabled")),
        "local_cache_enabled": bool(source.get("local_cache_enabled")),
        "is_default": bool(source.get("is_default")),
        "notes": str(source.get("notes") or ""),
    }


def _map_source_form_from_payload(payload: dict[str, Any], *, record_id: int | None) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "name": str(payload.get("name") or "").strip(),
        "url_template": str(payload.get("url_template") or "").strip(),
        "attribution": str(payload.get("attribution") or "").strip(),
        "min_zoom": str(payload.get("min_zoom") or "").strip() or "0",
        "max_zoom": str(payload.get("max_zoom") or "").strip() or "19",
        "enabled": _map_source_checkbox(payload.get("enabled")),
        "local_cache_enabled": _map_source_checkbox(payload.get("local_cache_enabled")),
        "is_default": _map_source_checkbox(payload.get("is_default")),
        "notes": str(payload.get("notes") or "").strip(),
    }


def _settings_page_context(
    request: Request,
    current_user: UserIdentity,
    *,
    latest_version_result: dict | None = None,
    flash: str | None = None,
    flash_success: bool = True,
    current_language: str | None = None,
    current_default_units: str | None = None,
    current_ui_palette: str | None = None,
    current_aprs_symbol_set: str | None = None,
    map_source_edit_id: int | None = None,
    map_source_form: dict[str, Any] | None = None,
) -> dict:
    container_mode = is_container_mode()
    station_settings = get_station_settings()
    database_vacuum_blocked = has_enabled_modem_interface()
    db_maintenance_snapshot = database_maintenance_snapshot()
    tracked_row_counts = dict(db_maintenance_snapshot.get("tracked_row_counts") or {})
    reset_targets: list[dict[str, Any]] = []
    for table_name in RUNTIME_MAINTENANCE_RESET_TABLES:
        if table_name not in tracked_row_counts:
            continue
        reset_targets.append(
            {
                "table_name": table_name,
                "label": DATABASE_MAINTENANCE_TABLE_LABELS.get(table_name, table_name),
                "row_count": int(tracked_row_counts.get(table_name) or 0),
            }
        )
    reset_total_rows = sum(int(row.get("row_count") or 0) for row in reset_targets)
    db_quick_check = str(db_maintenance_snapshot.get("quick_check") or "unknown").strip()
    db_quick_check_ok = db_quick_check.lower() == "ok"
    db_vacuum_recommended = bool(db_maintenance_snapshot.get("vacuum_recommended"))
    if not db_quick_check_ok:
        db_vacuum_recommendation = "Integrity check returned issues. Investigate before maintenance operations."
    elif db_vacuum_recommended and database_vacuum_blocked:
        db_vacuum_recommendation = "Recommended now based on reclaimable space, but blocked while any TNC is enabled."
    elif db_vacuum_recommended:
        db_vacuum_recommendation = "Recommended now based on reclaimable space."
    else:
        db_vacuum_recommendation = "Not required now; reclaimable space is below the recommendation threshold."
    map_sources = list_map_sources()
    map_source_edit = get_map_source(map_source_edit_id) if map_source_edit_id is not None else None
    resolved_map_source_form = (
        map_source_form
        if map_source_form is not None
        else (_map_source_form_from_source(map_source_edit) if map_source_edit is not None else _empty_map_source_form())
    )
    update_channels = list_update_channels()
    resolved_ui_palette = normalize_ui_palette(current_ui_palette if current_ui_palette is not None else get_app_setting("ui_palette"))
    resolved_aprs_symbol_set = get_aprs_symbol_set() if current_aprs_symbol_set is None else current_aprs_symbol_set
    event_log_min_level = _normalize_event_log_min_level(get_app_setting(EVENT_LOG_MIN_LEVEL_SETTING_KEY))
    event_log_debug_enabled = get_event_log_debug_enabled()
    traffic_retention_minutes = _normalize_traffic_retention_minutes_option(get_traffic_retention_minutes())
    coverage_fill_opacity = get_coverage_fill_opacity_percent()
    selected_update_channel = str(update_channels.get("selected_channel") or current_update_channel())
    stable_update_channel = str(update_channels.get("stable_channel") or request.app.state.settings.gui_update_branch)
    update_channel_options = [
        {"value": str(name), "label": str(name)}
        for name in (update_channels.get("channels") or [selected_update_channel])
    ]
    update_log_snapshot = read_update_log()
    aprs_alarm_enabled = get_aprs_alarm_enabled()
    aprs_alarm_groups = get_aprs_alarm_groups()
    effective_rf_message_groups = get_effective_message_target_groups(
        alarm_groups=aprs_alarm_groups
    )
    automatic_aprsis_alarm_filter = build_automatic_aprsis_alarm_filter(
        aprs_alarm_groups
    )
    alarm_category_thresholds = get_aprs_alarm_category_thresholds()
    alarm_category_threshold_rows = [
        {
            **category,
            **alarm_category_thresholds[str(category["key"])],
        }
        for category in ALERT_EVENT_CATEGORIES
    ]
    return build_template_context(
        request,
        page_title="Settings",
        current_user=current_user,
        active_nav="settings",
        current_gui_version=current_gui_version(),
        gui_update_url=request.app.state.settings.gui_update_url,
        gui_update_branch=selected_update_channel,
        latest_version_result=latest_version_result,
        flash=flash,
        flash_success=flash_success,
        can_manage_updates=current_user.role in {"admin", "operator"},
        can_manage_global_settings=current_user.role in {"admin", "operator"},
        can_manage_database_maintenance=current_user.role in {"admin", "operator"},
        can_manage_config_backup=current_user.role in {"admin", "operator"},
        current_language=current_language if current_language is not None else get_app_language(),
        current_default_units=current_default_units if current_default_units is not None else station_settings.get("default_units", "metric"),
        current_ui_palette=resolved_ui_palette,
        current_aprs_symbol_set=resolved_aprs_symbol_set,
        current_ui_palette_label=get_ui_palette_label(resolved_ui_palette),
        current_aprs_symbol_set_label=_translate("Modern icon set") if resolved_aprs_symbol_set == APRS_SYMBOL_SET_MODERN else _translate("Legacy icon set"),
        aprs_symbol_set_options=[
            {"value": APRS_SYMBOL_SET_LEGACY, "label": "Legacy icon set"},
            {"value": APRS_SYMBOL_SET_MODERN, "label": "Modern icon set"},
        ],
        ui_palette_options=get_ui_palette_options(),
        aprs_device_identification_status=get_aprs_device_identification_status(),
        event_log_keep_rows=DEFAULT_EVENT_LOG_KEEP_ROWS,
        event_log_min_level=event_log_min_level,
        event_log_debug_enabled=event_log_debug_enabled,
        event_log_min_level_options=[{"value": value, "label": value} for value in EVENT_LOG_MIN_LEVEL_OPTIONS],
        traffic_retention_minutes=traffic_retention_minutes,
        traffic_retention_minutes_label=_format_traffic_retention_minutes_option(traffic_retention_minutes),
        traffic_retention_minutes_options=[
            {"value": value, "label": _format_traffic_retention_minutes_option(value)}
            for value in TRAFFIC_RETENTION_ALLOWED_MINUTES
        ],
        coverage_fill_opacity=coverage_fill_opacity,
        database_vacuum_blocked=database_vacuum_blocked,
        database_maintenance_snapshot=db_maintenance_snapshot,
        database_path=str(db_maintenance_snapshot.get("database_path") or ""),
        database_exists=bool(db_maintenance_snapshot.get("database_exists")),
        database_file_size_label=_format_size_bytes(int(db_maintenance_snapshot.get("database_file_bytes") or 0)),
        database_wal_size_label=_format_size_bytes(int(db_maintenance_snapshot.get("wal_file_bytes") or 0)),
        database_shm_size_label=_format_size_bytes(int(db_maintenance_snapshot.get("shm_file_bytes") or 0)),
        database_allocated_size_label=_format_size_bytes(int(db_maintenance_snapshot.get("allocated_bytes") or 0)),
        database_reclaimable_size_label=_format_size_bytes(int(db_maintenance_snapshot.get("reclaimable_bytes") or 0)),
        database_reclaimable_ratio_label=_format_ratio_percent(float(db_maintenance_snapshot.get("reclaimable_ratio") or 0.0)),
        database_page_size=int(db_maintenance_snapshot.get("page_size") or 0),
        database_page_count=int(db_maintenance_snapshot.get("page_count") or 0),
        database_freelist_count=int(db_maintenance_snapshot.get("freelist_count") or 0),
        database_quick_check=db_quick_check,
        database_quick_check_ok=db_quick_check_ok,
        database_vacuum_recommended=db_vacuum_recommended,
        database_vacuum_recommendation=db_vacuum_recommendation,
        database_vacuum_threshold_size_label=_format_size_bytes(VACUUM_RECOMMEND_FREE_BYTES_MIN),
        database_vacuum_threshold_ratio_label=_format_ratio_percent(VACUUM_RECOMMEND_FREE_RATIO_MIN),
        database_reset_targets=reset_targets,
        database_reset_total_rows=reset_total_rows,
        update_channel_selected=selected_update_channel,
        update_channel_stable=stable_update_channel,
        update_channel_is_unstable=selected_update_channel != stable_update_channel,
        update_channel_options=update_channel_options,
        update_channels_fetch_error=str(update_channels.get("error") or "").strip() or None,
        update_channel_source=str(update_channels.get("source") or request.app.state.settings.gui_update_url),
        update_log_exists=bool(update_log_snapshot.get("exists")),
        update_log_content=str(update_log_snapshot.get("content") or ""),
        update_log_path=str(update_log_snapshot.get("path") or ""),
        update_log_truncated=bool(update_log_snapshot.get("truncated")),
        aprs_alarm_groups=aprs_alarm_groups,
        aprs_alarm_enabled=aprs_alarm_enabled,
        alarm_level_threshold_options=APRS_ALARM_LEVEL_THRESHOLDS,
        alarm_category_threshold_rows=alarm_category_threshold_rows,
        effective_rf_message_groups=effective_rf_message_groups,
        automatic_aprsis_alarm_filter=automatic_aprsis_alarm_filter,
        is_container_mode=container_mode,
        map_sources=map_sources,
        map_source_form=resolved_map_source_form,
        map_source_edit_id=resolved_map_source_form.get("record_id"),
        can_manage_map_sources=current_user.role in {"admin", "operator"},
    )


@router.get("/")
def root(request: Request) -> RedirectResponse:
    return RedirectResponse(url=_path(request, "/dashboard"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/dashboard")
def dashboard(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    dashboard_band = _dashboard_band_condition_card()
    dashboard_activity = get_dashboard_radio_activity(range_value="24h")
    context = build_template_context(
        request,
        page_title="Dashboard",
        current_user=current_user,
        active_nav="dashboard",
        dashboard_band=dashboard_band,
        dashboard_home=dashboard_home_data(dashboard_band, dashboard_activity),
    )
    return templates.TemplateResponse("dashboard.html", context)


@router.get("/band-condition")
def band_condition_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    page_data = get_band_condition_page_data()
    context = build_template_context(
        request,
        page_title="Band Condition",
        current_user=current_user,
        active_nav="band-condition",
        flash=None,
        **page_data,
    )
    return templates.TemplateResponse("band_condition.html", context)


@router.get("/api/band-condition")
def band_condition_snapshot(
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(get_band_condition_snapshot())


@router.get("/api/band-condition/history")
def band_condition_history(
    days: int = 365,
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(get_band_condition_history(days=days))


@router.get("/stations")
def stations_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    station_settings = get_station_settings()
    stations = heard_stations(unit_system=station_settings.get("default_units", "metric"))
    context = build_template_context(
        request,
        page_title="Stations",
        current_user=current_user,
        active_nav="stations",
        stations=stations,
        station_summary=station_summary(get_rf_heard_station_snapshots()),
        default_units=station_settings.get("default_units", "metric"),
    )
    return templates.TemplateResponse("stations.html", context)


@router.get("/stations/{callsign:path}")
def station_detail_page(
    callsign: str,
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    station_settings = get_station_settings()
    station_context = _station_detail_context(
        callsign,
        station_settings.get("default_units", "metric"),
        root_path=request.scope.get("root_path", ""),
    )
    if station_context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found")
    context = build_template_context(
        request,
        page_title=station_context["station"]["display_callsign"],
        current_user=current_user,
        active_nav="stations",
        station=station_context["station"],
        station_map_config=station_context["station_map_config"],
        station_api_endpoint=_path(request, f"/api{station_context['station']['detail_href']}"),
        recent_packets=station_context["recent_packets"],
        related_ssids=station_context["related_ssids"],
        message_flash=None,
        message_form=None,
    )
    return templates.TemplateResponse("station_detail.html", context)


@router.post("/stations/{callsign:path}/message")
def station_detail_message(
    callsign: str,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    destination_callsign: str = Form(""),
    message_text: str = Form(""),
) -> object:
    templates = request.app.state.templates
    station_settings = get_station_settings()
    station_context = _station_detail_context(
        callsign,
        station_settings.get("default_units", "metric"),
        root_path=request.scope.get("root_path", ""),
    )
    if station_context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found")
    message_flash = "APRS message transmit is not implemented yet. The form is present as UI scaffolding only."
    context = build_template_context(
        request,
        page_title=station_context["station"]["display_callsign"],
        current_user=current_user,
        active_nav="stations",
        station=station_context["station"],
        station_map_config=station_context["station_map_config"],
        station_api_endpoint=_path(request, f"/api{station_context['station']['detail_href']}"),
        recent_packets=station_context["recent_packets"],
        related_ssids=station_context["related_ssids"],
        message_flash=message_flash,
        message_form={
            "destination_callsign": (destination_callsign or station_context["station"]["display_callsign"]).strip(),
            "message_text": message_text.strip(),
        },
    )
    return templates.TemplateResponse("station_detail.html", context, status_code=status.HTTP_501_NOT_IMPLEMENTED)


@router.get("/api/stations/{callsign:path}")
def station_detail_snapshot(
    callsign: str,
    request: Request,
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    station_settings = get_station_settings()
    station_context = _station_detail_context(
        callsign,
        station_settings.get("default_units", "metric"),
        root_path=request.scope.get("root_path", ""),
    )
    if station_context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found")
    return JSONResponse(station_context)


@router.get("/api/stations")
def stations_snapshot(
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    station_settings = get_station_settings()
    stations = heard_stations(unit_system=station_settings.get("default_units", "metric"))
    return JSONResponse(
        {
            "stations": stations,
            "summary": station_summary(get_rf_heard_station_snapshots()),
            "default_units": station_settings.get("default_units", "metric"),
        }
    )


@router.get("/settings/modems")
def modems_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
    edit: int | None = None,
    new_type: str | None = None,
    flash: str | None = None,
    success: int = 0,
) -> object:
    templates = request.app.state.templates
    edit_row = get_section_row("modems", edit) if edit is not None else None
    normalized_initial_type = str(new_type or "").strip().upper()
    if normalized_initial_type not in {"SERIALL", "TCP", OPENWEBRX_MQTT_MODEM_TYPE, APRSIS_MODEM_TYPE}:
        normalized_initial_type = None
    return templates.TemplateResponse(
        "section.html",
        _section_template_context(
            request,
            current_user,
            "modems",
            edit_row=edit_row,
            flash=flash,
            flash_success=bool(success),
            initial_modem_type=normalized_initial_type,
        ),
    )


@router.post("/settings/modems")
def modems_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    record_id: int | None = Form(None),
    name: str = Form(...),
    band: str = Form(""),
    modem_type: str = Form(...),
    device_path: str = Form(""),
    baud_rate: int | None = Form(None),
    serial_rx_silence_reconnect_seconds: int = Form(150),
    enabled: str | None = Form(None),
    tx_blocked: str | None = Form(None),
    tx_min_gap_seconds: str = Form("0.35"),
    expose_port_enabled: str | None = Form(None),
    expose_allow_tx: str | None = Form(None),
    expose_bind_address: str = Form("0.0.0.0"),
    expose_port: int | None = Form(8002),
    expose_whitelist: str = Form(""),
    aprsis_server: str = Form(""),
    aprsis_port: str = Form(""),
    aprsis_login: str = Form(""),
    aprsis_passcode: str = Form(""),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"

    def error_response(message: object, context: dict[str, Any]) -> object:
        if wants_json:
            return JSONResponse(
                {"ok": False, "error": _translate(message)},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    normalized_modem_type = modem_type.strip().upper()
    if normalized_modem_type == "SERIAL":
        normalized_modem_type = "SERIALL"
    if normalized_modem_type not in {"SERIALL", "TCP", OPENWEBRX_MQTT_MODEM_TYPE, APRSIS_MODEM_TYPE}:
        context = _section_template_context(request, current_user, "modems", flash="Unsupported interface type.")
        return error_response("Unsupported interface type.", context)
    normalized_device_path = device_path.strip()
    if record_id is not None and normalized_modem_type == OPENWEBRX_MQTT_MODEM_TYPE and "***" in normalized_device_path:
        existing_row = fetch_one("SELECT modem_type, device_path FROM modems WHERE id = ?", (record_id,))
        if existing_row is not None:
            existing_type = str(existing_row["modem_type"] or "").strip().upper()
            existing_path = str(existing_row["device_path"] or "").strip()
            if existing_type == OPENWEBRX_MQTT_MODEM_TYPE and mask_mqtt_url(existing_path) == normalized_device_path:
                normalized_device_path = existing_path
    payload = {
        "name": name.strip(),
        "band": band.strip().lower(),
        "modem_type": normalized_modem_type,
        "device_path": normalized_device_path,
        "baud_rate": baud_rate,
        "serial_rx_silence_reconnect_seconds": serial_rx_silence_reconnect_seconds,
        "enabled": enabled,
        "tx_blocked": tx_blocked,
        "tx_min_gap_seconds": tx_min_gap_seconds,
        "expose_port_enabled": expose_port_enabled,
        "expose_allow_tx": expose_allow_tx,
        "expose_bind_address": expose_bind_address.strip(),
        "expose_port": expose_port,
        "expose_whitelist": expose_whitelist,
    }
    aprsis_form_data = {
        "aprsis_server": aprsis_server,
        "aprsis_port": aprsis_port,
        "aprsis_login": aprsis_login,
        "aprsis_passcode": aprsis_passcode,
    }
    normalized_aprsis_config: dict[str, Any] | None = None
    if normalized_modem_type == APRSIS_MODEM_TYPE:
        try:
            normalized_aprsis_config = normalize_aprsis_config_payload(
                {
                    "server": aprsis_server,
                    "port": aprsis_port,
                    "login": aprsis_login,
                    "passcode": aprsis_passcode,
                }
            )
        except ValueError as exc:
            edit_row = get_section_row("modems", record_id) if record_id is not None else None
            context = _section_template_context(
                request,
                current_user,
                "modems",
                flash=str(exc),
                edit_row=edit_row,
                form_data={**payload, **aprsis_form_data},
            )
            return error_response(str(exc), context)
    if record_id is None:
        if normalized_modem_type == APRSIS_MODEM_TYPE:
            existing_aprsis = fetch_one("SELECT id FROM modems WHERE UPPER(modem_type) = 'APRSIS' LIMIT 1")
            if existing_aprsis is not None:
                existing_id = int(existing_aprsis["id"])
                context = _section_template_context(
                    request,
                    current_user,
                    "modems",
                    flash="An APRSIS interface already exists. Edit the existing interface instead.",
                    edit_row=get_section_row("modems", existing_id),
                )
                return error_response("An APRSIS interface already exists. Edit the existing interface instead.", context)
        success, error = safe_create_section_row("modems", payload)
        edit_row = None
    else:
        success, error = safe_update_section_row("modems", record_id, payload)
        # Keep the form in edit mode after save; user exits via Cancel.
        edit_row = get_section_row("modems", record_id)
    if success and normalized_aprsis_config is not None:
        save_aprsis_config(normalized_aprsis_config)
    if wants_json:
        if not success:
            return JSONResponse(
                {"ok": False, "error": _translate(error or "Failed to save interface settings.")},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return JSONResponse(
            {
                "ok": True,
                "message": _translate("Interface settings updated."),
                "reload": True,
            }
        )
    context = _section_template_context(
        request,
        current_user,
        "modems",
        flash="Interface settings updated." if success and record_id is not None else (None if success else error),
        edit_row=edit_row,
        flash_success=success and record_id is not None,
        form_data=None if success else {**payload, **aprsis_form_data},
    )
    return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.post("/settings/modems/{record_id}/delete")
def modems_delete(
    record_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> RedirectResponse:
    delete_section_row("modems", record_id)
    return RedirectResponse(url=_path(request, "/settings/modems"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/settings/servers")
def servers_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    return templates.TemplateResponse("section.html", _section_template_context(request, current_user, "servers"))


@router.get("/settings")
def settings_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    edit_map_source: int | None = None,
) -> object:
    templates = request.app.state.templates
    context = _settings_page_context(request, current_user, map_source_edit_id=edit_map_source)
    return templates.TemplateResponse("settings.html", context)


@router.post("/settings/check-gui-version")
def settings_check_gui_version(
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    result = latest_gui_version()
    if not result.get("ok"):
        error_text = str(result.get("error") or "Version check failed.")
        return JSONResponse({"ok": False, "error": _translate(error_text)}, status_code=status.HTTP_502_BAD_GATEWAY)
    return JSONResponse({"ok": True, "result": result})

@router.post("/settings/update-channel")
def settings_update_channel(
    _: Request,
    __: UserIdentity = Depends(require_roles("admin", "operator")),
    update_channel: str = Form(...),
) -> object:
    try:
        selected = save_update_channel(update_channel)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": _translate(str(exc))}, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse({"ok": True, "channel": selected})


@router.post("/settings/update-application")
def settings_update_application(
    _: Request,
    __: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    if is_container_mode():
        return _container_mode_system_action_denied_response()
    job_id = create_system_job("update-application", message=_translate("Queued."))
    result = start_application_update_job(job_id=job_id)
    if not result.get("ok"):
        mark_system_job_error(job_id, message=_translate(str(result.get("error") or "Failed to start update script.")))
        return JSONResponse(
            {"ok": False, "error": _translate(str(result.get("error") or "Failed to start update."))},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    mark_system_job_running(
        job_id,
        pid=int(result.get("pid") or 0) or None,
        log_file=str(result.get("log_file") or "") or None,
        message=_translate("Running."),
    )
    return JSONResponse({"ok": True, "job_id": job_id, "status": "queued"}, status_code=status.HTTP_202_ACCEPTED)


@router.get("/api/settings/update/channels")
def settings_update_channels_api(
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    return JSONResponse(list_update_channels())


@router.get("/api/settings/update/channel")
def settings_update_channel_api(
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    channels = list_update_channels()
    return JSONResponse(
        {
            "channel": channels.get("selected_channel") or current_update_channel(),
            "stable_channel": channels.get("stable_channel"),
            "source": channels.get("source"),
        }
    )


@router.post("/api/settings/update/channel")
async def settings_update_channel_set_api(
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    payload = await request.json()
    try:
        selected = save_update_channel(str(payload.get("channel") or ""))
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": _translate(str(exc))}, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse({"ok": True, "channel": selected})


@router.get("/api/settings/update/log")
def settings_update_log_api(
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    return JSONResponse(read_update_log())


@router.get("/api/settings/jobs/{job_id}")
def settings_job_status_api(
    job_id: int,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    job = fetch_system_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    should_check_reporting = (
        str(job.get("kind") or "") in {"update-application", "restart-services"}
        and str(job.get("status") or "") == "running"
        and int(job.get("progress_percent") or 0) <= 1
        and not _system_job_process_is_running(job.get("pid"))
    )
    if should_check_reporting and mark_unreported_system_job_error(
        job_id,
        message=_translate(
            "The maintenance process stopped reporting status. Verify the installed version before trying again."
        ),
    ):
        job = fetch_system_job(job_id) or job
    return JSONResponse({"ok": True, "job": job})


@router.post("/settings/restart-services")
def settings_restart_services(
    _: Request,
    __: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    if is_container_mode():
        return _container_mode_system_action_denied_response()
    job_id = create_system_job("restart-services", message=_translate("Queued."))
    result = start_service_restart_job(job_id=job_id)
    if not result.get("ok"):
        mark_system_job_error(job_id, message=_translate(str(result.get("error") or "Failed to start restart script.")))
        return JSONResponse(
            {"ok": False, "error": _translate(str(result.get("error") or "Failed to start service restart."))},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    mark_system_job_running(
        job_id,
        pid=int(result.get("pid") or 0) or None,
        log_file=str(result.get("log_file") or "") or None,
        message=_translate("Running."),
    )
    return JSONResponse({"ok": True, "job_id": job_id, "status": "queued"}, status_code=status.HTTP_202_ACCEPTED)


@router.post("/settings/reboot-host")
def settings_reboot_host(
    _: Request,
    __: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    if is_container_mode():
        return _container_mode_system_action_denied_response()
    job_id = create_system_job("reboot-host", message=_translate("Queued."))
    result = start_host_reboot_job(job_id=job_id)
    if not result.get("ok"):
        mark_system_job_error(job_id, message=_translate(str(result.get("error") or "Failed to start reboot script.")))
        return JSONResponse(
            {"ok": False, "error": _translate(str(result.get("error") or "Failed to start host reboot."))},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    mark_system_job_running(
        job_id,
        pid=int(result.get("pid") or 0) or None,
        log_file=str(result.get("log_file") or "") or None,
        message=_translate("Running."),
    )
    return JSONResponse({"ok": True, "job_id": job_id, "status": "queued"}, status_code=status.HTTP_202_ACCEPTED)


@router.post("/settings/poweroff-host")
def settings_poweroff_host(
    _: Request,
    __: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    if is_container_mode():
        return _container_mode_system_action_denied_response()
    job_id = create_system_job("poweroff-host", message=_translate("Queued."))
    result = start_host_poweroff_job(job_id=job_id)
    if not result.get("ok"):
        mark_system_job_error(job_id, message=_translate(str(result.get("error") or "Failed to start poweroff script.")))
        return JSONResponse(
            {"ok": False, "error": _translate(str(result.get("error") or "Failed to start host power off."))},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    mark_system_job_running(
        job_id,
        pid=int(result.get("pid") or 0) or None,
        log_file=str(result.get("log_file") or "") or None,
        message=_translate("Running."),
    )
    return JSONResponse({"ok": True, "job_id": job_id, "status": "queued"}, status_code=status.HTTP_202_ACCEPTED)


@router.post("/settings/update-aprs-device-identification")
def settings_update_aprs_device_identification(
    _: Request,
    __: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    result = refresh_aprs_device_identification_cache()
    if not result.get("ok"):
        error_text = str(result.get("error") or "APRS device identification database update failed.")
        return JSONResponse(
            {"ok": False, "error": _translate(error_text)},
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    return JSONResponse({"ok": True, "message": _translate("APRS device identification database updated.")})


@router.post("/settings/vacuum-db")
def settings_vacuum_db(
    _: Request,
    __: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    if has_enabled_modem_interface():
        return JSONResponse(
            {"ok": False, "error": _translate("Disable all TNC interfaces before running database vacuum.")},
            status_code=status.HTTP_409_CONFLICT,
        )

    vacuum_database()
    return JSONResponse({"ok": True, "message": _translate("Database vacuum completed.")})


@router.post("/settings/reset-runtime-data")
def settings_reset_runtime_data(
    _: Request,
    __: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    if has_enabled_modem_interface():
        return JSONResponse(
            {"ok": False, "error": _translate("Disable all TNC interfaces before clearing runtime logs and traffic history.")},
            status_code=status.HTTP_409_CONFLICT,
        )

    deleted_by_table = reset_runtime_operational_data()
    deleted_total = sum(int(value) for value in deleted_by_table.values())
    return JSONResponse(
        {
            "ok": True,
            "message": _translate("Runtime logs and traffic history cleared."),
            "details": {"deleted_total": deleted_total, "deleted_by_table": deleted_by_table},
            "reload": True,
        }
    )


@router.get("/settings/config/export")
def settings_export_configuration_backup(
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> Response:
    payload = export_configuration_backup_bytes()
    filename = build_configuration_backup_filename()
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/settings/config/import")
async def settings_import_configuration_backup(
    backup_file: UploadFile = File(...),
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    try:
        payload = await backup_file.read(_CONFIG_BACKUP_MAX_BYTES + 1)
    finally:
        await backup_file.close()

    if not payload:
        return JSONResponse({"ok": False, "error": _translate("Backup file is empty.")}, status_code=status.HTTP_400_BAD_REQUEST)
    if len(payload) > _CONFIG_BACKUP_MAX_BYTES:
        return JSONResponse(
            {"ok": False, "error": _translate("Backup file is too large (limit: 5 MB).")},
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    success, error = safe_import_configuration_backup(payload)
    if not success:
        return JSONResponse(
            {"ok": False, "error": _translate(error or "Failed to import configuration backup.")},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return JSONResponse(
        {
            "ok": True,
            "message": _translate("Configuration backup imported. Restart services to apply runtime changes."),
            "reload": True,
        }
    )


@router.post("/settings/global")
def settings_update_global(
    request: Request,
    language: str = Form(...),
    default_units: str = Form(...),
    traffic_retention_minutes: str = Form(""),
    ui_palette: str = Form(""),
    aprs_symbol_set: str = Form(""),
    event_log_min_level: str = Form(""),
    event_log_debug_enabled: str | None = Form(None),
    coverage_fill_opacity: str = Form(str(DEFAULT_COVERAGE_FILL_OPACITY_PERCENT)),
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    raw_language = str(language or "").strip().lower()
    raw_ui_palette = str(ui_palette or "").strip().lower()
    raw_aprs_symbol_set = str(aprs_symbol_set or "").strip().lower()
    selected_language = normalize_language(language)
    selected_default_units = str(default_units or "").strip().lower()
    raw_traffic_retention_minutes = str(traffic_retention_minutes or "").strip()
    selected_traffic_retention_minutes = _normalize_traffic_retention_minutes_option(raw_traffic_retention_minutes)
    selected_ui_palette = normalize_ui_palette(raw_ui_palette)
    selected_aprs_symbol_set = raw_aprs_symbol_set if raw_aprs_symbol_set in {APRS_SYMBOL_SET_LEGACY, APRS_SYMBOL_SET_MODERN} else APRS_SYMBOL_SET_LEGACY
    raw_event_log_min_level = str(event_log_min_level or "").strip().upper()
    selected_event_log_min_level = _normalize_event_log_min_level(raw_event_log_min_level)
    selected_event_log_debug_enabled = _map_source_checkbox(event_log_debug_enabled)
    raw_coverage_fill_opacity = str(coverage_fill_opacity or "").strip()
    selected_coverage_fill_opacity = normalize_coverage_fill_opacity_percent(raw_coverage_fill_opacity)
    station_settings = get_station_settings()
    current_default_units = station_settings.get("default_units", "metric")
    if selected_language not in SUPPORTED_LANGUAGE_CODES or selected_language != raw_language:
        return JSONResponse({"ok": False, "error": _translate("Unsupported language selection.")}, status_code=status.HTTP_400_BAD_REQUEST)
    if selected_default_units not in {"metric", "imperial"}:
        return JSONResponse({"ok": False, "error": _translate("Unsupported unit selection.")}, status_code=status.HTTP_400_BAD_REQUEST)
    if raw_traffic_retention_minutes != str(selected_traffic_retention_minutes):
        return JSONResponse(
            {"ok": False, "error": _translate("Unsupported traffic history retention selection.")},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not is_supported_ui_palette(raw_ui_palette):
        return JSONResponse({"ok": False, "error": _translate("Unsupported color palette selection.")}, status_code=status.HTTP_400_BAD_REQUEST)
    if raw_aprs_symbol_set and raw_aprs_symbol_set not in {APRS_SYMBOL_SET_LEGACY, APRS_SYMBOL_SET_MODERN}:
        return JSONResponse({"ok": False, "error": _translate("Unsupported icon set selection.")}, status_code=status.HTTP_400_BAD_REQUEST)
    if raw_event_log_min_level not in EVENT_LOG_MIN_LEVEL_OPTIONS:
        return JSONResponse({"ok": False, "error": _translate("Unsupported log level selection.")}, status_code=status.HTTP_400_BAD_REQUEST)
    if raw_coverage_fill_opacity != str(selected_coverage_fill_opacity):
        return JSONResponse(
            {"ok": False, "error": _translate("Unsupported coverage fill opacity selection.")},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    station_payload = dict(station_settings)
    station_payload["default_units"] = selected_default_units
    success, error = safe_update_station_settings(station_payload)
    if not success:
        return JSONResponse(
            {"ok": False, "error": _translate(str(error or "Failed to update global settings."))},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    set_app_setting("app_language", selected_language)
    set_app_setting(TRAFFIC_RETENTION_MINUTES_SETTING_KEY, str(selected_traffic_retention_minutes))
    set_app_setting("ui_palette", selected_ui_palette)
    set_app_setting(APRS_SYMBOL_SET_SETTING_KEY, selected_aprs_symbol_set)
    set_app_setting(EVENT_LOG_MIN_LEVEL_SETTING_KEY, selected_event_log_min_level)
    set_app_setting(EVENT_LOG_DEBUG_ENABLED_SETTING_KEY, "1" if selected_event_log_debug_enabled else "0")
    set_app_setting(COVERAGE_FILL_OPACITY_SETTING_KEY, str(selected_coverage_fill_opacity))
    return JSONResponse(
        {
            "ok": True,
            "message": _translate("Global settings updated."),
            "current_language": selected_language,
            "current_default_units": selected_default_units,
            "traffic_retention_minutes": selected_traffic_retention_minutes,
            "current_ui_palette": selected_ui_palette,
            "current_aprs_symbol_set": selected_aprs_symbol_set,
            "event_log_min_level": selected_event_log_min_level,
            "event_log_debug_enabled": selected_event_log_debug_enabled,
            "coverage_fill_opacity": selected_coverage_fill_opacity,
            "reload": True,
        }
    )


@router.post("/settings/alarm-groups")
def settings_update_alarm_groups(
    _: Request,
    alarm_enabled: bool = Form(False),
    alarm_groups: str = Form(""),
    threshold_category: list[str] | None = Form(None),
    alert_level_threshold: list[str] | None = Form(None),
    map_level_threshold: list[str] | None = Form(None),
    popup_level_threshold: list[str] | None = Form(None),
    map_alarm_level_threshold: str | None = Form(None),
    global_alarm_level_threshold: str | None = Form(None),
    __: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    try:
        normalized_groups = normalize_aprs_alarm_groups(alarm_groups)
        selected_category_thresholds = get_aprs_alarm_category_thresholds()
        if (
            threshold_category is not None
            or alert_level_threshold is not None
            or map_level_threshold is not None
            or popup_level_threshold is not None
        ):
            categories = threshold_category or []
            alert_thresholds = alert_level_threshold or []
            map_thresholds = map_level_threshold
            popup_thresholds = popup_level_threshold
            expected_categories = {
                str(category["key"])
                for category in ALERT_EVENT_CATEGORIES
            }
            if (
                len(categories) != len(alert_thresholds)
                or (
                    map_thresholds is not None
                    and len(categories) != len(map_thresholds)
                )
                or (
                    popup_thresholds is not None
                    and len(categories) != len(popup_thresholds)
                )
                or len(categories) != len(expected_categories)
                or set(categories) != expected_categories
            ):
                raise ValueError(_translate("Invalid APRS alarm category thresholds."))
            selected_category_thresholds = normalize_aprs_alarm_category_thresholds(
                {
                    category: {
                        "alerts": alerts,
                        "map": (
                            map_thresholds[index]
                            if map_thresholds is not None
                            else selected_category_thresholds[category]["map"]
                        ),
                        "popup": (
                            popup_thresholds[index]
                            if popup_thresholds is not None
                            else selected_category_thresholds[category]["popup"]
                        ),
                    }
                    for index, (category, alerts) in enumerate(
                        zip(categories, alert_thresholds)
                    )
                }
            )
        elif (
            map_alarm_level_threshold is not None
            or global_alarm_level_threshold is not None
        ):
            selected_map_threshold = (
                get_map_alarm_level_threshold()
                if map_alarm_level_threshold is None
                else normalize_aprs_alarm_level_threshold(
                    map_alarm_level_threshold
                )
            )
            selected_global_threshold = (
                get_global_alarm_level_threshold()
                if global_alarm_level_threshold is None
                else normalize_aprs_alarm_level_threshold(
                    global_alarm_level_threshold
                )
            )
            for thresholds in selected_category_thresholds.values():
                thresholds["map"] = selected_map_threshold
                thresholds["alerts"] = selected_global_threshold
        saved_alarm_enabled = save_aprs_alarm_enabled(alarm_enabled)
        saved_groups = save_aprs_alarm_groups(normalized_groups)
        saved_category_thresholds = save_aprs_alarm_category_thresholds(
            selected_category_thresholds
        )
        if map_alarm_level_threshold is not None:
            save_map_alarm_level_threshold(selected_map_threshold)
        if global_alarm_level_threshold is not None:
            save_global_alarm_level_threshold(selected_global_threshold)
        reconcile_effective_message_group_conversations(alarm_groups=saved_groups)
    except ValueError as exc:
        return JSONResponse(
            {"ok": False, "error": _translate(str(exc))},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return JSONResponse(
        {
            "ok": True,
            "message": _translate("APRS alarm settings updated."),
            "alarm_enabled": saved_alarm_enabled,
            "alarm_groups": saved_groups,
            "alarm_category_thresholds": saved_category_thresholds,
            "map_alarm_level_threshold": get_map_alarm_level_threshold(),
            "global_alarm_level_threshold": get_global_alarm_level_threshold(),
            "reload": True,
        }
    )


@router.post("/settings/map-sources")
def settings_map_sources_save(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    record_id: int | None = Form(None),
    name: str = Form(""),
    url_template: str = Form(""),
    attribution: str = Form(""),
    min_zoom: str = Form("0"),
    max_zoom: str = Form("19"),
    enabled: str | None = Form(None),
    local_cache_enabled: str | None = Form(None),
    is_default: str | None = Form(None),
    notes: str = Form(""),
) -> object:
    templates = request.app.state.templates
    payload = {
        "name": name.strip(),
        "url_template": url_template.strip(),
        "attribution": attribution.strip(),
        "min_zoom": min_zoom.strip(),
        "max_zoom": max_zoom.strip(),
        "enabled": enabled,
        "local_cache_enabled": local_cache_enabled,
        "is_default": is_default,
        "notes": notes.strip(),
    }
    success, error, saved_id = safe_save_map_source(payload, source_id=record_id)
    if not success:
        context = _settings_page_context(
            request,
            current_user,
            flash=error or "Failed to save map source.",
            flash_success=False,
            map_source_edit_id=record_id,
            map_source_form=_map_source_form_from_payload(payload, record_id=record_id),
        )
        return templates.TemplateResponse("settings.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    context = _settings_page_context(
        request,
        current_user,
        flash="Map source saved.",
        flash_success=True,
        map_source_edit_id=saved_id if record_id is not None else None,
    )
    return templates.TemplateResponse("settings.html", context)


@router.post("/settings/map-sources/{source_id}/default")
def settings_map_sources_set_default(
    source_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    success, error = safe_set_default_map_source(source_id)
    context = _settings_page_context(
        request,
        current_user,
        flash="Default map source updated." if success else (error or "Failed to change default map source."),
        flash_success=success,
        map_source_edit_id=source_id if success else None,
    )
    return templates.TemplateResponse("settings.html", context, status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST)


@router.post("/settings/map-sources/{source_id}/move")
def settings_map_sources_move(
    source_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    direction: str = Form(...),
) -> object:
    templates = request.app.state.templates
    success, error = safe_move_map_source(source_id, direction)
    context = _settings_page_context(
        request,
        current_user,
        flash=None if success else (error or "Failed to reorder map source."),
        flash_success=success,
    )
    return templates.TemplateResponse("settings.html", context, status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST)


@router.post("/settings/map-sources/{source_id}/delete")
def settings_map_sources_delete(
    source_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    success, error = safe_delete_map_source(source_id)
    context = _settings_page_context(
        request,
        current_user,
        flash="Map source deleted." if success else (error or "Failed to delete map source."),
        flash_success=success,
    )
    return templates.TemplateResponse("settings.html", context, status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST)


@router.post("/settings/map-sources/{source_id}/cache/clear")
def settings_map_sources_clear_cache(
    source_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    success, error = safe_clear_map_source_cache(source_id)
    context = _settings_page_context(
        request,
        current_user,
        flash="Map source cache cleared." if success else (error or "Failed to clear map source cache."),
        flash_success=success,
        map_source_edit_id=source_id if success else None,
    )
    return templates.TemplateResponse("settings.html", context, status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST)


@router.post("/settings/language")
def settings_update_language(
    request: Request,
    language: str = Form(...),
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    selected_language = normalize_language(language)
    if selected_language not in SUPPORTED_LANGUAGE_CODES or selected_language != str(language or "").strip().lower():
        context = _settings_page_context(request, current_user, flash="Unsupported language selection.", flash_success=False)
        return templates.TemplateResponse("settings.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    set_app_setting("app_language", selected_language)
    context = _settings_page_context(request, current_user, flash="GUI language updated.", flash_success=True, current_language=selected_language)
    return templates.TemplateResponse("settings.html", context)


@router.post("/settings/servers")
def servers_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    name: str = Form(...),
    host: str = Form(...),
    port: int = Form(...),
    use_tls: str | None = Form(None),
    enabled: str | None = Form(None),
    notes: str = Form(""),
) -> object:
    templates = request.app.state.templates
    success, error = safe_create_section_row(
        "servers",
        {
            "name": name.strip(),
            "host": host.strip(),
            "port": port,
            "use_tls": use_tls,
            "enabled": enabled,
            "notes": notes.strip(),
        },
    )
    context = _section_template_context(request, current_user, "servers", flash=None if success else error)
    return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.get("/igate")
def igate_page(
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
    flash: str | None = None,
    success: int = 0,
) -> RedirectResponse:
    target = _aprsis_interface_settings_path()
    if flash:
        target += f"&flash={quote(flash)}&success={1 if success else 0}"
    return RedirectResponse(url=_path(request, target), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/igate")
def igate_settings_update(
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
    server: str = Form(""),
    port: str = Form(""),
    login: str = Form(""),
    passcode: str = Form(""),
) -> RedirectResponse:
    success, error = safe_save_aprsis_config(
        {
            "server": server,
            "port": port,
            "login": login,
            "passcode": passcode,
        }
    )
    target = _aprsis_interface_settings_path()
    message = "APRS-IS settings updated." if success else (error or "Failed to save APRS-IS settings.")
    return RedirectResponse(
        url=_path(request, f"{target}&flash={quote(message)}&success={1 if success else 0}"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/api/igate/diagnostics")
def igate_diagnostics_api(
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    runtime = get_aprsis_runtime_status()
    return JSONResponse(
        {
            "runtime": runtime,
            "runtime_badge": aprsis_runtime_badge(runtime.get("status", "")),
            "config": get_aprsis_config(),
            "diagnostics": get_aprsis_diagnostics(),
        }
    )


@router.get("/digi")
def digi_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    return templates.TemplateResponse("section.html", _section_template_context(request, current_user, "digi"))


@router.post("/digi")
def digi_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    name: str = Form(...),
    source_match: str = Form(""),
    destination_match: str = Form(""),
    path_rewrite: str = Form(""),
    is_enabled: str | None = Form(None),
) -> object:
    templates = request.app.state.templates
    success, error = safe_create_section_row(
        "digi",
        {
            "name": name.strip(),
            "source_match": source_match.strip(),
            "destination_match": destination_match.strip(),
            "path_rewrite": path_rewrite.strip(),
            "is_enabled": is_enabled,
        },
    )
    context = _section_template_context(request, current_user, "digi", flash=None if success else error)
    return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.get("/digi-flows")
def digi_flows_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    flash: str | None = None,
    success: int = 0,
) -> object:
    templates = request.app.state.templates
    context = build_template_context(
        request,
        page_title="Packet Routing",
        current_user=current_user,
        active_nav="digi-flows",
        flows=list_digi_flows(),
        can_edit=current_user.role in {"admin", "operator"},
        flash=flash,
        flash_success=bool(success),
    )
    return templates.TemplateResponse("digi_flows.html", context)


@router.post("/digi-flows/aprsis-config")
def digi_flows_aprsis_config_update(
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
    server: str = Form(""),
    port: str = Form(""),
    login: str = Form(""),
    passcode: str = Form(""),
) -> RedirectResponse:
    success, error = safe_save_aprsis_config(
        {
            "server": server,
            "port": port,
            "login": login,
            "passcode": passcode,
        }
    )
    if not success:
        return RedirectResponse(
            url=_path(
                request,
                f"{_aprsis_interface_settings_path()}&flash={quote(error or 'Failed to save APRS-IS settings.')}&success=0",
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=_path(
            request,
            f"{_aprsis_interface_settings_path()}&flash=APRS-IS%20settings%20updated.&success=1",
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/digi-flows/new")
def digi_flow_new_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    duplicate: int | None = None,
) -> object:
    templates = request.app.state.templates
    flash = None
    flash_success = False
    if duplicate is not None:
        duplicate_flow = get_digi_flow(duplicate)
        if duplicate_flow is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DIGI Flow not found")
        form_data = build_digi_flow_editor_payload(duplicate_flow)
        form_data["name"] = f"{form_data['name']} copy"
        flash = "Flow duplicated into a new draft. You can keep the same source and target; only one flow per source+target pair can stay enabled at a time."
        flash_success = True
    else:
        form_data = build_digi_flow_editor_payload()
    context = _digi_flow_editor_context(
        request,
        current_user,
        form_data=form_data,
        flash=flash,
        flash_success=flash_success,
    )
    return templates.TemplateResponse("digi_flow_form.html", context)


@router.get("/digi-flows/{flow_id}")
def digi_flow_edit_page(
    flow_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    flow = get_digi_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DIGI Flow not found")
    context = _digi_flow_editor_context(
        request,
        current_user,
        flow_id=flow_id,
        form_data=build_digi_flow_editor_payload(flow),
    )
    return templates.TemplateResponse("digi_flow_form.html", context)


@router.get("/api/digi-flows/{flow_id}/events")
def digi_flow_event_log_api(
    flow_id: int,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    flow = get_digi_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DIGI Flow not found")
    return JSONResponse({"flow_id": flow_id, "events": get_digi_flow_event_log(flow_id, limit=200)})


@router.get("/api/digi-flows/{flow_id}/executions")
def digi_flow_execution_summaries_api(
    flow_id: int,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    flow = get_digi_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DIGI Flow not found")
    return JSONResponse({"flow_id": flow_id, "executions": get_digi_flow_execution_summaries(flow_id, execution_limit=10)})


@router.post("/digi-flows")
async def digi_flow_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    form = await request.form()
    try:
        payload = _parse_digi_flow_form_payload(form)
    except ValueError as exc:
        context = _digi_flow_editor_context(request, current_user, form_data=build_digi_flow_editor_payload(), flash=str(exc))
        return templates.TemplateResponse("digi_flow_form.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    flow_id, error = safe_create_digi_flow(payload)
    if error:
        context = _digi_flow_editor_context(request, current_user, form_data=payload, flash=error)
        return templates.TemplateResponse("digi_flow_form.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    assert flow_id is not None
    flow = get_digi_flow(flow_id)
    context = _digi_flow_editor_context(
        request,
        current_user,
        flow_id=flow_id,
        form_data=build_digi_flow_editor_payload(flow),
        flash="Packet Routing flow created.",
        flash_success=True,
    )
    return templates.TemplateResponse("digi_flow_form.html", context)


@router.post("/digi-flows/{flow_id}")
async def digi_flow_update(
    flow_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    if get_digi_flow(flow_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DIGI Flow not found")

    form = await request.form()
    try:
        payload = _parse_digi_flow_form_payload(form)
    except ValueError as exc:
        context = _digi_flow_editor_context(request, current_user, flow_id=flow_id, form_data=build_digi_flow_editor_payload(), flash=str(exc))
        return templates.TemplateResponse("digi_flow_form.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    error = safe_update_digi_flow(flow_id, payload)
    if error:
        context = _digi_flow_editor_context(request, current_user, flow_id=flow_id, form_data=payload, flash=error)
        return templates.TemplateResponse("digi_flow_form.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    flow = get_digi_flow(flow_id)
    context = _digi_flow_editor_context(
        request,
        current_user,
        flow_id=flow_id,
        form_data=build_digi_flow_editor_payload(flow),
        flash="Packet Routing flow updated.",
        flash_success=True,
    )
    return templates.TemplateResponse("digi_flow_form.html", context)


@router.post("/digi-flows/{flow_id}/toggle")
def digi_flow_toggle(
    flow_id: int,
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
    enabled: int = Form(...),
) -> RedirectResponse:
    try:
        set_digi_flow_enabled(flow_id, bool(enabled))
    except ValueError as exc:
        return RedirectResponse(
            url=_path(request, f"/digi-flows?flash={quote(str(exc))}&success=0"),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=_path(request, f"/digi-flows?flash={'Packet%20Routing%20flow%20status%20updated.'}&success=1"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/digi-flows/{flow_id}/move")
def digi_flow_move(
    flow_id: int,
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
    direction: str = Form(...),
) -> RedirectResponse:
    error = safe_move_digi_flow(flow_id, direction)
    if error:
        return RedirectResponse(
            url=_path(request, f"/digi-flows?flash={quote(error)}&success=0"),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=_path(request, "/digi-flows"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/digi-flows/{flow_id}/delete")
def digi_flow_delete(
    flow_id: int,
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> RedirectResponse:
    delete_digi_flow(flow_id)
    return RedirectResponse(
        url=_path(request, f"/digi-flows?flash={'Packet%20Routing%20flow%20deleted.'}&success=1"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/objects")
def objects_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    edit: int | None = None,
    flash: str | None = None,
    success: str | None = None,
) -> object:
    templates = request.app.state.templates
    edit_row = get_section_row("objects", edit) if edit is not None else None
    context = _section_template_context(
        request,
        current_user,
        "objects",
        flash=flash,
        edit_row=edit_row,
    )
    if success is not None:
        context["flash_success"] = str(success).strip() not in {"0", "false", "False"}
    return templates.TemplateResponse("section.html", context)


@router.post("/objects")
def objects_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    record_id: int | None = Form(None),
    name: str = Form(...),
    lifetime: str = Form("temporary"),
    state: str = Form("live"),
    latitude: str = Form(""),
    longitude: str = Form(""),
    symbol_table: str = Form("/"),
    symbol_code: str = Form(">"),
    symbol_overlay: str = Form(""),
    interval_minutes: str = Form("30"),
    activation_mode: str = Form("manual"),
    active_from_utc: str = Form(""),
    active_until_utc: str = Form(""),
    recurrence_duration_minutes: str = Form(""),
    recurrence_interval_value: str = Form(""),
    recurrence_interval_unit: str = Form(""),
    path: str = Form(""),
    is_enabled: str | None = Form(None),
    comment: str = Form(""),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    payload = {
        "name": name.strip(),
        "lifetime": lifetime.strip(),
        "state": state.strip(),
        "latitude": latitude.strip(),
        "longitude": longitude.strip(),
        "symbol_table": symbol_table.strip(),
        "symbol_code": symbol_code.strip(),
        "symbol_overlay": symbol_overlay.strip(),
        "interval_minutes": interval_minutes.strip(),
        "activation_mode": activation_mode.strip(),
        "active_from_utc": active_from_utc.strip(),
        "active_until_utc": active_until_utc.strip(),
        "recurrence_duration_minutes": recurrence_duration_minutes.strip(),
        "recurrence_interval_value": recurrence_interval_value.strip(),
        "recurrence_interval_unit": recurrence_interval_unit.strip(),
        "path": path.strip(),
        "is_enabled": is_enabled,
        "comment": comment.strip(),
    }
    if record_id is None:
        success, error = safe_create_section_row("objects", payload)
        if success:
            created_row = fetch_one("SELECT id FROM aprs_objects WHERE name = ?", (payload["name"],))
            if created_row is not None:
                if wants_json:
                    created_id = int(created_row["id"])
                    return JSONResponse(
                        {
                            "ok": True,
                            "message": _translate("Object saved."),
                            "reload": True,
                            "redirect": _path(request, f"/objects?edit={created_id}"),
                        }
                    )
                return _section_edit_redirect(request, "objects", int(created_row["id"]))
        edit_row = None
    else:
        success, error = safe_update_section_row("objects", record_id, payload)
        if success:
            if wants_json:
                return JSONResponse(
                    {
                        "ok": True,
                        "message": _translate("Object saved."),
                        "reload": True,
                        "redirect": _path(request, f"/objects?edit={record_id}"),
                    }
                )
            return _section_edit_redirect(request, "objects", record_id)
        edit_row = get_section_row("objects", record_id) if error else None
    context = _section_template_context(request, current_user, "objects", flash=None if success else error, edit_row=edit_row)
    if wants_json:
        if success:
            return JSONResponse(
                {
                    "ok": True,
                    "message": _translate("Object saved."),
                    "reload": True,
                    "redirect": _path(request, "/objects"),
                }
            )
        return JSONResponse(
            {"ok": False, "error": _translate(error or "Failed to save object.")},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.post("/settings/objects/{record_id}/send")
def objects_send_now(
    record_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    row = get_section_row("objects", record_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Object not found.")

    station_settings = get_station_settings()
    success, flash = enqueue_object_job(row, station_settings, trigger="manual", force_send=True)
    if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        return JSONResponse(
            {
                "ok": success,
                "message" if success else "error": _translate(flash or "Failed to send object."),
                "reload": success,
                "redirect": _path(request, f"/objects?edit={record_id}"),
            },
            status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(
        url=_path(
            request,
            f"/objects?edit={record_id}&flash={quote(str(flash or '') )}&success={'1' if success else '0'}",
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/items")
def items_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    edit: int | None = None,
) -> object:
    templates = request.app.state.templates
    edit_row = get_section_row("items", edit) if edit is not None else None
    return templates.TemplateResponse("section.html", _section_template_context(request, current_user, "items", edit_row=edit_row))


@router.post("/items")
def items_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    record_id: int | None = Form(None),
    name: str = Form(...),
    state: str = Form("live"),
    latitude: str = Form(""),
    longitude: str = Form(""),
    symbol_table: str = Form("/"),
    symbol_code: str = Form(">"),
    symbol_overlay: str = Form(""),
    interval_minutes: str = Form("30"),
    activation_mode: str = Form("manual"),
    active_from_utc: str = Form(""),
    active_until_utc: str = Form(""),
    recurrence_duration_minutes: str = Form(""),
    recurrence_interval_value: str = Form(""),
    recurrence_interval_unit: str = Form(""),
    path: str = Form(""),
    is_enabled: str | None = Form(None),
    comment: str = Form(""),
) -> object:
    templates = request.app.state.templates
    payload = {
        "name": name.strip(),
        "state": state.strip(),
        "latitude": latitude.strip(),
        "longitude": longitude.strip(),
        "symbol_table": symbol_table.strip(),
        "symbol_code": symbol_code.strip(),
        "symbol_overlay": symbol_overlay.strip(),
        "interval_minutes": interval_minutes.strip(),
        "activation_mode": activation_mode.strip(),
        "active_from_utc": active_from_utc.strip(),
        "active_until_utc": active_until_utc.strip(),
        "recurrence_duration_minutes": recurrence_duration_minutes.strip(),
        "recurrence_interval_value": recurrence_interval_value.strip(),
        "recurrence_interval_unit": recurrence_interval_unit.strip(),
        "path": path.strip(),
        "is_enabled": is_enabled,
        "comment": comment.strip(),
    }
    if record_id is None:
        success, error = safe_create_section_row("items", payload)
        if success:
            created_row = fetch_one("SELECT id FROM aprs_items WHERE name = ?", (payload["name"],))
            if created_row is not None:
                return _section_edit_redirect(request, "items", int(created_row["id"]))
        edit_row = None
    else:
        success, error = safe_update_section_row("items", record_id, payload)
        if success:
            return _section_edit_redirect(request, "items", record_id)
        edit_row = get_section_row("items", record_id) if error else None
    context = _section_template_context(request, current_user, "items", flash=None if success else error, edit_row=edit_row)
    return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.post("/settings/objects/{record_id}/delete")
def objects_delete(
    record_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    delete_section_row("objects", record_id)
    if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        return JSONResponse(
            {
                "ok": True,
                "message": _translate("Object deleted."),
                "reload": True,
                "redirect": _path(request, "/objects"),
            }
        )
    return RedirectResponse(url=_path(request, "/objects"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/items/{record_id}/delete")
def items_delete(
    record_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> RedirectResponse:
    delete_section_row("items", record_id)
    return RedirectResponse(url=_path(request, "/items"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/bulletins")
def bulletins_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    edit: int | None = None,
    flash: str | None = None,
    success: str | None = None,
) -> object:
    templates = request.app.state.templates
    edit_row = get_section_row("bulletins", edit) if edit is not None else None
    context = _section_template_context(
        request,
        current_user,
        "bulletins",
        flash=flash,
        edit_row=edit_row,
    )
    if success is not None:
        context["flash_success"] = str(success).strip() not in {"0", "false", "False"}
    return templates.TemplateResponse("section.html", context)


@router.post("/bulletins")
def bulletins_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    record_id: int | None = Form(None),
    message_kind: str = Form("bulletin"),
    bulletin_code: str = Form(""),
    group_name: str = Form(""),
    interval_minutes: str = Form("30"),
    activation_mode: str = Form("manual"),
    active_from_utc: str = Form(""),
    active_until_utc: str = Form(""),
    recurrence_duration_minutes: str = Form(""),
    recurrence_interval_value: str = Form(""),
    recurrence_interval_unit: str = Form(""),
    path: str = Form(""),
    is_enabled: str | None = Form(None),
    message_text: str = Form(...),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    payload = {
        "message_kind": message_kind.strip(),
        "bulletin_code": bulletin_code.strip(),
        "group_name": group_name.strip(),
        "interval_minutes": interval_minutes.strip(),
        "activation_mode": activation_mode.strip(),
        "active_from_utc": active_from_utc.strip(),
        "active_until_utc": active_until_utc.strip(),
        "recurrence_duration_minutes": recurrence_duration_minutes.strip(),
        "recurrence_interval_value": recurrence_interval_value.strip(),
        "recurrence_interval_unit": recurrence_interval_unit.strip(),
        "path": path.strip(),
        "is_enabled": is_enabled,
        "message_text": message_text.strip(),
    }
    if record_id is None:
        success, error = safe_create_section_row("bulletins", payload)
        if success:
            created_row = fetch_one("SELECT id FROM bulletins ORDER BY id DESC LIMIT 1")
            if created_row is not None:
                created_id = int(created_row["id"])
                if wants_json:
                    return JSONResponse(
                        {
                            "ok": True,
                            "message": _translate("Bulletin saved."),
                            "reload": True,
                            "redirect": _path(request, f"/bulletins?edit={created_id}"),
                        }
                    )
                return _section_edit_redirect(request, "bulletins", created_id)
        edit_row = None
    else:
        success, error = safe_update_section_row("bulletins", record_id, payload)
        if success:
            if wants_json:
                return JSONResponse(
                    {
                        "ok": True,
                        "message": _translate("Bulletin saved."),
                        "reload": True,
                        "redirect": _path(request, f"/bulletins?edit={record_id}"),
                    }
                )
            return _section_edit_redirect(request, "bulletins", record_id)
        edit_row = get_section_row("bulletins", record_id) if error else None
    context = _section_template_context(request, current_user, "bulletins", flash=None if success else error, edit_row=edit_row)
    if wants_json:
        if success:
            return JSONResponse(
                {
                    "ok": True,
                    "message": _translate("Bulletin saved."),
                    "reload": True,
                    "redirect": _path(request, "/bulletins"),
                }
            )
        return JSONResponse(
            {"ok": False, "error": _translate(error or "Failed to save bulletin.")},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.post("/settings/bulletins/{record_id}/send")
def bulletins_send_now(
    record_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    row = get_section_row("bulletins", record_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bulletin not found.")

    station_settings = get_station_settings()
    success, flash = enqueue_message_job(row, station_settings, trigger="manual", force_send=True)
    if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        return JSONResponse(
            {
                "ok": success,
                "message" if success else "error": _translate(flash or "Failed to send bulletin."),
                "reload": success,
                "redirect": _path(request, f"/bulletins?edit={record_id}"),
            },
            status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(
        url=_path(
            request,
            f"/bulletins?edit={record_id}&flash={quote(str(flash or '') )}&success={'1' if success else '0'}",
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/settings/bulletins/{record_id}/delete")
def bulletins_delete(
    record_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    delete_section_row("bulletins", record_id)
    if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        return JSONResponse(
            {
                "ok": True,
                "message": _translate("Bulletin deleted."),
                "reload": True,
                "redirect": _path(request, "/bulletins"),
            }
        )
    return RedirectResponse(url=_path(request, "/bulletins"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/station")
def station_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    context = _station_page_context(request, current_user)
    return templates.TemplateResponse("station.html", context)


@router.get("/map")
def map_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    station_settings = get_station_settings()
    station_callsign = str(station_settings.get("callsign") or "").strip().upper()
    station_ssid = str(station_settings.get("ssid") or "").strip()
    if station_ssid == "0":
        station_ssid = ""
    map_station_source_key = station_callsign
    if station_callsign and station_ssid:
        map_station_source_key = f"{station_callsign}-{station_ssid}"
    context = build_template_context(
        request,
        page_title="Map",
        current_user=current_user,
        active_nav="map",
        body_class="page-map",
        map_config=get_map_page_config(root_path=request.scope.get("root_path", "")),
        map_station_source_key=map_station_source_key,
        map_stations_endpoint=_path(request, "/api/map/stations-lite"),
        map_alert_areas_endpoint=_path(request, "/api/map/alert-areas"),
        map_station_details_endpoint=_path(request, "/api/map/stations-details"),
        map_mobile_tracks_endpoint=_path(request, "/api/map/mobile-tracks"),
        map_tile_events_endpoint=_path(request, "/api/map/tile-events"),
        map_traffic_stream_endpoint=_path(request, "/api/traffic/stream"),
    )
    return templates.TemplateResponse("map.html", context)


@router.get("/api/map/stations-lite")
def map_stations_lite(
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(get_map_station_markers_payload())


@router.get("/api/map/alert-areas")
def map_alert_areas(
    request: Request,
    _: UserIdentity = Depends(get_current_user),
) -> Response:
    payload = get_map_alert_areas_payload()
    revision = str(payload.get("revision") or "empty")
    etag = f'"map-alert-areas-{revision}"'
    response_headers = {
        "Cache-Control": "private, no-cache",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=response_headers)
    return JSONResponse(payload, headers=response_headers)


@router.get("/api/map/stations-details")
def map_station_details(
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(get_map_station_details_payload())


@router.get("/api/map/mobile-tracks")
def map_mobile_tracks(
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(get_map_mobile_tracks_payload())


@router.get("/api/map/stations")
def map_stations(
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(get_map_station_payload())


@router.get("/api/map/tiles/{source_id}/{z}/{x}/{y}")
def map_tiles_proxy(
    source_id: int,
    z: int,
    x: int,
    y: int,
    request: Request,
    _: UserIdentity = Depends(get_current_user),
) -> Response:
    requested_subdomain = str(request.query_params.get("s") or "").strip()
    try:
        result = resolve_map_tile(
            source_id=source_id,
            z=z,
            x=x,
            y=y,
            requested_subdomain=requested_subdomain,
        )
    except MapTileProxyError as exc:
        return Response(content=exc.message, status_code=exc.status_code, media_type="text/plain")

    if result.cache_hit and result.cache_path is not None:
        return FileResponse(path=result.cache_path)
    return Response(content=result.body or b"", media_type=result.media_type or "application/octet-stream")


@router.post("/api/map/tile-events")
async def map_tile_events(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": _translate("Invalid JSON payload.")}, status_code=status.HTTP_400_BAD_REQUEST)
    if not isinstance(payload, dict):
        return JSONResponse({"error": _translate("Invalid JSON payload.")}, status_code=status.HTTP_400_BAD_REQUEST)

    event_type = str(payload.get("event_type") or "").strip().lower()
    if event_type not in {"tile_error", "tile_recovered"}:
        return JSONResponse({"error": _translate("Unsupported event type.")}, status_code=status.HTTP_400_BAD_REQUEST)

    source_name = str(payload.get("source_name") or "").strip()[:120]
    provider_url = str(payload.get("provider_url") or "").strip()[:512]
    tile_url = str(payload.get("tile_url") or "").strip()[:512]
    error_count = _safe_positive_int(payload.get("error_count"))
    load_count = _safe_positive_int(payload.get("load_count"))

    message = (
        f"tile_event={event_type}"
        f", source={source_name or '-'}"
        f", provider={provider_url or '-'}"
        f", tile={tile_url or '-'}"
        f", errors={error_count}"
        f", loads={load_count}"
        f", user={current_user.username}"
    )
    log_event("WARNING" if event_type == "tile_error" else "INFO", "map", message)
    return JSONResponse({"ok": True})


@router.get("/wx")
def wx_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    edit_source: int | None = None,
) -> object:
    templates = request.app.state.templates
    context = _wx_page_context(request, current_user, edit_source_id=edit_source)
    return templates.TemplateResponse("wx.html", context)


@router.post("/wx/config")
def wx_config_update(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    enabled: str | None = Form(None),
    ssid: str = Form(""),
    beacon_interface_id: str = Form(""),
    path: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
    refresh_interval_s: str = Form("300"),
    allow_cache_fallback: str | None = Form(None),
    default_cache_max_age_s: str = Form("900"),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    success, error = safe_save_wx_config(
        {
            "enabled": enabled,
            "ssid": ssid.strip(),
            "beacon_interface_id": beacon_interface_id.strip(),
            "path": path.strip(),
            "latitude": latitude.strip(),
            "longitude": longitude.strip(),
            "refresh_interval_s": refresh_interval_s.strip(),
            "allow_cache_fallback": allow_cache_fallback,
            "default_cache_max_age_s": default_cache_max_age_s.strip(),
        }
    )
    if wants_json:
        message = "WX configuration saved." if success else (error or "Failed to save WX configuration.")
        return JSONResponse(
            {"ok": success, "message" if success else "error": _translate(message), "reload": success},
            status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )
    context = _wx_page_context(
        request,
        current_user,
        flash="WX configuration saved." if success else error,
        flash_success=success,
    )
    return templates.TemplateResponse("wx.html", context, status_code=200 if success else status.HTTP_400_BAD_REQUEST)


@router.post("/wx/mappings")
async def wx_mappings_update(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    form = await request.form()
    payload_by_parameter: dict[str, dict[str, Any]] = {}
    for parameter_name in form.getlist("parameter_name"):
        normalized = str(parameter_name or "").strip()
        if not normalized:
            continue
        payload_by_parameter[normalized] = {
            "source_id": str(form.get(f"source_id__{normalized}") or "").strip(),
            "identifier": str(form.get(f"identifier__{normalized}") or "").strip(),
            "selector_kind": str(form.get(f"selector_kind__{normalized}") or "state").strip(),
            "selector_name": str(form.get(f"selector_name__{normalized}") or "").strip(),
            "unit_override": str(form.get(f"unit_override__{normalized}") or "").strip(),
            "cache_max_age_s": str(form.get(f"cache_max_age_s__{normalized}") or "").strip(),
        }
    success, error = safe_save_wx_mappings(payload_by_parameter)
    if wants_json:
        message = "WX mappings saved." if success else (error or "Failed to save WX mappings.")
        return JSONResponse(
            {"ok": success, "message" if success else "error": _translate(message), "reload": success},
            status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )
    context = _wx_page_context(
        request,
        current_user,
        flash="WX mappings saved." if success else error,
        flash_success=success,
    )
    return templates.TemplateResponse("wx.html", context, status_code=200 if success else status.HTTP_400_BAD_REQUEST)


@router.post("/wx/refresh")
def wx_refresh_now(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    success, _, error = safe_refresh_wx_runtime(trigger="manual")
    if wants_json:
        message = "WX refresh completed." if success else (error or "WX refresh failed.")
        return JSONResponse(
            {"ok": success, "message" if success else "error": _translate(message), "reload": success},
            status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )
    context = _wx_page_context(
        request,
        current_user,
        flash="WX refresh completed." if success else error,
        flash_success=success,
    )
    return templates.TemplateResponse("wx.html", context, status_code=200 if success else status.HTTP_400_BAD_REQUEST)


@router.post("/wx/send")
def wx_send_now(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    enabled: str | None = Form(None),
    ssid: str = Form(""),
    beacon_interface_id: str = Form(""),
    path: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
    refresh_interval_s: str = Form("300"),
    allow_cache_fallback: str | None = Form(None),
    default_cache_max_age_s: str = Form("900"),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    success, error = safe_save_wx_config(
        {
            "enabled": enabled,
            "ssid": ssid.strip(),
            "beacon_interface_id": beacon_interface_id.strip(),
            "path": path.strip(),
            "latitude": latitude.strip(),
            "longitude": longitude.strip(),
            "refresh_interval_s": refresh_interval_s.strip(),
            "allow_cache_fallback": allow_cache_fallback,
            "default_cache_max_age_s": default_cache_max_age_s.strip(),
        }
    )
    if not success:
        if wants_json:
            return JSONResponse(
                {"ok": False, "error": _translate(error or "Failed to save WX configuration.")},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        context = _wx_page_context(request, current_user, flash=error, flash_success=False)
        return templates.TemplateResponse("wx.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    refreshed, _, refresh_error = safe_refresh_wx_runtime(trigger="manual-send")
    if not refreshed:
        if wants_json:
            return JSONResponse(
                {"ok": False, "error": _translate(refresh_error or "WX refresh failed.")},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        context = _wx_page_context(request, current_user, flash=refresh_error, flash_success=False)
        return templates.TemplateResponse("wx.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    queued, queue_message = safe_enqueue_wx_outbound(trigger="manual")
    if wants_json:
        return JSONResponse(
            {"ok": queued, "message" if queued else "error": _translate(queue_message), "reload": queued},
            status_code=status.HTTP_200_OK if queued else status.HTTP_400_BAD_REQUEST,
        )
    context = _wx_page_context(request, current_user, flash=queue_message, flash_success=queued)
    return templates.TemplateResponse("wx.html", context, status_code=200 if queued else status.HTTP_400_BAD_REQUEST)


@router.post("/wx/mappings/{parameter_name}/test")
def wx_mapping_test_read(
    parameter_name: str,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    try:
        result = refresh_single_wx_mapping(parameter_name, trigger="manual-test")
        refreshed_row = (result.get("rows") or [{}])[0]
        refreshed_status = str(refreshed_row.get("status") or "").upper()
        if refreshed_status in {"LIVE", "CACHED"}:
            flash = f"WX mapping {parameter_name} refreshed with status {refreshed_status}."
            flash_success = True
            status_code = 200
        else:
            flash = str(refreshed_row.get("last_error") or f"WX mapping {parameter_name} refresh finished with status {refreshed_status or 'UNKNOWN'}.")
            flash_success = False
            status_code = status.HTTP_400_BAD_REQUEST
    except ValueError as exc:
        flash = str(exc)
        flash_success = False
        status_code = status.HTTP_400_BAD_REQUEST
    if wants_json:
        return JSONResponse(
            {"ok": flash_success, "message" if flash_success else "error": _translate(flash), "reload": flash_success},
            status_code=status_code,
        )
    context = _wx_page_context(request, current_user, flash=flash, flash_success=flash_success)
    return templates.TemplateResponse("wx.html", context, status_code=status_code)


@router.post("/wx/sources")
def wx_source_save(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    source_id: str = Form(""),
    name: str = Form(""),
    source_type: str = Form("home_assistant"),
    base_url: str = Form(""),
    auth_type: str = Form("none"),
    token: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    timeout_s: str = Form("5"),
    verify_tls: str | None = Form(None),
    enabled: str | None = Form(None),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    normalized_source_id = int(source_id) if str(source_id or "").strip() else None
    success, error, _ = safe_save_wx_source(
        {
            "name": name.strip(),
            "source_type": source_type.strip(),
            "base_url": base_url.strip(),
            "auth_type": auth_type.strip(),
            "token": token.strip(),
            "username": username,
            "password": password,
            "timeout_s": timeout_s.strip(),
            "verify_tls": verify_tls,
            "enabled": enabled,
        },
        source_id=normalized_source_id,
    )
    if wants_json:
        message = "WX source saved." if success else (error or "Failed to save WX source.")
        return JSONResponse(
            {
                "ok": success,
                "message" if success else "error": _translate(message),
                "reload": success,
                "redirect": _path(request, "/wx") if success else None,
            },
            status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )
    context = _wx_page_context(
        request,
        current_user,
        flash="WX source saved." if success else error,
        flash_success=success,
        edit_source_id=None if success else normalized_source_id,
    )
    return templates.TemplateResponse("wx.html", context, status_code=200 if success else status.HTTP_400_BAD_REQUEST)


@router.post("/wx/sources/{source_id}/delete")
def wx_source_delete(
    source_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    delete_wx_source(source_id)
    if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        return JSONResponse(
            {
                "ok": True,
                "message": _translate("WX source deleted."),
                "reload": True,
                "redirect": _path(request, "/wx"),
            }
        )
    return RedirectResponse(url=_path(request, "/wx"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/wx/sources/{source_id}/test")
def wx_source_test(
    source_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    result = test_wx_source_connection(source_id)
    if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        success = bool(result.get("ok"))
        message = "WX source connection succeeded." if success else (result.get("error") or "WX source connection failed.")
        return JSONResponse(
            {"ok": success, "message" if success else "error": _translate(message), "reload": success},
            status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )
    context = _wx_page_context(
        request,
        current_user,
        flash="WX source connection succeeded." if result.get("ok") else result.get("error"),
        flash_success=bool(result.get("ok")),
    )
    return templates.TemplateResponse("wx.html", context, status_code=200 if result.get("ok") else status.HTTP_400_BAD_REQUEST)


@router.post("/wx/sources/{source_id}/discover")
def wx_source_discover(
    source_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    result = discover_wx_source_items(source_id)
    if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        success = bool(result.get("ok"))
        message = "WX source discovery completed." if success else (result.get("error") or "WX source discovery failed.")
        return JSONResponse(
            {
                "ok": success,
                "message" if success else "error": _translate(message),
                "reload": False,
                "discovery": {
                    "items": list(result.get("items") or []),
                    "source": {"name": str((result.get("source") or {}).get("name") or "")},
                } if success else None,
            },
            status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )
    context = _wx_page_context(
        request,
        current_user,
        flash="WX source discovery completed." if result.get("ok") else result.get("error"),
        flash_success=bool(result.get("ok")),
        source_discovery=result if result.get("ok") else None,
    )
    return templates.TemplateResponse("wx.html", context, status_code=200 if result.get("ok") else status.HTTP_400_BAD_REQUEST)


@router.get("/notifications")
def notifications_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    edit_transport: int | None = None,
    edit_rule: int | None = None,
) -> object:
    templates = request.app.state.templates
    context = _notifications_page_context(
        request,
        current_user,
        edit_transport_id=edit_transport,
        edit_rule_id=edit_rule,
    )
    return templates.TemplateResponse("notifications.html", context)


@router.post("/notifications/settings")
def notifications_settings_update(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    messages_enabled: str | None = Form(None),
    messages_include_content: str | None = Form(None),
    radar_enabled: str | None = Form(None),
    radar_ignored_patterns: str = Form(""),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    success, error = safe_save_notification_settings(
        {
            "messages_enabled": messages_enabled,
            "messages_include_content": messages_include_content,
            "radar_enabled": radar_enabled,
            "radar_ignored_patterns": radar_ignored_patterns,
        }
    )
    if wants_json:
        message = "Notification settings updated." if success else (error or "Failed to save notification settings.")
        return JSONResponse(
            {
                "ok": success,
                "message" if success else "error": _translate(message),
                "reload": success,
                "redirect": _path(request, "/notifications#notification-settings") if success else None,
            },
            status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )
    context = _notifications_page_context(
        request,
        current_user,
        flash="Notification settings updated." if success else error,
        flash_success=success,
    )
    return templates.TemplateResponse("notifications.html", context, status_code=200 if success else status.HTTP_400_BAD_REQUEST)


@router.post("/notifications/transports")
def notifications_transport_save(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    transport_id: int | None = Form(None),
    name: str = Form(""),
    transport_type: str = Form("webhook"),
    enabled: str | None = Form(None),
    url: str = Form(""),
    secret_header_name: str = Form(""),
    secret_token: str = Form(""),
    bot_token: str = Form(""),
    chat_id: str = Form(""),
    timeout_s: str = Form(""),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    payload = {
        "name": name,
        "transport_type": transport_type,
        "enabled": enabled,
        "url": url,
        "secret_header_name": secret_header_name,
        "secret_token": secret_token,
        "bot_token": bot_token,
        "chat_id": chat_id,
        "timeout_s": timeout_s,
    }
    success, error, _saved_transport_id = safe_save_notification_transport(payload, transport_id=transport_id)
    if wants_json:
        message = "Notification transport saved." if success else (error or "Failed to save notification transport.")
        return JSONResponse(
            {
                "ok": success,
                "message" if success else "error": _translate(message),
                "reload": success,
                "redirect": _path(request, "/notifications#notification-transports") if success else None,
            },
            status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )
    context = _notifications_page_context(
        request,
        current_user,
        flash="Notification transport saved." if success else error,
        flash_success=success,
        edit_transport_id=None if success else transport_id,
        notification_transport_form=None if success else _notification_transport_form_from_payload(payload, transport_id=transport_id),
    )
    return templates.TemplateResponse("notifications.html", context, status_code=200 if success else status.HTTP_400_BAD_REQUEST)


@router.post("/notifications/transports/{transport_id}/test")
def notifications_transport_test(
    transport_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    result = test_notification_transport(transport_id)
    success = bool(result.get("ok"))
    if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        message = "Notification transport test succeeded." if success else str(result.get("error") or "Notification transport test failed.")
        return JSONResponse(
            {
                "ok": success,
                "message" if success else "error": _translate(message),
                "reload": success,
                "redirect": _path(request, "/notifications#notification-transports") if success else None,
            },
            status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )
    context = _notifications_page_context(
        request,
        current_user,
        flash="Notification transport test succeeded." if success else str(result.get("error") or "Notification transport test failed."),
        flash_success=success,
        edit_transport_id=transport_id,
    )
    return templates.TemplateResponse("notifications.html", context, status_code=200 if success else status.HTTP_400_BAD_REQUEST)


@router.post("/notifications/transports/{transport_id}/delete")
def notifications_transport_delete(
    transport_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    delete_notification_transport(transport_id)
    if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        return JSONResponse(
            {
                "ok": True,
                "message": _translate("Notification transport deleted."),
                "reload": True,
                "redirect": _path(request, "/notifications#notification-transports"),
            }
        )
    context = _notifications_page_context(
        request,
        current_user,
        flash="Notification transport deleted.",
        flash_success=True,
    )
    return templates.TemplateResponse("notifications.html", context)


@router.post("/notifications/radar-rules")
def notifications_radar_rule_save(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    rule_id: int | None = Form(None),
    enabled: str | None = Form(None),
    pattern: str = Form(""),
    distance_m: str = Form(""),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    payload = {
        "enabled": enabled,
        "pattern": pattern,
        "distance_m": distance_m,
    }
    success, error, _saved_rule_id = safe_save_notification_radar_rule(payload, rule_id=rule_id)
    if wants_json:
        message = "Radar rule saved." if success else (error or "Failed to save radar rule.")
        return JSONResponse(
            {
                "ok": success,
                "message" if success else "error": _translate(message),
                "reload": success,
                "redirect": _path(request, "/notifications#notification-radar-rules") if success else None,
            },
            status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )
    context = _notifications_page_context(
        request,
        current_user,
        flash="Radar rule saved." if success else error,
        flash_success=success,
        edit_rule_id=None if success else rule_id,
        notification_radar_rule_form=None if success else _notification_radar_rule_form_from_payload(payload, rule_id=rule_id),
    )
    return templates.TemplateResponse("notifications.html", context, status_code=200 if success else status.HTTP_400_BAD_REQUEST)


@router.post("/notifications/radar-rules/{rule_id}/delete")
def notifications_radar_rule_delete(
    rule_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    delete_notification_radar_rule(rule_id)
    if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        return JSONResponse(
            {
                "ok": True,
                "message": _translate("Radar rule deleted."),
                "reload": True,
                "redirect": _path(request, "/notifications#notification-radar-rules"),
            }
        )
    context = _notifications_page_context(
        request,
        current_user,
        flash="Radar rule deleted.",
        flash_success=True,
    )
    return templates.TemplateResponse("notifications.html", context)


@router.post("/station")
def station_update(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    callsign: str = Form(""),
    ssid: str = Form(""),
    beacon_interface_id: str = Form(""),
    beacon_comment: str = Form(""),
    beacon_interval_minutes: str = Form("30"),
    beacon_interval_mode: str = Form(BEACON_INTERVAL_MODE_FIXED),
    beacon_interval_minutes_fixed: str = Form("30"),
    beacon_path: str = Form(""),
    status_enabled: str | None = Form(None),
    status_text: str = Form(""),
    status_interval_minutes: str = Form("30"),
    latitude: str = Form(""),
    longitude: str = Form(""),
    symbol_table: str = Form("/"),
    symbol_code: str = Form(">"),
    symbol_overlay: str = Form(""),
    default_units: str | None = Form(None),
    tx_enabled: str | None = Form(None),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    current_default_units = get_station_settings().get("default_units", "metric")
    payload = {
        "callsign": callsign.strip(),
        "ssid": ssid.strip(),
        "beacon_interface_id": beacon_interface_id.strip(),
        "beacon_comment": beacon_comment.strip(),
        "beacon_interval_minutes": beacon_interval_minutes.strip(),
        "beacon_interval_mode": beacon_interval_mode.strip().lower(),
        "beacon_interval_minutes_fixed": beacon_interval_minutes_fixed.strip(),
        "beacon_path": beacon_path.strip(),
        "status_enabled": status_enabled,
        "status_text": status_text.strip(),
        "status_interval_minutes": status_interval_minutes.strip(),
        "latitude": latitude.strip(),
        "longitude": longitude.strip(),
        "symbol_table": symbol_table.strip(),
        "symbol_code": symbol_code.strip(),
        "symbol_overlay": symbol_overlay.strip(),
        "default_units": default_units.strip() if default_units is not None else current_default_units,
        "tx_enabled": tx_enabled,
    }
    success, error = safe_update_station_settings(payload)
    if not success:
        if wants_json:
            return JSONResponse(
                {"ok": False, "error": _translate(error or "Failed to save station settings.")},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        context = _station_page_context(request, current_user, flash=error, flash_success=False, station=payload)
        return templates.TemplateResponse("station.html", context, status_code=status.HTTP_400_BAD_REQUEST)
    if wants_json:
        return JSONResponse(
            {
                "ok": True,
                "message": _translate("Station settings saved."),
                "reload": True,
            }
        )
    context = _station_page_context(request, current_user, flash="Station settings saved.", flash_success=True)
    return templates.TemplateResponse("station.html", context)


@router.post("/station/send-beacon")
def station_send_beacon(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    callsign: str = Form(""),
    ssid: str = Form(""),
    beacon_interface_id: str = Form(""),
    beacon_comment: str = Form(""),
    beacon_interval_minutes: str = Form("30"),
    beacon_interval_mode: str = Form(BEACON_INTERVAL_MODE_FIXED),
    beacon_interval_minutes_fixed: str = Form("30"),
    beacon_path: str = Form(""),
    status_enabled: str | None = Form(None),
    status_text: str = Form(""),
    status_interval_minutes: str = Form("30"),
    latitude: str = Form(""),
    longitude: str = Form(""),
    symbol_table: str = Form("/"),
    symbol_code: str = Form(">"),
    symbol_overlay: str = Form(""),
    default_units: str | None = Form(None),
    tx_enabled: str | None = Form(None),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    current_default_units = get_station_settings().get("default_units", "metric")
    payload = {
        "callsign": callsign.strip(),
        "ssid": ssid.strip(),
        "beacon_interface_id": beacon_interface_id.strip(),
        "beacon_comment": beacon_comment.strip(),
        "beacon_interval_minutes": beacon_interval_minutes.strip(),
        "beacon_interval_mode": beacon_interval_mode.strip().lower(),
        "beacon_interval_minutes_fixed": beacon_interval_minutes_fixed.strip(),
        "beacon_path": beacon_path.strip(),
        "status_enabled": status_enabled,
        "status_text": status_text.strip(),
        "status_interval_minutes": status_interval_minutes.strip(),
        "latitude": latitude.strip(),
        "longitude": longitude.strip(),
        "symbol_table": symbol_table.strip(),
        "symbol_code": symbol_code.strip(),
        "symbol_overlay": symbol_overlay.strip(),
        "default_units": default_units.strip() if default_units is not None else current_default_units,
        "tx_enabled": tx_enabled,
    }
    success, error = safe_update_station_settings(payload)
    if not success:
        if wants_json:
            return JSONResponse(
                {"ok": False, "error": _translate(error or "Failed to save station settings.")},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        context = _station_page_context(request, current_user, flash=error, flash_success=False, station=payload)
        return templates.TemplateResponse("station.html", context, status_code=status.HTTP_400_BAD_REQUEST)
    station_settings = get_station_settings()
    success, flash = enqueue_beacon_job(station_settings)
    if wants_json:
        return JSONResponse(
            {"ok": success, "message" if success else "error": _translate(flash), "reload": success},
            status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )
    context = _station_page_context(request, current_user, flash=flash, flash_success=success, station=station_settings)
    return templates.TemplateResponse("station.html", context, status_code=200 if success else status.HTTP_400_BAD_REQUEST)


@router.post("/station/send-beacon-now")
def station_send_beacon_now(
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    station_settings = get_station_settings()
    success, message = enqueue_beacon_job(station_settings)
    return JSONResponse(
        {"ok": success, "message": message},
        status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
    )


@router.post("/station/send-status")
def station_send_status(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    callsign: str = Form(""),
    ssid: str = Form(""),
    beacon_interface_id: str = Form(""),
    beacon_comment: str = Form(""),
    beacon_interval_minutes: str = Form("30"),
    beacon_interval_mode: str = Form(BEACON_INTERVAL_MODE_FIXED),
    beacon_interval_minutes_fixed: str = Form("30"),
    beacon_path: str = Form(""),
    status_enabled: str | None = Form(None),
    status_text: str = Form(""),
    status_interval_minutes: str = Form("30"),
    latitude: str = Form(""),
    longitude: str = Form(""),
    symbol_table: str = Form("/"),
    symbol_code: str = Form(">"),
    symbol_overlay: str = Form(""),
    default_units: str | None = Form(None),
    tx_enabled: str | None = Form(None),
) -> object:
    templates = request.app.state.templates
    wants_json = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    current_default_units = get_station_settings().get("default_units", "metric")
    payload = {
        "callsign": callsign.strip(),
        "ssid": ssid.strip(),
        "beacon_interface_id": beacon_interface_id.strip(),
        "beacon_comment": beacon_comment.strip(),
        "beacon_interval_minutes": beacon_interval_minutes.strip(),
        "beacon_interval_mode": beacon_interval_mode.strip().lower(),
        "beacon_interval_minutes_fixed": beacon_interval_minutes_fixed.strip(),
        "beacon_path": beacon_path.strip(),
        "status_enabled": status_enabled,
        "status_text": status_text.strip(),
        "status_interval_minutes": status_interval_minutes.strip(),
        "latitude": latitude.strip(),
        "longitude": longitude.strip(),
        "symbol_table": symbol_table.strip(),
        "symbol_code": symbol_code.strip(),
        "symbol_overlay": symbol_overlay.strip(),
        "default_units": default_units.strip() if default_units is not None else current_default_units,
        "tx_enabled": tx_enabled,
    }
    success, error = safe_update_station_settings(payload)
    if not success:
        if wants_json:
            return JSONResponse(
                {"ok": False, "error": _translate(error or "Failed to save station settings.")},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        context = _station_page_context(request, current_user, flash=error, flash_success=False, station=payload)
        return templates.TemplateResponse("station.html", context, status_code=status.HTTP_400_BAD_REQUEST)
    station_settings = get_station_settings()
    success, flash = enqueue_status_job(station_settings)
    if wants_json:
        return JSONResponse(
            {"ok": success, "message" if success else "error": _translate(flash), "reload": success},
            status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )
    context = _station_page_context(request, current_user, flash=flash, flash_success=success, station=station_settings)
    return templates.TemplateResponse("station.html", context, status_code=200 if success else status.HTTP_400_BAD_REQUEST)


@router.get("/logs")
def logs_page(
    request: Request,
    min_level: str = "",
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    configured_min_level = _normalize_event_log_min_level(get_app_setting(EVENT_LOG_MIN_LEVEL_SETTING_KEY))
    selected_min_level = normalize_event_log_level(min_level, default=configured_min_level)
    visible_levels = event_log_levels_at_or_above(selected_min_level)
    context = build_template_context(
        request,
        page_title="Logs",
        current_user=current_user,
        active_nav="logs",
        log_rows=recent_event_logs(limit=200, min_level=selected_min_level),
        log_min_level=selected_min_level,
        log_min_level_options=[{"value": value, "label": value} for value in EVENT_LOG_VIEW_LEVEL_OPTIONS],
        log_visible_levels=visible_levels,
    )
    return templates.TemplateResponse("logs.html", context)


@router.get("/changelog")
def changelog_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    context = build_template_context(
        request,
        page_title="Changelog",
        current_user=current_user,
        active_nav="changelog",
        changelog_markdown=_read_changelog_markdown(),
    )
    return templates.TemplateResponse("changelog.html", context)


def _alerts_redirect(
    request: Request,
    path: str,
    message: str,
    *,
    success: bool = True,
) -> RedirectResponse:
    separator = "&" if "?" in path else "?"
    target = (
        f"{_path(request, path)}{separator}"
        f"flash={quote(message, safe='')}&flash_success={1 if success else 0}"
    )
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


def _alert_action_return_path(alert_id: int, return_to: str | None) -> str:
    target = str(return_to or "").strip()
    if target == "/alerts" or target.startswith("/alerts?"):
        return target
    return f"/alerts/{alert_id}"


def _own_alert_compose_page_context() -> dict[str, Any]:
    own_alert_compose = get_own_alert_compose_context()
    translator = get_translator(get_app_language())
    for group in own_alert_compose["groups"]:
        for option in group["event_options"]:
            option["translated_label"] = translator(option["label"])
        for option in group["hazard_options"]:
            option["translated_label"] = translator(option["label"])
        for option in group["level_options"]:
            option["translated_label"] = translator(option["label"])
    return own_alert_compose


@router.get("/alerts")
def alerts_page(
    request: Request,
    page: int = 1,
    flash: str | None = None,
    flash_success: bool = True,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    alerts_page_data = list_alerts(page=page)
    station = get_station_settings()
    station_callsign = str(station.get("callsign") or "").strip().upper()
    station_ssid = str(station.get("ssid") or "").strip()
    if station_ssid and station_ssid != "0":
        station_callsign = f"{station_callsign}-{station_ssid}"
    for alert in alerts_page_data["items"]:
        source_matches_station = bool(station_callsign) and (
            str(alert.get("source_callsign") or "").strip().upper()
            == station_callsign
        )
        alert["can_cancel_protocol"] = bool(
            source_matches_station
            and alert.get("destination_group")
            and alert.get("logical_alert_id")
            and alert.get("area_codes")
        )
        alert["protocol_cancel_label"] = (
            f"{str(alert.get('logical_alert_id') or '').strip().upper()} · "
            f"{str(alert.get('destination_group') or '').strip().upper()}"
        ).strip(" ·")
    context = build_template_context(
        request,
        page_title="Alerts",
        current_user=current_user,
        active_nav="alerts",
        alerts_page=alerts_page_data,
        flash=flash,
        flash_success=flash_success,
        can_manage_alerts=current_user.role in {"admin", "operator"},
    )
    return templates.TemplateResponse("alerts.html", context)


@router.get("/alerts/send")
def own_alert_send_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    context = build_template_context(
        request,
        page_title="Send alarm",
        current_user=current_user,
        active_nav="alerts",
        own_alert_compose=_own_alert_compose_page_context(),
    )
    return templates.TemplateResponse("alert_send.html", context)


@router.get("/api/alerts/send/areas")
def own_alert_area_options(
    group: str,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    try:
        payload = get_own_alert_area_options(group)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return JSONResponse(payload)


@router.post("/api/alerts/send/preview")
async def own_alert_preview(
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Invalid alarm payload.")
        return JSONResponse(preview_own_alert(payload))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/api/alerts/send")
async def own_alert_send(
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Invalid alarm payload.")
        return JSONResponse({"ok": True, **create_own_alert(payload)})
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/alerts/own/{own_alert_id}/send-now")
def own_alert_send_now_action(
    own_alert_id: int,
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> RedirectResponse:
    success, message = send_own_alert_now(own_alert_id)
    return _alerts_redirect(
        request,
        "/alerts",
        "Own alarm queued for transmission." if success else message,
        success=success,
    )


@router.post("/alerts/own/{own_alert_id}/cancel")
def own_alert_cancel_action(
    own_alert_id: int,
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> RedirectResponse:
    success, message = cancel_own_alert(own_alert_id)
    return _alerts_redirect(
        request,
        "/alerts",
        "Own alarm cancelled." if success else message,
        success=success,
    )


@router.post("/alerts/{alert_id}/cancel-protocol")
def station_alert_cancel_action(
    alert_id: int,
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> RedirectResponse:
    success, message = cancel_station_aprs_alert(alert_id)
    return _alerts_redirect(
        request,
        "/alerts",
        "Own alarm cancelled." if success else message,
        success=success,
    )


@router.get("/alerts/{alert_id}")
def alert_detail_page(
    alert_id: int,
    request: Request,
    flash: str | None = None,
    flash_success: bool = True,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    alert = get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    templates = request.app.state.templates
    root_path = request.scope.get("root_path", "")
    alert_map_config = get_alert_detail_map_config(alert, root_path=root_path)
    if alert_map_config.get("map_mode") == "station":
        station_settings = get_station_settings()
        related_entity = alert.get("related_entity")
        related_label = (
            str(related_entity.get("label") or "")
            if isinstance(related_entity, dict)
            else ""
        )
        station_context = _station_detail_context(
            related_label or str(alert.get("source_callsign") or ""),
            station_settings.get("default_units", "metric"),
            root_path=root_path,
        )
        if station_context is not None:
            station_map_config = dict(station_context["station_map_config"])
            if station_map_config.get("latitude") is None:
                station_map_config["latitude"] = alert_map_config.get("latitude")
            if station_map_config.get("longitude") is None:
                station_map_config["longitude"] = alert_map_config.get("longitude")
            station_map_config.update(
                {
                    "map_mode": "station",
                    "has_position": (
                        station_map_config.get("latitude") is not None
                        and station_map_config.get("longitude") is not None
                    ),
                }
            )
            alert_map_config = station_map_config
    context = build_template_context(
        request,
        page_title="Alert details",
        current_user=current_user,
        active_nav="alerts",
        alert=alert,
        alert_map_config=alert_map_config,
        flash=flash,
        flash_success=flash_success,
        can_manage_alerts=current_user.role in {"admin", "operator"},
    )
    return templates.TemplateResponse("alert_detail.html", context)


@router.post("/alerts/{alert_id}/mute")
def alert_mute(
    alert_id: int,
    request: Request,
    duration: str = Form(...),
    return_to: str | None = Form(None),
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> RedirectResponse:
    return_path = _alert_action_return_path(alert_id, return_to)
    try:
        changed = mute_alert(alert_id, duration)
    except ValueError:
        return _alerts_redirect(
            request,
            return_path,
            "Unsupported mute duration.",
            success=False,
        )
    if not changed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return _alerts_redirect(request, return_path, "Alert muted.")


@router.post("/alerts/{alert_id}/unmute")
def alert_unmute(
    alert_id: int,
    request: Request,
    return_to: str | None = Form(None),
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> RedirectResponse:
    if not unmute_alert(alert_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return _alerts_redirect(
        request,
        _alert_action_return_path(alert_id, return_to),
        "Alert unmuted.",
    )


@router.post("/alerts/{alert_id}/delete")
def alert_delete(
    alert_id: int,
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> RedirectResponse:
    if not delete_alert(alert_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return _alerts_redirect(request, "/alerts", "Alert deleted. Original frames remain in Traffic Monitor.")


@router.post("/alerts/delete-selected")
async def alerts_delete_selected(
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> RedirectResponse:
    form_data = await request.form()
    alert_ids: list[int] = []
    for raw_id in form_data.getlist("alert_ids"):
        try:
            alert_ids.append(int(str(raw_id)))
        except (TypeError, ValueError):
            continue
    deleted = delete_alerts(alert_ids)
    if deleted <= 0:
        return _alerts_redirect(request, "/alerts", "No alerts selected.", success=False)
    return _alerts_redirect(
        request,
        "/alerts",
        "Selected alerts deleted. Original frames remain in Traffic Monitor.",
    )


@router.get("/traffic/frames/{frame_id}")
def traffic_frame_detail_page(
    frame_id: int,
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    frame = get_traffic_frame(frame_id)
    if frame is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found")
    templates = request.app.state.templates
    context = build_template_context(
        request,
        page_title="Frame details",
        current_user=current_user,
        active_nav="traffic",
        frame=frame,
    )
    return templates.TemplateResponse("traffic_frame_detail.html", context)


@router.get("/traffic")
def traffic_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
    flash: str | None = None,
    flash_success: bool = True,
) -> object:
    templates = request.app.state.templates
    traffic_snapshot = get_traffic_snapshot()
    context = build_template_context(
        request,
        page_title="Traffic Monitor",
        current_user=current_user,
        active_nav="traffic",
        traffic_snapshot=traffic_snapshot,
        flash=flash,
        flash_success=flash_success,
        can_manage_traffic_runtime=current_user.role in {"admin", "operator"},
    )
    return templates.TemplateResponse("traffic.html", context)


@router.get("/statistics")
def statistics_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    statistics_payload = get_traffic_statistics(range_value="24h")
    statistics_devices_payload = get_traffic_devices_statistics(range_value="24h")
    statistics_users_payload = get_traffic_users_statistics(range_value="24h")
    statistics_direct_heard_payload = get_traffic_direct_heard_statistics(range_value="24h")
    context = build_template_context(
        request,
        page_title="Statistics",
        current_user=current_user,
        active_nav="statistics",
        statistics_payload=statistics_payload,
        statistics_devices_payload=statistics_devices_payload,
        statistics_users_payload=statistics_users_payload,
        statistics_direct_heard_payload=statistics_direct_heard_payload,
    )
    return templates.TemplateResponse("statistics.html", context)


@router.get("/messages")
def messages_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    context = build_template_context(
        request,
        page_title="Messages",
        current_user=current_user,
        active_nav="messages",
        messages_view=get_live_messages_page_data(),
    )
    return templates.TemplateResponse("messages.html", context)


@router.get("/api/messages")
def messages_snapshot(
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    return JSONResponse(get_live_messages_page_data())


@router.get("/api/messages/unread-status")
def messages_unread_status(
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    unread_count = get_unread_inbox_count()
    return JSONResponse({"unread_count": unread_count, "has_unread": unread_count > 0})


@router.get("/api/help")
def help_markdown_api(
    page: str | None = None,
    path: str | None = None,
    language: str | None = None,
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    resolved = _read_help_markdown(page=page, path=path, language=language)
    if resolved is None:
        return JSONResponse({"ok": False, "error": _translate("Help file not found.")}, status_code=status.HTTP_404_NOT_FOUND)
    resolved_path, markdown = resolved
    return JSONResponse(
        {
            "ok": True,
            "path": resolved_path,
            "title": _help_markdown_title(markdown, fallback=_translate("Help")),
            "markdown": markdown,
        }
    )


@router.post("/api/messages/conversations")
async def messages_create_conversation(
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    payload = await request.json()
    try:
        conversation = create_or_update_conversation(str(payload.get("callsign") or ""), path="")
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse({"conversation_id": str(conversation.get("id") or ""), "messages_view": get_live_messages_page_data()})


@router.put("/api/messages/settings")
async def messages_save_settings(
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    payload = await request.json()
    try:
        settings = save_message_settings(payload if isinstance(payload, dict) else {})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse({"ok": True, "settings": settings, "messages_view": get_live_messages_page_data()})


@router.post("/api/messages/send")
async def messages_send(
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    payload = await request.json()
    try:
        conversation_id = payload.get("conversation_id")
        if conversation_id not in {None, ""}:
            update_conversation_path(int(conversation_id), str(payload.get("path") or ""))
        message = queue_outgoing_message(
            callsign=str(payload.get("callsign") or ""),
            message_text=str(payload.get("message_text") or ""),
            path=str(payload.get("path") or ""),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse({"message_id": str(message["id"]), "messages_view": get_live_messages_page_data()})


@router.post("/api/messages/conversations/{conversation_id}/read")
def messages_mark_read(
    conversation_id: int,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    mark_conversation_read(conversation_id)
    return JSONResponse({"ok": True})


@router.post("/api/messages/conversations/{conversation_id}/path")
async def messages_update_path(
    conversation_id: int,
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    payload = await request.json()
    try:
        update_conversation_path(conversation_id, str(payload.get("path") or ""))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse({"ok": True, "messages_view": get_live_messages_page_data()})


@router.post("/api/messages/conversations/{conversation_id}/delete")
def messages_delete(
    conversation_id: int,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    delete_message_conversation(conversation_id)
    return JSONResponse({"ok": True, "messages_view": get_live_messages_page_data()})


@router.post("/api/messages/clear")
def messages_clear(
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    deleted = clear_message_inbox()
    return JSONResponse({"ok": True, "deleted": deleted, "messages_view": get_live_messages_page_data()})


@router.post("/api/messages/{message_id}/retry")
def messages_retry(
    message_id: int,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> JSONResponse:
    try:
        retry_failed_message(message_id)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse({"ok": True, "messages_view": get_live_messages_page_data()})


@router.get("/api/traffic")
async def traffic_snapshot(
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(get_traffic_snapshot())


@router.get("/api/dashboard/radio-activity")
def dashboard_radio_activity(
    range: str = "24h",
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    try:
        payload = get_dashboard_radio_activity(range_value=range)
    except ValueError:
        return JSONResponse({"error": "Unsupported range."}, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse(payload)


@router.get("/api/statistics/traffic")
def statistics_traffic(
    range: str = "24h",
    shift: int = 0,
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    try:
        payload = get_traffic_statistics(range_value=range, shift_windows=shift)
    except ValueError:
        return JSONResponse({"error": "Unsupported range."}, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse(payload)


@router.get("/api/statistics/devices")
def statistics_devices(
    range: str = "24h",
    shift: int = 0,
    window: str | None = None,
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    try:
        payload = get_traffic_devices_statistics(range_value=range, shift_windows=shift, window=window)
    except ValueError as exc:
        return JSONResponse({"error": str(exc) or "Unsupported range."}, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse(payload)


@router.get("/api/statistics/users")
def statistics_users(
    range: str = "24h",
    shift: int = 0,
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    try:
        payload = get_traffic_users_statistics(range_value=range, shift_windows=shift)
    except ValueError as exc:
        return JSONResponse({"error": str(exc) or "Unsupported range."}, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse(payload)


@router.get("/api/statistics/direct-heard")
def statistics_direct_heard(
    range: str = "24h",
    shift: int = 0,
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    try:
        payload = get_traffic_direct_heard_statistics(range_value=range, shift_windows=shift)
    except ValueError as exc:
        return JSONResponse({"error": str(exc) or "Unsupported range."}, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse(payload)


@router.post("/traffic/reconnect")
def traffic_reconnect(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    result = restart_core_traffic_monitor()
    flash = "Traffic monitor runtime restarted." if result.get("ok") else str(result.get("error") or "Traffic monitor restart failed.")
    context = build_template_context(
        request,
        page_title="Traffic Monitor",
        current_user=current_user,
        active_nav="traffic",
        traffic_snapshot=get_traffic_snapshot(),
        flash=flash,
        flash_success=bool(result.get("ok")),
        can_manage_traffic_runtime=True,
    )
    return templates.TemplateResponse("traffic.html", context, status_code=status.HTTP_400_BAD_REQUEST if not result.get("ok") else 200)


@router.get("/api/traffic/stream")
async def traffic_stream(
    request: Request,
    _: UserIdentity = Depends(get_current_user),
) -> StreamingResponse:
    broadcaster: TrafficSnapshotBroadcaster | None = getattr(request.app.state, "traffic_stream_broadcaster", None)
    if broadcaster is None:
        log_event("ERROR", "traffic", "Traffic SSE stream requested but broadcaster is not initialized.")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Traffic stream is unavailable.")

    try:
        subscriber_id, queue = await broadcaster.subscribe()
    except TrafficStreamCapacityError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                yield event
        finally:
            await broadcaster.unsubscribe(subscriber_id)

    # Reverse proxy note (nginx): proxy_buffering off; proxy_cache off; proxy_read_timeout sufficiently long.
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)
