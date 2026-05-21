from __future__ import annotations

import re
from typing import Any

BEACON_INTERVAL_MODE_FIXED = "fixed"
BEACON_INTERVAL_MODE_PROPORTIONAL = "proportional"
PROPORTIONAL_BEACON_INTERVAL_MINUTES = 10

_PATH_HOP_SUFFIX_RE = re.compile(r".*-(\d+)$")


def normalize_beacon_interval_mode(value: Any, *, default: str = BEACON_INTERVAL_MODE_FIXED) -> str:
    text = str(value or "").strip().lower()
    if text == BEACON_INTERVAL_MODE_PROPORTIONAL:
        return BEACON_INTERVAL_MODE_PROPORTIONAL
    return default


def split_path_tokens(path: str) -> list[str]:
    return [item.strip().upper() for item in str(path or "").split(",") if item.strip()]


def classify_beacon_path(path: str) -> dict[str, Any]:
    normalized_path = str(path or "").strip().upper()
    tokens = split_path_tokens(normalized_path)
    if not tokens or all(token in {"DIRECT"} for token in tokens):
        return {
            "hop_class": 0,
            "is_direct": True,
            "is_recommended_known": True,
            "normalized_path": "",
        }

    parsed_hops: list[int] = []
    for token in tokens:
        normalized_token = token.rstrip("*")
        if normalized_token in {"DIRECT"}:
            continue
        match = _PATH_HOP_SUFFIX_RE.fullmatch(normalized_token)
        if match is None:
            continue
        hops = int(match.group(1))
        if hops < 0:
            continue
        parsed_hops.append(hops)

    if not parsed_hops:
        return {
            "hop_class": "unknown",
            "is_direct": False,
            "is_recommended_known": False,
            "normalized_path": normalized_path,
        }

    max_hops = max(parsed_hops)
    total_hops = sum(parsed_hops)
    estimated_hops = min(3, max(max_hops, total_hops))
    return {
        "hop_class": estimated_hops,
        "is_direct": estimated_hops == 0,
        "is_recommended_known": True,
        "normalized_path": normalized_path,
    }


def evaluate_beacon_health(
    *,
    beacon_interval_mode: str,
    beacon_interval_minutes: int | None,
    beacon_path: str,
) -> dict[str, Any]:
    mode = normalize_beacon_interval_mode(beacon_interval_mode)
    path_class = classify_beacon_path(beacon_path)
    hop_class = path_class["hop_class"]

    if mode == BEACON_INTERVAL_MODE_PROPORTIONAL:
        return {
            "tone": "ok",
            "is_recommended": True,
            "headline": "Recommended: frequent local beacons, rarer full-path beacons.",
            "details": [],
            "requires_confirmation": False,
            "path_classification": path_class,
        }

    if not isinstance(hop_class, int):
        return {
            "tone": "neutral",
            "is_recommended": False,
            "headline": "No recommendation available for this beacon path.",
            "details": [],
            "requires_confirmation": False,
            "path_classification": path_class,
        }

    interval = int(beacon_interval_minutes or 0)

    if hop_class <= 0:
        if interval < 10:
            return {
                "tone": "warning",
                "is_recommended": False,
                "headline": "Consider: direct path with interval shorter than 10m may increase RF traffic.",
                "details": ["Use 10m or longer."],
                "requires_confirmation": False,
                "path_classification": path_class,
            }
        return {
            "tone": "ok",
            "is_recommended": True,
            "headline": "Recommended: direct path with interval 10m or longer.",
            "details": [],
            "requires_confirmation": False,
            "path_classification": path_class,
        }

    if hop_class == 1:
        requires_confirmation = interval < 10
        if interval < 30:
            return {
                "tone": "warning",
                "is_recommended": False,
                "headline": "Consider: 1-hop path with interval shorter than 30m may increase RF traffic.",
                "details": ["Use 30m or Proportional Path."],
                "requires_confirmation": requires_confirmation,
                "path_classification": path_class,
            }
        return {
            "tone": "ok",
            "is_recommended": True,
            "headline": "Recommended: 1-hop path with interval 30m or longer.",
            "details": [],
            "requires_confirmation": False,
            "path_classification": path_class,
        }

    requires_confirmation = interval < 30
    if hop_class >= 3 and interval < 60:
        requires_confirmation = True

    if interval < 60:
        return {
            "tone": "not_recommended",
            "is_recommended": False,
            "headline": "Not recommended: 2-hop path with interval shorter than 60m.",
            "details": ["Use 60m or Proportional Path."],
            "requires_confirmation": requires_confirmation,
            "path_classification": path_class,
        }

    return {
        "tone": "ok",
        "is_recommended": True,
        "headline": "Recommended: 2-hop path with interval 60m or longer.",
        "details": [],
        "requires_confirmation": False,
        "path_classification": path_class,
    }


