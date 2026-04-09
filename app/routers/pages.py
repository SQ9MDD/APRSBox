from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from app.dependencies import get_current_user, require_roles
from app.db import (
    DEFAULT_EVENT_LOG_KEEP_ROWS,
    create_system_job,
    fetch_system_job,
    mark_system_job_error,
    mark_system_job_running,
    set_app_setting,
    vacuum_database,
)
from app.i18n import get_app_language, normalize_language, SUPPORTED_LANGUAGE_CODES
from app.models import UserIdentity
from app.sections import SECTION_DEFINITIONS
from app.services.content import (
    dashboard_home_data,
    delete_section_row,
    get_configured_modem_interfaces,
    get_aprs_symbol_icon_path,
    get_recent_station_packets,
    heard_stations,
    has_enabled_modem_interface,
    get_section_row,
    get_section_rows,
    get_related_ssids,
    get_visible_station_snapshots,
    recent_station_outbound_jobs,
    get_station_detail,
    get_station_settings,
    recent_event_logs,
    safe_update_station_settings,
    station_summary,
    traffic_snapshot as get_traffic_snapshot,
    safe_create_section_row,
    safe_update_section_row,
)
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
    list_digi_flows,
    safe_create_digi_flow,
    safe_update_digi_flow,
    set_digi_flow_enabled,
)
from app.services.messages import (
    create_or_update_conversation,
    delete_conversation as delete_message_conversation,
    get_messages_page_data as get_live_messages_page_data,
    get_unread_inbox_count,
    mark_conversation_read,
    queue_outgoing_message,
    retry_failed_message,
    update_conversation_path,
)
from app.services.band_condition import (
    build_station_key,
    delete_reference_station,
    get_band_condition_page_data,
    get_band_condition_snapshot,
    save_reference_station,
    split_station_key,
)
from app.services.aprs_device_identification import (
    get_aprs_device_identification_status,
    refresh_aprs_device_identification_cache,
)
from app.services.core_client import restart_core_traffic_monitor
from app.services.map_service import (
    get_map_page_config,
    get_map_station_payload,
    get_station_detail_map_config,
    get_station_detail_track_payload,
)
from app.services.outbound import enqueue_beacon_job
from app.services.system import (
    current_update_channel,
    current_gui_version,
    latest_gui_version,
    list_update_channels,
    read_update_log,
    save_update_channel,
    start_application_update_job,
    start_host_poweroff_job,
    start_host_reboot_job,
    start_service_restart_job,
)
from app.template_helpers import build_template_context
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


