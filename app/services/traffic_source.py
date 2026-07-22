from __future__ import annotations

from typing import Any


RF_SOURCE_KIND = "rf"
APRSIS_SOURCE_KIND = "aprsis"
APRSIS_MODEM_TYPE = "APRSIS"
DEFAULT_APRSIS_FILTER = "m/20"

# Keep the exclusion rule in one place.  SQL readers of traffic_frames use
# this predicate as well as the live RX pipeline so APRS-IS history remains
# visible without ever becoming statistical input.
STATISTICS_TRAFFIC_SQL_PREDICATE = (
    "LOWER(COALESCE(source_kind, 'rf')) <> 'aprsis'"
)


def normalize_source_kind(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized or RF_SOURCE_KIND


def should_collect_statistics(source_kind: Any) -> bool:
    return normalize_source_kind(source_kind) != APRSIS_SOURCE_KIND


def is_rf_source(source_kind: Any) -> bool:
    return normalize_source_kind(source_kind) == RF_SOURCE_KIND


def normalize_aprsis_filter(value: Any) -> str:
    filter_text = str(value or "").strip()
    if filter_text.lower().startswith("filter "):
        filter_text = filter_text[7:].strip()
    if not filter_text:
        return DEFAULT_APRSIS_FILTER
    if len(filter_text) > 512:
        raise ValueError("APRS-IS filter must be 512 characters or fewer.")
    if any(char in "\r\n" or ord(char) < 32 or ord(char) > 126 for char in filter_text):
        raise ValueError("APRS-IS filter must contain printable ASCII characters on one line.")
    return filter_text