def proportional_path_signature(beacon_path: str) -> str:
    classification = classify_beacon_path(beacon_path)
    return f"{classification['normalized_path']}|{classification['hop_class']}"


def resolve_proportional_beacon_path(beacon_path: str, step_index: int) -> str:
    classification = classify_beacon_path(beacon_path)
    hop_class = classification["hop_class"]
    normalized_path = str(classification["normalized_path"] or "")
    tick = max(0, int(step_index or 0))

    if not isinstance(hop_class, int) or hop_class <= 0:
        return ""

    if hop_class == 1:
        if tick > 0 and tick % 3 == 0:
            return normalized_path
        return ""

    if tick > 0 and tick % 6 == 0:
        return normalized_path
    if tick > 0 and tick % 3 == 0:
        return "WIDE1-1"
    return ""


def build_proportional_schedule_lines(beacon_path: str) -> list[str]:
    classification = classify_beacon_path(beacon_path)
    hop_class = classification["hop_class"]
    normalized_path = str(classification["normalized_path"] or "")

    if not isinstance(hop_class, int) or hop_class <= 0:
        return [
            "00:00  DIRECT (first run)",
            "00:10  DIRECT",
            "00:20  DIRECT",
            "00:30  DIRECT",
            "",
            "Then cycle repeats every 10 minutes (DIRECT).",
        ]

    if hop_class == 1:
        return [
            "00:00  DIRECT (first run)",
            "00:10  DIRECT",
            "00:20  DIRECT",
            f"00:30  {normalized_path}",
            "00:40  DIRECT",
            "00:50  DIRECT",
            f"01:00  {normalized_path}",
            "01:10  DIRECT",
            "",
            "Then cycle repeats every 30 minutes (full path every third beacon).",
        ]

    return [
        "00:00  DIRECT (first run)",
        "00:10  DIRECT",
        "00:20  DIRECT",
        "00:30  WIDE1-1",
        "00:40  DIRECT",
        "00:50  DIRECT",
        f"01:00  {normalized_path}",
        "01:10  DIRECT",
        "01:20  DIRECT",
        "01:30  WIDE1-1",
        "01:40  DIRECT",
        "01:50  DIRECT",
        f"02:00  {normalized_path}",
        "02:10  DIRECT",
        "",
        "Then cycle repeats every 60 minutes (WIDE1-1 at +30m, full path at +60m).",
    ]


def build_proportional_schedule_tooltip(beacon_path: str) -> str:
    classification = classify_beacon_path(beacon_path)
    normalized_path = str(classification["normalized_path"] or "")
    lines = build_proportional_schedule_lines(beacon_path)

    if normalized_path:
        header = f"Effective schedule for {normalized_path}:"
    else:
        header = "Effective schedule:"

    return "\n".join(
        [
            header,
            "",
            *lines,
            "",
            "Proportional Path sends frequent local beacons and rarer wide-path beacons to reduce RF channel load.",
        ]
    )
