from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request, status

from app.auth import create_user, list_users, set_user_active
from app.dependencies import require_roles
from app.models import ROLES, UserIdentity
from app.template_helpers import build_template_context

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
def users_page(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin")),
) -> object:
    templates = request.app.state.templates
    context = build_template_context(
        request,
        page_title="Users / Roles",
        current_user=current_user,
        active_nav="users",
        users=list_users(),
        roles=ROLES,
        flash=None,
    )
    return templates.TemplateResponse("users.html", context)


@router.post("/users")
def users_create(
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin")),
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    is_active: str | None = Form(None),
) -> object:
    templates = request.app.state.templates
    flash = "User created."
    status_code = status.HTTP_200_OK
    try:
        create_user(username=username.strip(), password=password, role=role, is_active=bool(is_active))
    except (ValueError, sqlite3.IntegrityError) as exc:
        flash = str(exc)
        status_code = status.HTTP_400_BAD_REQUEST
    context = build_template_context(
        request,
        page_title="Users / Roles",
        current_user=current_user,
        active_nav="users",
        users=list_users(),
        roles=ROLES,
        flash=flash,
    )
    return templates.TemplateResponse("users.html", context, status_code=status_code)


@router.post("/users/{user_id}/toggle")
def users_toggle(
    user_id: int,
    request: Request,
    current_user: UserIdentity = Depends(require_roles("admin")),
    is_active: int = Form(...),
) -> object:
    templates = request.app.state.templates
    set_user_active(user_id, bool(is_active))
    context = build_template_context(
        request,
        page_title="Users / Roles",
        current_user=current_user,
        active_nav="users",
        users=list_users(),
        roles=ROLES,
        flash="User status updated.",
    )
    return templates.TemplateResponse("users.html", context)
