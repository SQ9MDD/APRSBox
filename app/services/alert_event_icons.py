from __future__ import annotations

import re
from typing import Any


DEFAULT_ALERT_EVENT_ICON = "alert-outline.svg"

_EVENT_ICON_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("TORNADO",), "weather-tornado.svg"),
    (("HURRICANE", "CYCLONE"), "weather-hurricane.svg"),
    (("TSTORM", "THUNDERSTORM", "THUNDER", "LIGHTNING"), "weather-lightning-rainy.svg"),
    (("HAIL",), "weather-hail.svg"),
    (("RAIN", "SHOWER", "PRECIP"), "weather-pouring.svg"),
    (("FLASHFLOOD", "FLOOD", "SURGE"), "home-flood.svg"),
    (("WIND", "GALE"), "weather-windy.svg"),
    (("HEAT", "HOT"), "heat-wave.svg"),
    (("COLD", "FROST", "FREEZE", "ICE"), "thermometer-low.svg"),
    (("SNOW", "BLIZZARD"), "weather-snowy-heavy.svg"),
    (("FOG", "MIST"), "weather-fog.svg"),
    (("WILDFIRE", "FIRE"), "fire-alert.svg"),
    (("DUST", "SAND"), "weather-dust.svg"),
    (("CLOUD",), "weather-cloudy-alert.svg"),
)


def normalize_alert_event_family(event_code: Any) -> str:
    compact = re.sub(r"[^A-Z0-9]+", "", str(event_code or "").strip().upper())
    return re.sub(r"[0-9]+$", "", compact)


def resolve_alert_event_icon(
    event_code: Any,
    *,
    alert_type: Any = "",
) -> str:
    family = normalize_alert_event_family(event_code)
    if not family:
        family = normalize_alert_event_family(alert_type)
    for prefixes, icon_name in _EVENT_ICON_RULES:
        if family.startswith(prefixes):
            return icon_name
    return DEFAULT_ALERT_EVENT_ICON
