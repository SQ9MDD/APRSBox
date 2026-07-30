from __future__ import annotations

import re
from typing import Any

from app.db import get_app_setting, set_app_setting
from app.i18n import get_app_language, get_translator
from app.services.traffic_source import normalize_aprsis_filter


APRS_ALARM_GROUPS_SETTING_KEY = "aprs.alarm_groups"
APRS_MAP_ALARM_LEVEL_THRESHOLD_SETTING_KEY = "aprs.map_alarm_level_threshold"
APRS_GLOBAL_ALARM_LEVEL_THRESHOLD_SETTING_KEY = "aprs.global_alarm_level_threshold"
DEFAULT_APRS_ALARM_GROUPS = ("PL-WARN",)
DEFAULT_APRS_ALARM_LEVEL_THRESHOLD = 1
APRS_ALARM_LEVEL_THRESHOLDS = (1, 2, 3)

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


def normalize_aprs_alarm_level_threshold(value: Any) -> int:
    try:
        threshold = int(str(value).strip())
    except (TypeError, ValueError):
        threshold = 0
    if threshold not in APRS_ALARM_LEVEL_THRESHOLDS:
        raise ValueError(_t("Alarm level threshold must be 1, 2, or 3."))
    return threshold


def _get_aprs_alarm_level_threshold(setting_key: str) -> int:
    saved_threshold = get_app_setting(setting_key)
    if saved_threshold is None:
        return DEFAULT_APRS_ALARM_LEVEL_THRESHOLD
    try:
        return normalize_aprs_alarm_level_threshold(saved_threshold)
    except ValueError:
        return DEFAULT_APRS_ALARM_LEVEL_THRESHOLD


def get_map_alarm_level_threshold() -> int:
    return _get_aprs_alarm_level_threshold(
        APRS_MAP_ALARM_LEVEL_THRESHOLD_SETTING_KEY
    )


def save_map_alarm_level_threshold(value: Any) -> int:
    threshold = normalize_aprs_alarm_level_threshold(value)
    set_app_setting(
        APRS_MAP_ALARM_LEVEL_THRESHOLD_SETTING_KEY,
        str(threshold),
    )
    return threshold


def get_global_alarm_level_threshold() -> int:
    return _get_aprs_alarm_level_threshold(
        APRS_GLOBAL_ALARM_LEVEL_THRESHOLD_SETTING_KEY
    )


def save_global_alarm_level_threshold(value: Any) -> int:
    threshold = normalize_aprs_alarm_level_threshold(value)
    set_app_setting(
        APRS_GLOBAL_ALARM_LEVEL_THRESHOLD_SETTING_KEY,
        str(threshold),
    )
    return threshold


def alarm_severity_meets_threshold(
    severity_level: Any,
    threshold: Any,
) -> bool:
    """Keep unknown levels visible instead of silently discarding new formats."""
    try:
        normalized_severity = int(severity_level)
    except (TypeError, ValueError):
        return True
    if normalized_severity not in APRS_ALARM_LEVEL_THRESHOLDS:
        return True
    return normalized_severity >= normalize_aprs_alarm_level_threshold(threshold)


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
