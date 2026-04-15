from __future__ import annotations

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import RedirectResponse

from app.auth import authenticate_user, mark_user_login
from app.db import log_event
from app.services.content import get_station_settings
from app.template_helpers import build_template_context

router = APIRouter()


def _path(request: Request, suffix: str) -> str:
    return f"{request.scope.get('root_path', '')}{suffix}"


@router.get("/login")
def login_page(request: Request) -> object:
    templates = request.app.state.templates
    if request.session.get("user_id"):
        return RedirectResponse(url=_path(request, "/dashboard"), status_code=status.HTTP_303_SEE_OTHER)
    station = get_station_settings()
    station_callsign = str(station.get("callsign") or "").strip()
    station_ssid = str(station.get("ssid") or "").strip()
    station_identity = None
    if station_callsign:
        normalized_ssid = station_ssid if station_ssid and station_ssid != "0" else ""
        station_identity = station_callsign if not normalized_ssid else f"{station_callsign}-{normalized_ssid}"
    else:
        station_identity = "N0CALL"
    context = build_template_context(
        request,
        page_title="Login",
        login_error=None,
        station_identity=station_identity,
    )
    return templates.TemplateResponse("login.html", context)


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
) -> object:
    templates = request.app.state.templates
    client_ip = request.app.state.get_client_ip(request)
    normalized_username = username.strip()
    if not normalized_username or not password:
        context = build_template_context(
            request,
            page_title="Login",
            login_error="Invalid username or password.",
        )
        attempted_username = normalized_username if normalized_username else "<empty>"
        log_event("WARNING", "auth", f"Failed login attempt for {attempted_username} from {client_ip}")
        return templates.TemplateResponse("login.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    user = authenticate_user(username=normalized_username, password=password)
    if not user:
        context = build_template_context(
            request,
            page_title="Login",
            login_error="Invalid username or password.",
        )
        log_event("WARNING", "auth", f"Failed login attempt for {normalized_username} from {client_ip}")
        return templates.TemplateResponse("login.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role
    mark_user_login(user.id)
    log_event("INFO", "auth", f"User {user.username} logged in from {client_ip}")
    return RedirectResponse(url=_path(request, "/dashboard"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    username = request.session.get("username", "unknown")
    client_ip = request.app.state.get_client_ip(request)
    request.session.clear()
    log_event("INFO", "auth", f"Session ended for {username} from {client_ip}")
    return RedirectResponse(url=_path(request, "/login"), status_code=status.HTTP_303_SEE_OTHER)
