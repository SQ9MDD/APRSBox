from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse

from app.dependencies import get_current_user, require_roles
from app.models import UserIdentity
from app.sections import SECTION_DEFINITIONS
from app.services.content import (
    dashboard_summary,
    get_section_rows,
    get_station_settings,
    recent_event_logs,
    safe_create_section_row,
    update_station_settings,
)
from app.template_helpers import build_template_context

router = APIRouter()


def _section_template_context(request: Request, current_user: UserIdentity, slug: str, flash: str | None = None) -> dict:
    definition = SECTION_DEFINITIONS[slug]
    return build_template_context(
        request,
        page_title=definition.title,
        current_user=current_user,
        active_nav=definition.nav_key,
        section=definition,
        rows=get_section_rows(slug),
        flash=flash,
        can_edit=current_user.role in definition.create_roles,
    )


@router.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/dashboard")
def dashboard(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    context = build_template_context(
        request,
        page_title="Dashboard",
        current_user=current_user,
        active_nav="dashboard",
        summary=dashboard_summary(),
        recent_logs=recent_event_logs(limit=8),
    )
    return templates.TemplateResponse("dashboard.html", context)


@router.get("/settings/modems")
def modems_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    return templates.TemplateResponse("section.html", _section_template_context(request, current_user, "modems"))


@router.post("/settings/modems")
def modems_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    name: str = Form(...),
    modem_type: str = Form(...),
    device_path: str = Form(""),
    baud_rate: int | None = Form(None),
    enabled: str | None = Form(None),
    notes: str = Form(""),
) -> object:
    templates = request.app.state.templates
    success, error = safe_create_section_row(
        "modems",
        {
            "name": name.strip(),
            "modem_type": modem_type.strip(),
            "device_path": device_path.strip(),
            "baud_rate": baud_rate,
            "enabled": enabled,
            "notes": notes.strip(),
        },
    )
    context = _section_template_context(request, current_user, "modems", flash=None if success else error)
    return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.get("/settings/servers")
def servers_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    return templates.TemplateResponse("section.html", _section_template_context(request, current_user, "servers"))


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


@router.get("/objects")
def objects_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    return templates.TemplateResponse("section.html", _section_template_context(request, current_user, "objects"))


@router.post("/objects")
def objects_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    name: str = Form(...),
    latitude: str = Form(""),
    longitude: str = Form(""),
    symbol_table: str = Form("/"),
    symbol_code: str = Form(">"),
    is_enabled: str | None = Form(None),
    comment: str = Form(""),
) -> object:
    templates = request.app.state.templates
    success, error = safe_create_section_row(
        "objects",
        {
            "name": name.strip(),
            "latitude": latitude.strip(),
            "longitude": longitude.strip(),
            "symbol_table": symbol_table.strip(),
            "symbol_code": symbol_code.strip(),
            "is_enabled": is_enabled,
            "comment": comment.strip(),
        },
    )
    context = _section_template_context(request, current_user, "objects", flash=None if success else error)
    return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.get("/items")
def items_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    return templates.TemplateResponse("section.html", _section_template_context(request, current_user, "items"))


@router.post("/items")
def items_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    name: str = Form(...),
    latitude: str = Form(""),
    longitude: str = Form(""),
    symbol_table: str = Form("/"),
    symbol_code: str = Form(">"),
    is_enabled: str | None = Form(None),
    comment: str = Form(""),
) -> object:
    templates = request.app.state.templates
    success, error = safe_create_section_row(
        "items",
        {
            "name": name.strip(),
            "latitude": latitude.strip(),
            "longitude": longitude.strip(),
            "symbol_table": symbol_table.strip(),
            "symbol_code": symbol_code.strip(),
            "is_enabled": is_enabled,
            "comment": comment.strip(),
        },
    )
    context = _section_template_context(request, current_user, "items", flash=None if success else error)
    return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.get("/bulletins")
def bulletins_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    return templates.TemplateResponse("section.html", _section_template_context(request, current_user, "bulletins"))


@router.post("/bulletins")
def bulletins_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    name: str = Form(...),
    body: str = Form(...),
    cadence_minutes: int | None = Form(None),
    is_enabled: str | None = Form(None),
) -> object:
    templates = request.app.state.templates
    success, error = safe_create_section_row(
        "bulletins",
        {
            "name": name.strip(),
            "body": body.strip(),
            "cadence_minutes": cadence_minutes,
            "is_enabled": is_enabled,
        },
    )
    context = _section_template_context(request, current_user, "bulletins", flash=None if success else error)
    return templates.TemplateResponse("section.html", context, status_code=status.HTTP_400_BAD_REQUEST if error else 200)


@router.get("/station")
def station_page(
    request: Request,
    current_user: UserIdentity = Depends(get_current_user),
) -> object:
    templates = request.app.state.templates
    context = build_template_context(
        request,
        page_title="Station Settings",
        current_user=current_user,
        active_nav="station",
        station=get_station_settings(),
        can_edit=current_user.role in {"admin", "operator"},
    )
    return templates.TemplateResponse("station.html", context)


@router.post("/station")
def station_update(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin", "operator")),
    callsign: str = Form(""),
    ssid: str = Form(""),
    beacon_comment: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
    symbol_table: str = Form("/"),
    symbol_code: str = Form(">"),
    tx_enabled: str | None = Form(None),
) -> object:
    templates = request.app.state.templates
    update_station_settings(
        {
            "callsign": callsign.strip(),
            "ssid": ssid.strip(),
            "beacon_comment": beacon_comment.strip(),
            "latitude": latitude.strip(),
            "longitude": longitude.strip(),
            "symbol_table": symbol_table.strip(),
            "symbol_code": symbol_code.strip(),
            "tx_enabled": tx_enabled,
        }
    )
    context = build_template_context(
        request,
        page_title="Station Settings",
        current_user=current_user,
        active_nav="station",
        station=get_station_settings(),
        can_edit=True,
        flash="Station settings saved.",
    )
    return templates.TemplateResponse("station.html", context)


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
) -> object:
    templates = request.app.state.templates
    context = build_template_context(
        request,
        page_title="Traffic Monitor",
        current_user=current_user,
        active_nav="traffic",
    )
    return templates.TemplateResponse("placeholder.html", context)


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
