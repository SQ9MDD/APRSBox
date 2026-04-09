from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

DISPLAY_DATETIME_FORMAT = "%Y.%m.%d %H:%M"


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_display_datetime(value: Any, *, use_utc: bool = False) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return str(value or "").strip()
    display = parsed.astimezone(timezone.utc) if use_utc else parsed.astimezone()
    return display.strftime(DISPLAY_DATETIME_FORMAT)
