from __future__ import annotations

import re
from typing import Any


DEFAULT_ALERT_EVENT_ICON = "alert-outline.svg"

ALERT_EVENT_CATEGORIES: tuple[dict[str, Any], ...] = (
    {"key": "TORNADO", "label": "Tornado", "prefixes": ("TORNADO",), "icon": "weather-tornado.svg"},
    {"key": "HURRICANE", "label": "Hurricane / cyclone", "prefixes": ("HURRICANE", "CYCLONE"), "icon": "weather-hurricane.svg"},
    {"key": "THUNDERSTORM", "label": "Thunderstorm", "prefixes": ("TSTORM", "THUNDERSTORM", "THUNDER", "LIGHTNING"), "icon": "weather-lightning-rainy.svg"},
    {"key": "HAIL", "label": "Hail", "prefixes": ("HAIL",), "icon": "weather-hail.svg"},
    {"key": "RAIN", "label": "Rain", "prefixes": ("RAIN", "SHOWER", "PRECIP"), "icon": "weather-pouring.svg"},
    {"key": "FLOOD", "label": "Flood / surge", "prefixes": ("FLASHFLOOD", "FLOOD", "SURGE"), "icon": "home-flood.svg"},
    {"key": "WIND", "label": "Wind / gale", "prefixes": ("WIND", "GALE"), "icon": "weather-windy.svg"},
    {"key": "HEAT", "label": "Heat", "prefixes": ("HEAT", "HOT"), "icon": "heat-wave.svg"},
    {"key": "COLD", "label": "Cold / frost / ice", "prefixes": ("COLD", "FROST", "FREEZE", "ICE"), "icon": "thermometer-low.svg"},
    {"key": "SNOW", "label": "Snow / blizzard", "prefixes": ("SNOW", "BLIZZARD"), "icon": "weather-snowy-heavy.svg"},
    {"key": "FOG", "label": "Fog / mist", "prefixes": ("FOG", "MIST"), "icon": "weather-fog.svg"},
    {"key": "FIRE", "label": "Wildfire / fire", "prefixes": ("WILDFIRE", "FIRE"), "icon": "fire-alert.svg"},
    {"key": "DUST", "label": "Dust / sand", "prefixes": ("DUST", "SAND"), "icon": "weather-dust.svg"},
    {"key": "CLOUD", "label": "Cloud", "prefixes": ("CLOUD",), "icon": "weather-cloudy-alert.svg"},
    {"key": "OTHER", "label": "Other / unknown", "prefixes": (), "icon": DEFAULT_ALERT_EVENT_ICON},
)


def normalize_alert_event_family(event_code: Any) -> str:
    compact = re.sub(r"[^A-Z0-9]+", "", str(event_code or "").strip().upper())
    return re.sub(r"[0-9]+$", "", compact)


def resolve_alert_event_category(event_code: Any) -> str:
    family = normalize_alert_event_family(event_code)
    for category in ALERT_EVENT_CATEGORIES:
        prefixes = tuple(category["prefixes"])
        if prefixes and family.startswith(prefixes):
            return str(category["key"])
    return "OTHER"


def resolve_alert_event_label(event_code: Any) -> str | None:
    """Return a descriptive label only when the event family is recognized."""

    category_key = resolve_alert_event_category(event_code)
    if category_key == "OTHER":
        return None
    return next(
        str(category["label"])
        for category in ALERT_EVENT_CATEGORIES
        if category["key"] == category_key
    )


def resolve_alert_event_icon(
    event_code: Any,
    *,
    alert_type: Any = "",
) -> str:
    family = normalize_alert_event_family(event_code)
    if not family:
        family = normalize_alert_event_family(alert_type)
    for category in ALERT_EVENT_CATEGORIES:
        prefixes = tuple(category["prefixes"])
        if family.startswith(prefixes):
            return str(category["icon"])
    return DEFAULT_ALERT_EVENT_ICON
