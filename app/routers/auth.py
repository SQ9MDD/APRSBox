from __future__ import annotations

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import RedirectResponse

from app.auth import authenticate_user, mark_user_login
from app.db import log_event
from app.template_helpers import build_template_context

router = APIRouter()


@router.get("/login")
def login_page(request: Request) -> object:
    templates = request.app.state.templates
    if request.session.get("user_id"):
        return RedirectResponse(url=str(request.url_for("dashboard")), status_code=status.HTTP_303_SEE_OTHER)
    context = build_template_context(request, page_title="Login", login_error=None)
    return templates.TemplateResponse("login.html", context)


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> object:
    templates = request.app.state.templates
    client_ip = request.app.state.get_client_ip(request)
    user = authenticate_user(username=username.strip(), password=password)
    if not user:
        context = build_template_context(
            request,
            page_title="Login",
            login_error="Invalid username or password.",
        )
        log_event("WARNING", "auth", f"Failed login attempt for {username.strip()} from {client_ip}")
        return templates.TemplateResponse("login.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role
    mark_user_login(user.id)
    log_event("INFO", "auth", f"User {user.username} logged in from {client_ip}")
    return RedirectResponse(url=str(request.url_for("dashboard")), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    username = request.session.get("username", "unknown")
    client_ip = request.app.state.get_client_ip(request)
    request.session.clear()
    log_event("INFO", "auth", f"Session ended for {username} from {client_ip}")
    return RedirectResponse(url=str(request.url_for("login_page")), status_code=status.HTTP_303_SEE_OTHER)
