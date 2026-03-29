from __future__ import annotations

from typing import Any

from fastapi import Request

from app import __version__


PRIMARY_NAV = [
    {"key": "dashboard", "label": "Dashboard", "href": "/dashboard", "roles": ("admin", "operator", "viewer")},
    {"key": "modems", "label": "Settings / Modems", "href": "/settings/modems", "roles": ("admin", "operator", "viewer")},
    {"key": "servers", "label": "Settings / APRS-IS Servers", "href": "/settings/servers", "roles": ("admin", "operator", "viewer")},
    {"key": "station", "label": "Station Settings", "href": "/station", "roles": ("admin", "operator", "viewer")},
    {"key": "igate", "label": "iGate Rules", "href": "/igate", "roles": ("admin", "operator", "viewer")},
    {"key": "digi", "label": "DIGI Rules", "href": "/digi", "roles": ("admin", "operator", "viewer")},
    {"key": "objects", "label": "Objects", "href": "/objects", "roles": ("admin", "operator", "viewer")},
    {"key": "items", "label": "Items", "href": "/items", "roles": ("admin", "operator", "viewer")},
    {"key": "bulletins", "label": "Bulletins", "href": "/bulletins", "roles": ("admin", "operator", "viewer")},
    {"key": "logs", "label": "Logs", "href": "/logs", "roles": ("admin", "operator", "viewer")},
    {"key": "traffic", "label": "Traffic Monitor", "href": "/traffic", "roles": ("admin", "operator", "viewer")},
    {"key": "map", "label": "Map", "href": "/map", "roles": ("admin", "operator", "viewer")},
    {"key": "users", "label": "Users / Roles", "href": "/admin/users", "roles": ("admin",)},
]


def build_template_context(
    request: Request,
    *,
    page_title: str,
    current_user: Any = None,
    active_nav: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    navigation: list[dict[str, Any]] = []
    for item in PRIMARY_NAV:
        if current_user and current_user.role in item["roles"]:
            navigation.append(item)

    return {
        "request": request,
        "page_title": page_title,
        "app_version": __version__,
        "current_user": current_user,
        "active_nav": active_nav,
        "navigation": navigation,
        **extra,
    }

