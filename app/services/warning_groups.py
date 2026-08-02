from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.alarm_groups import (
    get_aprs_alarm_enabled,
    get_aprs_alarm_groups,
)
from app.services.alert_areas import alarm_group_has_geojson
from app.services.aprs_warning_identity import CAWF_EVENT_FAMILIES


@dataclass(frozen=True)
class WarningGroupProfile:
    group: str
    protocol: str
    area_encoding: str
    event_families: tuple[tuple[str, str], ...]


_WARNING_GROUP_PROFILES: dict[str, WarningGroupProfile] = {
    "PL-WARN": WarningGroupProfile(
        group="PL-WARN",
        protocol="CAWF-v1",
        area_encoding="TERYT-county",
        event_families=CAWF_EVENT_FAMILIES,
    ),
    "ES-WARN": WarningGroupProfile(
        group="ES-WARN",
        protocol="CAWF-v1",
        area_encoding="AEMET-zone-code",
        event_families=CAWF_EVENT_FAMILIES,
    ),
}


def get_warning_group_profile(value: Any) -> WarningGroupProfile | None:
    return _WARNING_GROUP_PROFILES.get(str(value or "").strip().upper())


def list_supported_warning_group_profiles(
    *,
    configured_only: bool = True,
) -> list[WarningGroupProfile]:
    if configured_only:
        if not get_aprs_alarm_enabled():
            return []
        configured = set(get_aprs_alarm_groups())
    else:
        configured = set(_WARNING_GROUP_PROFILES)
    return [
        profile
        for group, profile in _WARNING_GROUP_PROFILES.items()
        if group in configured
        and profile.protocol == "CAWF-v1"
        and bool(profile.event_families)
        and bool(profile.area_encoding)
        and alarm_group_has_geojson(group)
    ]


def list_supported_warning_groups(*, configured_only: bool = True) -> list[str]:
    return [
        profile.group
        for profile in list_supported_warning_group_profiles(
            configured_only=configured_only
        )
    ]


def warning_event_options(group: Any) -> list[dict[str, Any]]:
    profile = get_warning_group_profile(group)
    if profile is None:
        return []
    return [
        {
            "code": f"{family}{level}",
            "family": family,
            "level": level,
            "label": label,
        }
        for family, label in profile.event_families
        for level in (1, 2, 3)
    ]


def warning_hazard_options(group: Any) -> list[dict[str, Any]]:
    """Return the profile's event families without the protocol severity suffix."""

    profile = get_warning_group_profile(group)
    if profile is None:
        return []
    return [
        {"code": family, "label": label}
        for family, label in profile.event_families
    ]


def warning_level_options() -> list[dict[str, Any]]:
    return [
        {"value": level, "label": f"Level {level}"}
        for level in (1, 2, 3)
    ]


def warning_event_is_supported(group: Any, event_code: Any) -> bool:
    normalized = str(event_code or "").strip().upper()
    return any(option["code"] == normalized for option in warning_event_options(group))
