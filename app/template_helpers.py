from __future__ import annotations

from typing import Any

from fastapi import Request

from app import get_version


PRIMARY_NAV = [
    {"key": "dashboard", "label": "Dashboard", "href": "/dashboard", "roles": ("admin", "operator", "viewer"), "icon": "view-dashboard-outline.svg"},
    {"key": "stations", "label": "Stations", "href": "/stations", "roles": ("admin", "operator", "viewer"), "icon": "account-multiple.svg"},
    {"key": "map", "label": "Map", "href": "/map", "roles": ("admin", "operator", "viewer"), "icon": "map-outline.svg"},
    {"key": "band-condition", "label": "Band Condition", "href": "/band-condition", "roles": ("admin", "operator", "viewer"), "icon": "chart-line.svg"},
    {"key": "modems", "label": "TNC", "href": "/settings/modems", "roles": ("admin", "operator", "viewer"), "icon": "radio-handheld.svg"},
    {"key": "traffic", "label": "Traffic Monitor", "href": "/traffic", "roles": ("admin", "operator", "viewer"), "icon": "radio-tower.svg"},
    {"key": "nav-separator-primary", "separator": True, "roles": ("admin", "operator", "viewer")},
    {"key": "servers", "label": "Settings / APRS-IS Servers", "href": "/settings/servers", "roles": ("admin", "operator", "viewer"), "icon": "server-network.svg"},
    {"key": "station", "label": "Station Settings", "href": "/station", "roles": ("admin", "operator", "viewer"), "icon": "antenna.svg"},
    {"key": "igate", "label": "iGate Rules", "href": "/igate", "roles": ("admin", "operator", "viewer"), "icon": "router-network.svg"},
    {"key": "digi", "label": "DIGI Rules", "href": "/digi", "roles": ("admin", "operator", "viewer"), "icon": "radar.svg"},
    {"key": "objects", "label": "Objects", "href": "/objects", "roles": ("admin", "operator", "viewer"), "icon": "crosshairs.svg"},
    {"key": "items", "label": "Items", "href": "/items", "roles": ("admin", "operator", "viewer"), "icon": "playlist-check.svg"},
    {"key": "bulletins", "label": "Bulletins", "href": "/bulletins", "roles": ("admin", "operator", "viewer"), "icon": "message-text-outline.svg"},
    {"key": "logs", "label": "Logs", "href": "/logs", "roles": ("admin", "operator", "viewer"), "icon": "book-open-variant.svg"},
    {"key": "users", "label": "Users / Roles", "href": "/admin/users", "roles": ("admin",), "icon": "account-cog.svg"},
    {"key": "settings", "label": "Settings", "href": "/settings", "roles": ("admin", "operator", "viewer"), "icon": "cog.svg"},
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
        "app_version": get_version(),
        "current_user": current_user,
        "active_nav": active_nav,
        "navigation": navigation,
        **extra,
    }