def _section_template_context(
    request: Request,
    current_user: UserIdentity,
    slug: str,
    flash: str | None = None,
    edit_row: dict | None = None,
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
    )
    if slug in {"objects", "items"}:
        context.update(
            {
                "map_picker_config": get_map_page_config(),
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
    return context


def _station_detail_context(callsign: str, unit_system: str) -> dict | None:
    snapshots = get_visible_station_snapshots()
    detail = get_station_detail(callsign, unit_system=unit_system, snapshots=snapshots)
    if detail is None:
        return None
    related_ssids = get_related_ssids(detail["base_callsign"], snapshots=snapshots)
    for item in related_ssids:
        item["is_current"] = item["display_callsign"].casefold() == detail["display_callsign"].casefold()
    station_track = get_station_detail_track_payload(detail["display_callsign"])
    station_map_config = get_station_detail_map_config(detail)
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
        page_title="DIGI Flow Editor" if flow_id else "New DIGI Flow",
        current_user=current_user,
        active_nav="digi-flows",
        flow_id=flow_id,
        form_data=form_data,
        type_meta=get_digi_flow_type_meta(),
        endpoint_options=get_digi_flow_endpoint_options(
            selected_target_selector=str(form_data.get("target_selector") or "").strip() or None,
            current_flow_id=flow_id,
        ),
        reference_options=get_digi_flow_reference_options(),
        source_step_types=SOURCE_STEP_TYPES,
        filter_step_types=FILTER_STEP_TYPES,
        target_step_types=TARGET_STEP_TYPES,
        flow_execution_summaries=get_digi_flow_execution_summaries(flow_id, execution_limit=10) if flow_id is not None else [],
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


def _station_form_options() -> dict[str, list[dict[str, str | int]]]:
    interface_options = [
        {
            "value": str(item["id"]),
            "label": f"{item['name']} ({item['modem_type']}, {item['band'] or '-'})",
        }
        for item in get_configured_modem_interfaces()
    ]
    return {
        "interface_options": [{"value": "", "label": "Select interface"}] + interface_options,
        "ssid_options": [{"value": "", "label": "Select SSID"}] + [{"value": str(value), "label": str(value)} for value in range(16)],
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
        "beacon_interval_options": [{"value": value, "label": f"{value}m"} for value in (15, 30, 45, 60)],
    }


def _station_page_context(
    request: Request,
    current_user: UserIdentity,
    *,
    flash: str | None = None,
    flash_success: bool = True,
    station: dict | None = None,
) -> dict:
    return build_template_context(
        request,
        page_title="My Settings",
        current_user=current_user,
        active_nav="station",
        station=station or get_station_settings(),
        can_edit=current_user.role in {"admin", "operator"},
        flash=flash,
        flash_success=flash_success,
        beacon_log_rows=recent_station_outbound_jobs(limit=20),
        map_picker_config=get_map_page_config(),
        **_station_form_options(),
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
        map_picker_config=get_map_page_config(),
        interface_options=_station_form_options()["interface_options"],
        **get_wx_page_data(edit_source_id=edit_source_id, source_discovery=source_discovery),
    )


def _settings_page_context(
    request: Request,
    current_user: UserIdentity,
    *,
    latest_version_result: dict | None = None,
    flash: str | None = None,
    flash_success: bool = True,
    current_language: str | None = None,
    current_default_units: str | None = None,
) -> dict:
    station_settings = get_station_settings()
    database_vacuum_blocked = has_enabled_modem_interface()
    update_channels = list_update_channels()
    selected_update_channel = str(update_channels.get("selected_channel") or current_update_channel())
    stable_update_channel = str(update_channels.get("stable_channel") or request.app.state.settings.gui_update_branch)
    update_channel_options = [
        {"value": str(name), "label": str(name)}
        for name in (update_channels.get("channels") or [selected_update_channel])
    ]
    update_log_snapshot = read_update_log()
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
        current_language=current_language if current_language is not None else get_app_language(),
        current_default_units=current_default_units if current_default_units is not None else station_settings.get("default_units", "metric"),
        aprs_device_identification_status=get_aprs_device_identification_status(),
        event_log_keep_rows=DEFAULT_EVENT_LOG_KEEP_ROWS,
        database_vacuum_blocked=database_vacuum_blocked,
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
    context = build_template_context(
        request,
        page_title="Dashboard",
        current_user=current_user,
        active_nav="dashboard",
        dashboard_band=dashboard_band,
        dashboard_home=dashboard_home_data(dashboard_band),
    )
    return templates.TemplateResponse("dashboard.html", context)


@router.get("/band-condition")
def band_condition_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
    edit_reference: int | None = None,
) -> object:
    templates = request.app.state.templates
    page_data = get_band_condition_page_data(edit_reference_id=edit_reference)
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


@router.post("/band-condition")
@router.post("/band-condition/reference-stations")
def band_condition_reference_station_save(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    record_id: int | None = Form(None),
    band: str = Form(...),
    station_key: str = Form(""),
    station_type: str = Form(...),
    enabled: str | None = Form(None),
    weight: str = Form("1.0"),
) -> object:
    templates = request.app.state.templates
    callsign, ssid = split_station_key(station_key)
    if not callsign and record_id is not None:
        page_data = get_band_condition_page_data(edit_reference_id=record_id)
        edit_reference = page_data.get("edit_reference") or {}
        callsign = str(edit_reference.get("callsign") or "")
        ssid = str(edit_reference.get("ssid") or "")
    success, error = save_reference_station(
        {
            "band": band,
            "callsign": callsign,
            "ssid": ssid,
            "station_type": station_type,
            "enabled": enabled,
            "weight": weight,
        },
        record_id=record_id,
    )
    page_data = get_band_condition_page_data(edit_reference_id=record_id if error else None)
    context = build_template_context(
        request,
        page_title="Band Condition",
        current_user=current_user,
        active_nav="band-condition",
        flash=None if success else error,
        selected_station_key=build_station_key(callsign, ssid),
        **page_data,
    )
    return templates.TemplateResponse("band_condition.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.post("/band-condition/reference-stations/{record_id}/delete")
def band_condition_reference_station_delete(
    record_id: int,
    request: Request,
    _: UserIdentity = Depends(require_roles("admin", "operator")),
) -> RedirectResponse:
    delete_reference_station(record_id)
    return RedirectResponse(url=_path(request, "/band-condition"), status_code=status.HTTP_303_SEE_OTHER)


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
        station_summary=station_summary(stations),
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
    station_context = _station_detail_context(callsign, station_settings.get("default_units", "metric"))
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
    current_user: UserIdentity = Depends(get_current_user),
    destination_callsign: str = Form(""),
    message_text: str = Form(""),
) -> object:
    templates = request.app.state.templates
    station_settings = get_station_settings()
    station_context = _station_detail_context(callsign, station_settings.get("default_units", "metric"))
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
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    station_settings = get_station_settings()
    station_context = _station_detail_context(callsign, station_settings.get("default_units", "metric"))
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
            "summary": station_summary(stations),
            "default_units": station_settings.get("default_units", "metric"),
        }
    )


