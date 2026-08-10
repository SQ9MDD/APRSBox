from __future__ import annotations

import re
from typing import Any

from app.services.alert_event_icons import resolve_alert_event_label
from app.services.aprs_warning_identity import CAWF_EVENT_FAMILIES


_LEVEL_LABELS = {
    1: ("Level 1", "Yellow"),
    2: ("Level 2", "Orange"),
    3: ("Level 3", "Red"),
}
_CAWF_LABELS = dict(CAWF_EVENT_FAMILIES)


def interpret_group_alert(
    *,
    destination_group: Any,
    event_code: Any,
    severity_level: Any,
) -> dict[str, Any]:
    """Build format-aware, human-readable warning metadata for the UI.

    CAWF has a defined event registry and a defined 1-3 colour scale.  The
    historical NWS-WARN event field is free text; APRSBox can recognize a
    category, but its numeric suffix is only the relay publisher's mapping.
    """

    group = str(destination_group or "").strip().upper()
    code = str(event_code or "").strip().upper()
    is_nws_warn = group == "NWS-WARN"
    event_family = re.sub(r"[0-9]+$", "", code)

    if is_nws_warn:
        event_label = resolve_alert_event_label(code)
        event_known = event_label is not None
        event_label = event_label or "Unrecognized sender event label"
        format_label = "NWS-WARN"
        event_note = (
            "NWS-WARN event names are sender-provided free text; APRSBox maps "
            "recognized names to a category."
        )
        severity_note = (
            "NWS-WARN level is the relay publisher's 1-3 mapping, not an "
            "official NWS CAP severity."
        )
    else:
        event_label = _CAWF_LABELS.get(event_family)
        event_known = event_label is not None
        event_label = event_label or "Unrecognized CAWF event code"
        format_label = "CAWF v1"
        event_note = (
            "CAWF event codes are interpreted against the CAWF v1 event registry."
        )
        severity_note = "CAWF v1 defines levels 1-3 as yellow, orange, and red."

    try:
        normalized_level = int(severity_level)
    except (TypeError, ValueError):
        normalized_level = None
    level_parts = _LEVEL_LABELS.get(normalized_level)

    return {
        "format_label": format_label,
        "event_label": event_label,
        "event_known": event_known,
        "event_note": event_note,
        "severity_level_label": level_parts[0] if level_parts else "Unknown level",
        "severity_color_label": level_parts[1] if level_parts else "",
        "severity_known": level_parts is not None,
        "severity_note": severity_note,
    }
