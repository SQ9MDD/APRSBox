from __future__ import annotations

import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, status

from app.auth import create_user, get_user_record_by_id, list_users, set_user_active, update_user
from app.dependencies import require_roles
from app.models import ROLES, UserIdentity
from app.template_helpers import build_template_context

router = APIRouter(prefix="/admin", tags=["admin"])


def _format_user_datetime(value: str | None) -> str:
    if not value:
        return "Never"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M:%S UTC")


def _users_template_context(
    request: Request,
    current_user: UserIdentity,
    *,
    flash: str | None,
    edit_user: dict | None = None,
    status_code: int = status.HTTP_200_OK,
) -> object:
    templates = request.app.state.templates
    users = list_users()
    for user in users:
        user["last_login_display"] = _format_user_datetime(user.get("last_login_at"))
    context = build_template_context(
        request,
        page_title="Users / Roles",
        current_user=current_user,
        active_nav="users",
        users=users,
        roles=ROLES,
        flash=flash,
        edit_user=edit_user,
    )
    return templates.TemplateResponse("users.html", context, status_code=status_code)


@router.get("/users")
def users_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin")),
    edit: int | None = None,
) -> object:
    edit_user = get_user_record_by_id(edit) if edit is not None else None
    return _users_template_context(request, current_user, flash=None, edit_user=edit_user)


@router.post("/users")
def users_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin")),
    record_id: int | None = Form(None),
    username: str = Form(...),
    password: str = Form(""),
    role: str = Form(...),
    is_active: str | None = Form(None),
) -> object:
    flash = "User created."
    status_code = status.HTTP_200_OK
    edit_user = None
    try:
        if record_id is not None:
            update_user(record_id, role=role, is_active=bool(is_active), password=password.strip() or None)
            flash = "User updated."
            edit_user = get_user_record_by_id(record_id)
        else:
            create_user(username=username.strip(), password=password, role=role, is_active=bool(is_active))
    except (ValueError, sqlite3.IntegrityError) as exc:
        flash = str(exc)
        status_code = status.HTTP_400_BAD_REQUEST
        if record_id is not None:
            edit_user = get_user_record_by_id(record_id)
    return _users_template_context(request, current_user, flash=flash, edit_user=edit_user, status_code=status_code)


@router.post("/users/{user_id}/toggle")
def users_toggle(
    user_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin")),
    is_active: int = Form(...),
) -> object:
    set_user_active(user_id, bool(is_active))
    return _users_template_context(request, current_user, flash="User status updated.")