@router.get("/settings/modems")
def modems_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
    edit: int | None = None,
) -> object:
    templates = request.app.state.templates
    edit_row = get_section_row("modems", edit) if edit is not None else None
    return templates.TemplateResponse("section.html", _section_template_context(request, current_user, "modems", edit_row=edit_row))


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
    enabled: str | None = Form(None),
    tx_blocked: str | None = Form(None),
    expose_port_enabled: str | None = Form(None),
    expose_bind_address: str = Form("0.0.0.0"),
    expose_port: int | None = Form(8002),
    expose_whitelist: str = Form(""),
    notes: str = Form(""),
) -> object:
    templates = request.app.state.templates
    normalized_modem_type = modem_type.strip().upper()
    if normalized_modem_type not in {"SERIALL", "TCP"}:
        context = _section_template_context(request, current_user, "modems", flash="Unsupported TNC type.")
        return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST)
    payload = {
        "name": name.strip(),
        "band": band.strip().lower(),
        "modem_type": normalized_modem_type,
        "device_path": device_path.strip(),
        "baud_rate": baud_rate,
        "enabled": enabled,
        "tx_blocked": tx_blocked,
        "expose_port_enabled": expose_port_enabled,
        "expose_bind_address": expose_bind_address.strip(),
        "expose_port": expose_port,
        "expose_whitelist": expose_whitelist,
        "notes": notes.strip(),
    }
    if record_id is None:
        success, error = safe_create_section_row("modems", payload)
        edit_row = None
    else:
        success, error = safe_update_section_row("modems", record_id, payload)
        edit_row = get_section_row("modems", record_id) if error else None
    context = _section_template_context(request, current_user, "modems", flash=None if success else error, edit_row=edit_row)
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
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    return templates.TemplateResponse("section.html", _section_template_context(request, current_user, "servers"))


@router.get("/settings")
def settings_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    context = _settings_page_context(request, current_user)
    return templates.TemplateResponse("settings.html", context)


@router.post("/settings/check-gui-version")
def settings_check_gui_version(
    _: UserIdentity = Depends(get_current_user),
) -> object:
    result = latest_gui_version()
    if not result.get("ok"):
        return JSONResponse({"ok": False, "error": result.get("error") or "Version check failed."}, status_code=status.HTTP_502_BAD_GATEWAY)
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
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse({"ok": True, "channel": selected})


