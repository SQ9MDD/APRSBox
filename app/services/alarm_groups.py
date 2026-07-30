from __future__ import annotations

import re
from typing import Any

from app.db import get_app_setting, set_app_setting
from app.i18n import get_app_language, get_translator
from app.services.traffic_source import normalize_aprsis_filter


APRS_ALARM_GROUPS_SETTING_KEY = "aprs.alarm_groups"
DEFAULT_APRS_ALARM_GROUPS = ("PL-WARN",)

_APRS_ALARM_GROUP_RE = re.compile(r"^[A-Z0-9-]{1,9}$")


def _t(message: str) -> str:
    return get_translator(get_app_language())(message)


def normalize_aprs_alarm_groups(value: Any) -> list[str]:
    """Normalize APRS alarm message addressees without touching message groups."""
    if isinstance(value, (list, tuple)):
        raw_values = value
    else:
        raw_text = str(value or "").replace("\n", ",")
        raw_values = raw_text.split(",")

    groups: list[str] = []
    for raw_value in raw_values:
        group = str(raw_value or "").strip().upper()
        if not group:
            continue
        if not _APRS_ALARM_GROUP_RE.fullmatch(group):
            raise ValueError(
                _t("Alarm groups must contain 1-9 letters, digits, or hyphens, separated by commas.")
            )
        if group.startswith("BLN"):
            raise ValueError(_t("Bulletin addresses cannot be used as APRS alarm groups."))
        if group not in groups:
            groups.append(group)
    return groups


def get_aprs_alarm_groups() -> list[str]:
    saved_groups = get_app_setting(APRS_ALARM_GROUPS_SETTING_KEY)
    if saved_groups is None:
        return list(DEFAULT_APRS_ALARM_GROUPS)
    try:
        return normalize_aprs_alarm_groups(saved_groups)
    except ValueError:
        return []


def save_aprs_alarm_groups(value: Any) -> list[str]:
    groups = normalize_aprs_alarm_groups(value)
    set_app_setting(APRS_ALARM_GROUPS_SETTING_KEY, ",".join(groups))
    return groups


def build_automatic_aprsis_alarm_filter(groups: Any | None = None) -> str:
    normalized_groups = (
        get_aprs_alarm_groups()
        if groups is None
        else normalize_aprs_alarm_groups(groups)
    )
    if not normalized_groups:
        return ""
    return f"g/{'/'.join(normalized_groups)}"


def build_effective_aprsis_filter(user_filter: Any, groups: Any | None = None) -> str:
    """Append only missing alarm-group subscriptions to the user's filter."""
    raw_user_filter = str(user_filter or "").strip()
    normalized_user_filter = (
        normalize_aprsis_filter(raw_user_filter)
        if raw_user_filter
        else ""
    )
    normalized_groups = (
        get_aprs_alarm_groups()
        if groups is None
        else normalize_aprs_alarm_groups(groups)
    )

    subscribed_groups: set[str] = set()
    for token in normalized_user_filter.split():
        if not token.lower().startswith("g/"):
            continue
        subscribed_groups.update(
            segment.strip().upper()
            for segment in token[2:].split("/")
            if segment.strip()
        )

    missing_groups = [
        group
        for group in normalized_groups
        if group not in subscribed_groups
    ]
    automatic_filter = build_automatic_aprsis_alarm_filter(missing_groups)
    if not automatic_filter:
        return normalized_user_filter
    if not normalized_user_filter:
        return automatic_filter
    return f"{normalized_user_filter} {automatic_filter}"
