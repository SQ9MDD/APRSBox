from __future__ import annotations

from typing import Any

from fastapi import Request

from app.db import fetch_one, get_app_setting
from app import get_version
from app.datetime_utils import format_display_datetime
from app.i18n import get_app_language, get_format_translator, get_supported_languages, get_translator
from app.ui_palette import normalize_ui_palette
from app.services.messages import get_unread_inbox_count


PRIMARY_NAV = [
    {"key": "dashboard", "label": "Dashboard", "href": "/dashboard", "roles": ("admin", "operator", "viewer"), "icon": "view-dashboard-outline.svg"},
    {"key": "stations", "label": "Stations", "href": "/stations", "roles": ("admin", "operator", "viewer"), "icon": "account-multiple.svg"},
    {"key": "map", "label": "Map", "href": "/map", "roles": ("admin", "operator", "viewer"), "icon": "map-outline.svg"},
    {"key": "band-condition", "label": "Band Condition", "href": "/band-condition", "roles": ("admin", "operator", "viewer"), "icon": "chart-line.svg"},
    {"key": "modems", "label": "TNC", "href": "/settings/modems", "roles": ("admin", "operator", "viewer"), "icon": "radio-handheld.svg"},
    {"key": "traffic", "label": "Traffic Monitor", "href": "/traffic", "roles": ("admin", "operator", "viewer"), "icon": "radio-tower.svg"},
    {"key": "statistics", "label": "Statistics", "href": "/statistics", "roles": ("admin", "operator", "viewer"), "icon": "chart-bar-stacked.svg"},
    {"key": "nav-separator-primary", "separator": True, "roles": ("admin", "operator", "viewer")},
    {"key": "station", "label": "My Station", "href": "/station", "roles": ("admin", "operator", "viewer"), "icon": "antenna.svg"},
    {"key": "wx", "label": "WX", "href": "/wx", "roles": ("admin", "operator", "viewer"), "icon": "weather-partly-snowy.svg"},
    {"key": "messages", "label": "Messages", "href": "/messages", "roles": ("admin", "operator", "viewer"), "icon": "message-reply-text-outline.svg"},
    {"key": "notifications", "label": "Notifications", "href": "/notifications", "roles": ("admin", "operator", "viewer"), "icon": "bell-outline.svg"},
    {"key": "objects", "label": "Objects / Items", "href": "/objects", "roles": ("admin", "operator", "viewer"), "icon": "crosshairs.svg"},
    {"key": "bulletins", "label": "Bulletins", "href": "/bulletins", "roles": ("admin", "operator", "viewer"), "icon": "message-text-outline.svg"},
    {"key": "digi-flows", "label": "Packet Routing", "href": "/digi-flows", "roles": ("admin", "operator", "viewer"), "icon": "source-branch-check.svg"},
    {"key": "igate", "label": "iGATE settings", "href": "/igate", "roles": ("admin", "operator", "viewer"), "icon": "lan-connect.svg"},
    {"key": "nav-separator-secondary", "separator": True, "roles": ("admin", "operator", "viewer")},
    {"key": "logs", "label": "Logs", "href": "/logs", "roles": ("admin", "operator", "viewer"), "icon": "book-open-variant.svg"},
    {"key": "users", "label": "Users / Roles", "href": "/admin/users", "roles": ("admin",), "icon": "account-cog.svg"},
    {"key": "settings", "label": "Settings", "href": "/settings", "roles": ("admin", "operator", "viewer"), "icon": "cog.svg"},
    {"key": "changelog", "label": "Changelog", "href": "/changelog", "roles": ("admin", "operator", "viewer"), "icon": "language-markdown-outline.svg"},
]


def _normalize_station_callsign(value: object) -> str:
    callsign = str(value or "").strip().upper()
    return callsign or "N0CALL"


def _normalize_station_ssid(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if not text.isdigit():
        return ""
    parsed = int(text)
    if parsed <= 0 or parsed > 15:
        return ""
    return str(parsed)


def _resolve_station_identity() -> str:
    try:
        row = fetch_one("SELECT callsign, ssid FROM station_settings WHERE id = 1")
    except Exception:
        row = None
    callsign = _normalize_station_callsign(row["callsign"] if row else "")
    ssid = _normalize_station_ssid(row["ssid"] if row else "")
    return f"{callsign}-{ssid}" if ssid else callsign


def build_template_context(
    request: Request,
    *,
    page_title: str,
    current_user: Any = None,
    active_nav: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    app_language = get_app_language()
    translate = get_translator(app_language)
    translate_format = get_format_translator(app_language)
    station_identity = _resolve_station_identity()
    current_ui_palette = normalize_ui_palette(get_app_setting("ui_palette"))
    unread_inbox_count = get_unread_inbox_count() if current_user else 0
    navigation: list[dict[str, Any]] = []
    for item in PRIMARY_NAV:
        if current_user and current_user.role in item["roles"]:
            translated_item = dict(item)
            if not item.get("separator"):
                translated_item["label"] = translate(item["label"])
                if item["key"] == "messages":
                    translated_item["has_unread"] = unread_inbox_count > 0
                    translated_item["unread_count"] = unread_inbox_count
                    if unread_inbox_count > 0:
                        translated_item["icon"] = "message-alert-outline.svg"
            navigation.append(translated_item)

    return {
        "request": request,
        "page_title": translate(page_title),
        "page_title_raw": page_title,
        "station_identity": station_identity,
        "browser_title": f"APRSBox: {station_identity}",
        "app_version": get_version(),
        "app_language": app_language,
        "app_languages": get_supported_languages(),
        "current_user": current_user,
        "active_nav": active_nav,
        "navigation": navigation,
        "t": translate,
        "tf": translate_format,
        "format_datetime": format_display_datetime,
        "current_ui_palette": current_ui_palette,
        **extra,
    }