@router.post("/settings/update-application")
def settings_update_application(
    _: Request,
    __: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    job_id = create_system_job("update-application", message="Queued.")
    result = start_application_update_job(job_id=job_id)
    if not result.get("ok"):
        mark_system_job_error(job_id, message=str(result.get("error") or "Failed to start update script."))
        return JSONResponse({"ok": False, "error": result.get("error") or "Failed to start update."}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    mark_system_job_running(
        job_id,
        pid=int(result.get("pid") or 0) or None,
        log_file=str(result.get("log_file") or "") or None,
        message="Running.",
    )
    return JSONResponse({"ok": True, "job_id": job_id, "status": "queued"}, status_code=status.HTTP_202_ACCEPTED)


@router.get("/api/settings/update/channels")
def settings_update_channels_api(
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(list_update_channels())


@router.get("/api/settings/update/channel")
def settings_update_channel_api(
    _: UserIdentity = Depends(get_current_user),
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
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse({"ok": True, "channel": selected})


@router.get("/api/settings/update/log")
def settings_update_log_api(
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(read_update_log())


@router.get("/api/settings/jobs/{job_id}")
def settings_job_status_api(
    job_id: int,
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    job = fetch_system_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return JSONResponse({"ok": True, "job": job})


@router.post("/settings/restart-services")
def settings_restart_services(
    _: Request,
    __: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    job_id = create_system_job("restart-services", message="Queued.")
    result = start_service_restart_job(job_id=job_id)
    if not result.get("ok"):
        mark_system_job_error(job_id, message=str(result.get("error") or "Failed to start restart script."))
        return JSONResponse({"ok": False, "error": result.get("error") or "Failed to start service restart."}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    mark_system_job_running(
        job_id,
        pid=int(result.get("pid") or 0) or None,
        log_file=str(result.get("log_file") or "") or None,
        message="Running.",
    )
    return JSONResponse({"ok": True, "job_id": job_id, "status": "queued"}, status_code=status.HTTP_202_ACCEPTED)


@router.post("/settings/reboot-host")
def settings_reboot_host(
    _: Request,
    __: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    job_id = create_system_job("reboot-host", message="Queued.")
    result = start_host_reboot_job(job_id=job_id)
    if not result.get("ok"):
        mark_system_job_error(job_id, message=str(result.get("error") or "Failed to start reboot script."))
        return JSONResponse({"ok": False, "error": result.get("error") or "Failed to start host reboot."}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    mark_system_job_running(
        job_id,
        pid=int(result.get("pid") or 0) or None,
        log_file=str(result.get("log_file") or "") or None,
        message="Running.",
    )
    return JSONResponse({"ok": True, "job_id": job_id, "status": "queued"}, status_code=status.HTTP_202_ACCEPTED)


@router.post("/settings/poweroff-host")
def settings_poweroff_host(
    _: Request,
    __: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    job_id = create_system_job("poweroff-host", message="Queued.")
    result = start_host_poweroff_job(job_id=job_id)
    if not result.get("ok"):
        mark_system_job_error(job_id, message=str(result.get("error") or "Failed to start poweroff script."))
        return JSONResponse({"ok": False, "error": result.get("error") or "Failed to start host power off."}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    mark_system_job_running(
        job_id,
        pid=int(result.get("pid") or 0) or None,
        log_file=str(result.get("log_file") or "") or None,
        message="Running.",
    )
    return JSONResponse({"ok": True, "job_id": job_id, "status": "queued"}, status_code=status.HTTP_202_ACCEPTED)


@router.post("/settings/update-aprs-device-identification")
def settings_update_aprs_device_identification(
    _: Request,
    __: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    result = refresh_aprs_device_identification_cache()
    if not result.get("ok"):
        return JSONResponse(
            {"ok": False, "error": result.get("error") or "APRS device identification database update failed."},
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    return JSONResponse({"ok": True, "message": "APRS device identification database updated."})


@router.post("/settings/vacuum-db")
def settings_vacuum_db(
    _: Request,
    __: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    if has_enabled_modem_interface():
        return JSONResponse(
            {"ok": False, "error": "Disable all TNC interfaces before running database vacuum."},
            status_code=status.HTTP_409_CONFLICT,
        )

    vacuum_database()
    return JSONResponse({"ok": True, "message": "Database vacuum completed."})


@router.post("/settings/global")
def settings_update_global(
    request: Request,
    language: str = Form(...),
    default_units: str = Form(...),
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    raw_language = str(language or "").strip().lower()
    selected_language = normalize_language(language)
    selected_default_units = str(default_units or "").strip().lower()
    station_settings = get_station_settings()
    current_default_units = station_settings.get("default_units", "metric")
    if selected_language not in SUPPORTED_LANGUAGE_CODES or selected_language != raw_language:
        return JSONResponse({"ok": False, "error": "Unsupported language selection."}, status_code=status.HTTP_400_BAD_REQUEST)
    if selected_default_units not in {"metric", "imperial"}:
        return JSONResponse({"ok": False, "error": "Unsupported unit selection."}, status_code=status.HTTP_400_BAD_REQUEST)

    station_payload = dict(station_settings)
    station_payload["default_units"] = selected_default_units
    success, error = safe_update_station_settings(station_payload)
    if not success:
        return JSONResponse({"ok": False, "error": error or "Failed to update global settings."}, status_code=status.HTTP_400_BAD_REQUEST)

    set_app_setting("app_language", selected_language)
    return JSONResponse(
        {
            "ok": True,
            "message": "Global settings updated.",
            "current_language": selected_language,
            "current_default_units": selected_default_units,
            "reload": True,
        }
    )


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
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    return templates.TemplateResponse("section.html", _section_template_context(request, current_user, "igate"))


@router.post("/igate")
def igate_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    name: str = Form(...),
    direction: str = Form(...),
    is_enabled: str | None = Form(None),
    policy_text: str = Form(""),
) -> object:
    templates = request.app.state.templates
    success, error = safe_create_section_row(
        "igate",
        {
            "name": name.strip(),
            "direction": direction.strip(),
            "is_enabled": is_enabled,
            "policy_text": policy_text.strip(),
        },
    )
    context = _section_template_context(request, current_user, "igate", flash=None if success else error)
    return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.get("/digi")
def digi_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
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
    current_user: UserIdentity = Depends(get_current_user),
    flash: str | None = None,
    success: int = 0,
) -> object:
    templates = request.app.state.templates
    context = build_template_context(
        request,
        page_title="DIGI Flows",
        current_user=current_user,
        active_nav="digi-flows",
        flows=list_digi_flows(),
        can_edit=current_user.role in {"admin", "operator"},
        flash=flash,
        flash_success=bool(success),
    )
    return templates.TemplateResponse("digi_flows.html", context)


@router.get("/digi-flows/new")
def digi_flow_new_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
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
        flash = "Flow duplicated into a new draft. Change source or target before saving because the source+target pair must stay unique."
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
    current_user: UserIdentity = Depends(get_current_user),
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
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    flow = get_digi_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DIGI Flow not found")
    return JSONResponse({"flow_id": flow_id, "events": get_digi_flow_event_log(flow_id, limit=200)})


@router.get("/api/digi-flows/{flow_id}/executions")
def digi_flow_execution_summaries_api(
    flow_id: int,
    _: UserIdentity = Depends(get_current_user),
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
        flash="DIGI Flow created.",
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
        flash="DIGI Flow updated.",
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
        url=_path(request, f"/digi-flows?flash={'DIGI%20Flow%20status%20updated.'}&success=1"),
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
        url=_path(request, f"/digi-flows?flash={'DIGI%20Flow%20deleted.'}&success=1"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/objects")
def objects_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
    edit: int | None = None,
) -> object:
    templates = request.app.state.templates
    edit_row = get_section_row("objects", edit) if edit is not None else None
    return templates.TemplateResponse("section.html", _section_template_context(request, current_user, "objects", edit_row=edit_row))


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
    interval_minutes: str = Form("30"),
    path: str = Form(""),
    is_enabled: str | None = Form(None),
    comment: str = Form(""),
) -> object:
    templates = request.app.state.templates
    payload = {
        "name": name.strip(),
        "lifetime": lifetime.strip(),
        "state": state.strip(),
        "latitude": latitude.strip(),
        "longitude": longitude.strip(),
        "symbol_table": symbol_table.strip(),
        "symbol_code": symbol_code.strip(),
        "interval_minutes": interval_minutes.strip(),
        "path": path.strip(),
        "is_enabled": is_enabled,
        "comment": comment.strip(),
    }
    if record_id is None:
        success, error = safe_create_section_row("objects", payload)
        edit_row = None
    else:
        success, error = safe_update_section_row("objects", record_id, payload)
        edit_row = get_section_row("objects", record_id) if error else None
    context = _section_template_context(request, current_user, "objects", flash=None if success else error, edit_row=edit_row)
    return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.get("/items")
def items_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
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
    interval_minutes: str = Form("30"),
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
        "interval_minutes": interval_minutes.strip(),
        "path": path.strip(),
        "is_enabled": is_enabled,
        "comment": comment.strip(),
    }
    if record_id is None:
        success, error = safe_create_section_row("items", payload)
        edit_row = None
    else:
        success, error = safe_update_section_row("items", record_id, payload)
        edit_row = get_section_row("items", record_id) if error else None
    context = _section_template_context(request, current_user, "items", flash=None if success else error, edit_row=edit_row)
    return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.post("/settings/objects/{record_id}/delete")
def objects_delete(
    record_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> RedirectResponse:
    delete_section_row("objects", record_id)
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
    current_user: UserIdentity = Depends(get_current_user),
    edit: int | None = None,
) -> object:
    templates = request.app.state.templates
    edit_row = get_section_row("bulletins", edit) if edit is not None else None
    return templates.TemplateResponse("section.html", _section_template_context(request, current_user, "bulletins", edit_row=edit_row))


@router.post("/bulletins")
def bulletins_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    record_id: int | None = Form(None),
    message_kind: str = Form("bulletin"),
    bulletin_code: str = Form(""),
    group_name: str = Form(""),
    interval_minutes: str = Form("30"),
    path: str = Form(""),
    is_enabled: str | None = Form(None),
    message_text: str = Form(...),
) -> object:
    templates = request.app.state.templates
    payload = {
        "message_kind": message_kind.strip(),
        "bulletin_code": bulletin_code.strip(),
        "group_name": group_name.strip(),
        "interval_minutes": interval_minutes.strip(),
        "path": path.strip(),
        "is_enabled": is_enabled,
        "message_text": message_text.strip(),
    }
    if record_id is None:
        success, error = safe_create_section_row("bulletins", payload)
        edit_row = None
    else:
        success, error = safe_update_section_row("bulletins", record_id, payload)
        edit_row = get_section_row("bulletins", record_id) if error else None
    context = _section_template_context(request, current_user, "bulletins", flash=None if success else error, edit_row=edit_row)
    return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.post("/settings/bulletins/{record_id}/delete")
def bulletins_delete(
    record_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> RedirectResponse:
    delete_section_row("bulletins", record_id)
    return RedirectResponse(url=_path(request, "/bulletins"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/station")
def station_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
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
    context = build_template_context(
        request,
        page_title="Map",
        current_user=current_user,
        active_nav="map",
        map_config=get_map_page_config(),
        map_stations_endpoint=_path(request, "/api/map/stations"),
    )
    return templates.TemplateResponse("map.html", context)


@router.get("/api/map/stations")
def map_stations(
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(get_map_station_payload())


@router.get("/wx")
def wx_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
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
    success, _, error = safe_refresh_wx_runtime(trigger="manual")
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
        context = _wx_page_context(request, current_user, flash=error, flash_success=False)
        return templates.TemplateResponse("wx.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    refreshed, _, refresh_error = safe_refresh_wx_runtime(trigger="manual-send")
    if not refreshed:
        context = _wx_page_context(request, current_user, flash=refresh_error, flash_success=False)
        return templates.TemplateResponse("wx.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    queued, queue_message = safe_enqueue_wx_outbound(trigger="manual")
    context = _wx_page_context(request, current_user, flash=queue_message, flash_success=queued)
    return templates.TemplateResponse("wx.html", context, status_code=200 if queued else status.HTTP_400_BAD_REQUEST)


@router.post("/wx/mappings/{parameter_name}/test")
def wx_mapping_test_read(
    parameter_name: str,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
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
) -> RedirectResponse:
    delete_wx_source(source_id)
    return RedirectResponse(url=_path(request, "/wx"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/wx/sources/{source_id}/test")
def wx_source_test(
    source_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
) -> object:
    templates = request.app.state.templates
    result = test_wx_source_connection(source_id)
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
    context = _wx_page_context(
        request,
        current_user,
        flash="WX source discovery completed." if result.get("ok") else result.get("error"),
        flash_success=bool(result.get("ok")),
        source_discovery=result if result.get("ok") else None,
    )
    return templates.TemplateResponse("wx.html", context, status_code=200 if result.get("ok") else status.HTTP_400_BAD_REQUEST)


@router.post("/station")
def station_update(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    callsign: str = Form(""),
    ssid: str = Form(""),
    beacon_interface_id: str = Form(""),
    beacon_comment: str = Form(""),
    beacon_interval_minutes: str = Form("30"),
    beacon_path: str = Form(""),
    status_enabled: str | None = Form(None),
    status_text: str = Form(""),
    status_interval_minutes: str = Form("30"),
    latitude: str = Form(""),
    longitude: str = Form(""),
    symbol_table: str = Form("/"),
    symbol_code: str = Form(">"),
    default_units: str | None = Form(None),
    tx_enabled: str | None = Form(None),
) -> object:
    templates = request.app.state.templates
    current_default_units = get_station_settings().get("default_units", "metric")
    payload = {
        "callsign": callsign.strip(),
        "ssid": ssid.strip(),
        "beacon_interface_id": beacon_interface_id.strip(),
        "beacon_comment": beacon_comment.strip(),
        "beacon_interval_minutes": beacon_interval_minutes.strip(),
        "beacon_path": beacon_path.strip(),
        "status_enabled": status_enabled,
        "status_text": status_text.strip(),
        "status_interval_minutes": status_interval_minutes.strip(),
        "latitude": latitude.strip(),
        "longitude": longitude.strip(),
        "symbol_table": symbol_table.strip(),
        "symbol_code": symbol_code.strip(),
        "default_units": default_units.strip() if default_units is not None else current_default_units,
        "tx_enabled": tx_enabled,
    }
    success, error = safe_update_station_settings(payload)
    if not success:
        context = _station_page_context(request, current_user, flash=error, flash_success=False, station=payload)
        return templates.TemplateResponse("station.html", context, status_code=status.HTTP_400_BAD_REQUEST)
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
    beacon_path: str = Form(""),
    status_enabled: str | None = Form(None),
    status_text: str = Form(""),
    status_interval_minutes: str = Form("30"),
    latitude: str = Form(""),
    longitude: str = Form(""),
    symbol_table: str = Form("/"),
    symbol_code: str = Form(">"),
    default_units: str | None = Form(None),
    tx_enabled: str | None = Form(None),
) -> object:
    templates = request.app.state.templates
    current_default_units = get_station_settings().get("default_units", "metric")
    payload = {
        "callsign": callsign.strip(),
        "ssid": ssid.strip(),
        "beacon_interface_id": beacon_interface_id.strip(),
        "beacon_comment": beacon_comment.strip(),
        "beacon_interval_minutes": beacon_interval_minutes.strip(),
        "beacon_path": beacon_path.strip(),
        "status_enabled": status_enabled,
        "status_text": status_text.strip(),
        "status_interval_minutes": status_interval_minutes.strip(),
        "latitude": latitude.strip(),
        "longitude": longitude.strip(),
        "symbol_table": symbol_table.strip(),
        "symbol_code": symbol_code.strip(),
        "default_units": default_units.strip() if default_units is not None else current_default_units,
        "tx_enabled": tx_enabled,
    }
    success, error = safe_update_station_settings(payload)
    if not success:
        context = _station_page_context(request, current_user, flash=error, flash_success=False, station=payload)
        return templates.TemplateResponse("station.html", context, status_code=status.HTTP_400_BAD_REQUEST)
    station_settings = get_station_settings()
    success, flash = enqueue_beacon_job(station_settings)
    context = _station_page_context(request, current_user, flash=flash, flash_success=success, station=station_settings)
    return templates.TemplateResponse("station.html", context, status_code=200 if success else status.HTTP_400_BAD_REQUEST)


@router.get("/logs")
def logs_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    context = build_template_context(
        request,
        page_title="Logs",
        current_user=current_user,
        active_nav="logs",
        log_rows=recent_event_logs(limit=200),
    )
    return templates.TemplateResponse("logs.html", context)


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


@router.get("/messages")
def messages_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
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
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(get_live_messages_page_data())


@router.get("/api/messages/unread-status")
def messages_unread_status(
    _: UserIdentity = Depends(get_current_user),
) -> JSONResponse:
    unread_count = get_unread_inbox_count()
    return JSONResponse({"unread_count": unread_count, "has_unread": unread_count > 0})


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
    _: UserIdentity = Depends(require_roles("admin", "operator", "viewer")),
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
    async def event_generator():
        previous_payload = ""
        while True:
            if await request.is_disconnected():
                break
            snapshot = get_traffic_snapshot()
            payload = json.dumps(snapshot, separators=(",", ":"))
            if payload != previous_payload:
                previous_payload = payload
                yield f"data: {payload}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/map")
def map_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    context = build_template_context(
        request,
        page_title="Map",
        current_user=current_user,
        active_nav="map",
    )
    return templates.TemplateResponse("placeholder.html", context)
