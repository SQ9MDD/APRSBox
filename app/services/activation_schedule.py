from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from app.i18n import get_app_language, get_translator


ACTIVATION_MODE_MANUAL = "manual"
ACTIVATION_MODE_SCHEDULED = "scheduled"
ACTIVATION_MODE_RECURRING = "recurring"
ACTIVATION_MODES = {
    ACTIVATION_MODE_MANUAL,
    ACTIVATION_MODE_SCHEDULED,
    ACTIVATION_MODE_RECURRING,
}
RECURRENCE_INTERVAL_UNITS = {"day", "week", "month", "year"}
SCHEDULE_DATETIME_FIELDS = (
    "active_from_utc",
    "active_until_utc",
    "first_activation_utc",
    "recurrence_until_utc",
)
SCHEDULE_FIELDS = (
    "activation_mode",
    *SCHEDULE_DATETIME_FIELDS,
    "recurrence_duration_minutes",
    "recurrence_interval_value",
    "recurrence_interval_unit",
)


@dataclass(frozen=True)
class ActivationState:
    active_now: bool
    reason: str
    next_activation_utc: datetime | None = None
    current_window_until_utc: datetime | None = None


def normalize_activation_schedule(payload: Mapping[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("activation_mode") or ACTIVATION_MODE_MANUAL).strip().lower()
    if mode not in ACTIVATION_MODES:
        raise ValueError("Activation mode must be manual, scheduled or recurring.")

    normalized: dict[str, Any] = {"activation_mode": mode}
    for field in SCHEDULE_DATETIME_FIELDS:
        normalized[field] = normalize_optional_utc_datetime(payload.get(field), label=_field_label(field))

    normalized["recurrence_duration_minutes"] = _normalize_optional_positive_int(
        payload.get("recurrence_duration_minutes"),
        label="Active-for duration",
    )
    normalized["recurrence_interval_value"] = _normalize_optional_positive_int(
        payload.get("recurrence_interval_value"),
        label="Recurrence interval",
    )
    unit = str(payload.get("recurrence_interval_unit") or "").strip().lower() or None
    if unit is not None and unit not in RECURRENCE_INTERVAL_UNITS:
        raise ValueError("Recurrence interval unit must be day, week, month or year.")
    normalized["recurrence_interval_unit"] = unit

    if mode == ACTIVATION_MODE_SCHEDULED:
        active_from = normalized["active_from_utc"]
        active_until = normalized["active_until_utc"]
        if not active_from or not active_until:
            raise ValueError("Scheduled activation requires active-from and active-until UTC dates.")
        if parse_utc_datetime(active_until) < parse_utc_datetime(active_from):
            raise ValueError("Scheduled active-until date cannot be earlier than active-from date.")

    if mode == ACTIVATION_MODE_RECURRING:
        first_activation = normalized["first_activation_utc"]
        duration = normalized["recurrence_duration_minutes"]
        interval_value = normalized["recurrence_interval_value"]
        interval_unit = normalized["recurrence_interval_unit"]
        if not first_activation:
            raise ValueError("Recurring activation requires the first activation UTC date.")
        if duration is None:
            raise ValueError("Recurring activation requires a positive active-for duration.")
        if interval_value is None:
            raise ValueError("Recurring activation requires a positive recurrence interval.")
        if interval_unit is None:
            raise ValueError("Recurring activation requires a recurrence interval unit.")
        recurrence_until = normalized["recurrence_until_utc"]
        if recurrence_until and parse_utc_datetime(recurrence_until) < parse_utc_datetime(first_activation):
            raise ValueError("Repeat-until date cannot be earlier than the first activation date.")

    return normalized


def compute_activation_state(record: Mapping[str, Any], now: datetime) -> ActivationState:
    current = _as_utc(now)
    if not _is_enabled(record.get("is_enabled")):
        return ActivationState(active_now=False, reason="disabled")

    mode = str(record.get("activation_mode") or ACTIVATION_MODE_MANUAL).strip().lower()
    if mode == ACTIVATION_MODE_MANUAL:
        valid_until = parse_utc_datetime(record.get("valid_until_utc"), legacy_date_end_of_day=True)
        if valid_until is not None and current >= valid_until:
            return ActivationState(active_now=False, reason="manual_expired")
        return ActivationState(active_now=True, reason="manual_active", current_window_until_utc=valid_until)

    if mode == ACTIVATION_MODE_SCHEDULED:
        active_from = parse_utc_datetime(record.get("active_from_utc"))
        active_until = parse_utc_datetime(record.get("active_until_utc"))
        if active_from is None or active_until is None or active_until < active_from:
            return ActivationState(active_now=False, reason="invalid_schedule")
        if current < active_from:
            return ActivationState(active_now=False, reason="scheduled_not_started", next_activation_utc=active_from)
        if current > active_until:
            return ActivationState(active_now=False, reason="scheduled_ended")
        return ActivationState(active_now=True, reason="scheduled_active", current_window_until_utc=active_until)

    if mode != ACTIVATION_MODE_RECURRING:
        return ActivationState(active_now=False, reason="invalid_schedule")

    first_activation = parse_utc_datetime(record.get("first_activation_utc"))
    recurrence_until = parse_utc_datetime(record.get("recurrence_until_utc"))
    duration_minutes = _positive_int(record.get("recurrence_duration_minutes"))
    interval_value = _positive_int(record.get("recurrence_interval_value"))
    interval_unit = str(record.get("recurrence_interval_unit") or "").strip().lower()
    if (
        first_activation is None
        or duration_minutes is None
        or interval_value is None
        or interval_unit not in RECURRENCE_INTERVAL_UNITS
        or (recurrence_until is not None and recurrence_until < first_activation)
    ):
        return ActivationState(active_now=False, reason="invalid_schedule")
    if current < first_activation:
        return ActivationState(active_now=False, reason="recurring_not_started", next_activation_utc=first_activation)

    occurrence_index = _occurrence_index_at_or_before(
        first_activation,
        current,
        interval_value=interval_value,
        interval_unit=interval_unit,
    )
    if recurrence_until is not None:
        occurrence_index = min(
            occurrence_index,
            _occurrence_index_at_or_before(
                first_activation,
                recurrence_until,
                interval_value=interval_value,
                interval_unit=interval_unit,
            ),
        )
    window_start = _occurrence_start(
        first_activation,
        occurrence_index,
        interval_value=interval_value,
        interval_unit=interval_unit,
    )
    window_until = window_start + timedelta(minutes=duration_minutes)
    next_activation = _next_occurrence(
        first_activation,
        occurrence_index + 1,
        interval_value=interval_value,
        interval_unit=interval_unit,
        recurrence_until=recurrence_until,
    )
    if current <= window_until:
        return ActivationState(
            active_now=True,
            reason="recurring_active",
            next_activation_utc=next_activation,
            current_window_until_utc=window_until,
        )
    return ActivationState(
        active_now=False,
        reason="recurring_between_windows" if next_activation is not None else "recurring_ended",
        next_activation_utc=next_activation,
    )


def normalize_optional_utc_datetime(value: Any, *, label: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = parse_utc_datetime(text)
    if parsed is None:
        raise ValueError(f"{label} must use YYYY-MM-DD HH:MM format.")
    return parsed.strftime("%Y-%m-%d %H:%M")


def parse_utc_datetime(value: Any, *, legacy_date_end_of_day: bool = False) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    if not legacy_date_end_of_day:
        return None
    try:
        parsed_date = datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None
    return parsed_date.replace(tzinfo=timezone.utc) + timedelta(days=1)


def schedule_summary(record: Mapping[str, Any], now: datetime) -> str:
    t = get_translator(get_app_language())
    state = compute_activation_state(record, now)
    mode = str(record.get("activation_mode") or ACTIVATION_MODE_MANUAL).strip().lower()
    if mode == ACTIVATION_MODE_MANUAL:
        valid_until = str(record.get("valid_until_utc") or "").strip()
        return t("Manual activation. Valid until: {validUntil} UTC.").format(validUntil=valid_until) if valid_until else t("Manual activation.")
    if mode == ACTIVATION_MODE_SCHEDULED:
        active_from = str(record.get("active_from_utc") or "").strip()
        active_until = str(record.get("active_until_utc") or "").strip()
        return t("Active from {fromDate} UTC to {toDate} UTC.").format(fromDate=active_from, toDate=active_until)
    if mode == ACTIVATION_MODE_RECURRING:
        interval_value = _positive_int(record.get("recurrence_interval_value")) or 0
        interval_unit = str(record.get("recurrence_interval_unit") or "").strip().lower()
        duration = _positive_int(record.get("recurrence_duration_minutes")) or 0
        first_activation = str(record.get("first_activation_utc") or "").strip()
        summary = t("Active every {value} {unit} from {fromDate} UTC for {duration}.").format(
            value=interval_value,
            unit=_recurrence_unit_label(interval_unit, t),
            fromDate=first_activation,
            duration=_duration_label(duration, t),
        )
        if state.next_activation_utc is not None:
            summary += " " + t("Next activation: {date} UTC.").format(date=_format_utc(state.next_activation_utc))
        return summary
    return t("Invalid activation schedule.")


def schedule_short_label(record: Mapping[str, Any], now: datetime) -> str:
    t = get_translator(get_app_language())
    state = compute_activation_state(record, now)
    mode = str(record.get("activation_mode") or ACTIVATION_MODE_MANUAL).strip().lower()
    if mode == ACTIVATION_MODE_MANUAL:
        return t("Manual")
    if mode == ACTIVATION_MODE_SCHEDULED:
        if state.active_now:
            return t("Scheduled: active now")
        if state.next_activation_utc is not None:
            return t("Scheduled: starts {date} UTC").format(date=_format_utc(state.next_activation_utc))
        return t("Scheduled: inactive")
    if mode == ACTIVATION_MODE_RECURRING:
        interval_value = _positive_int(record.get("recurrence_interval_value")) or 0
        interval_unit = str(record.get("recurrence_interval_unit") or "").strip().lower()
        prefix = t("Every {value} {unit}").format(value=interval_value, unit=_recurrence_unit_label(interval_unit, t))
        if state.active_now:
            return t("{prefix}: active now").format(prefix=prefix)
        if state.next_activation_utc is not None:
            return t("{prefix}: next {date} UTC").format(prefix=prefix, date=_format_utc(state.next_activation_utc))
        return t("{prefix}: inactive").format(prefix=prefix)
    return t("Invalid schedule")


def schedule_warnings(record: Mapping[str, Any]) -> list[str]:
    t = get_translator(get_app_language())
    warnings: list[str] = []
    mode = str(record.get("activation_mode") or ACTIVATION_MODE_MANUAL).strip().lower()
    if mode == ACTIVATION_MODE_RECURRING:
        if not str(record.get("recurrence_until_utc") or "").strip():
            warnings.append(t("Recurring schedule has no end date."))
        duration = _positive_int(record.get("recurrence_duration_minutes"))
        if duration is not None and duration > 24 * 60:
            warnings.append(t("Record will be active for more than 24h per cycle."))
    path = str(record.get("path") or "").strip().upper()
    interval = _positive_int(record.get("interval_minutes"))
    if "WIDE2-2" in path and interval is not None and interval < 60:
        warnings.append(t("WIDE2-2 with interval below 60m is not recommended."))
    if path:
        warnings.append(t("Direct path is recommended for local/simple records."))
    return warnings


def _occurrence_index_at_or_before(
    first_activation: datetime,
    current: datetime,
    *,
    interval_value: int,
    interval_unit: str,
) -> int:
    if interval_unit in {"day", "week"}:
        interval_days = interval_value * (7 if interval_unit == "week" else 1)
        return max(0, int((current - first_activation) // timedelta(days=interval_days)))

    interval_months = interval_value * (12 if interval_unit == "year" else 1)
    elapsed_months = (current.year - first_activation.year) * 12 + current.month - first_activation.month
    candidate_index = max(0, elapsed_months // interval_months)
    while candidate_index > 0 and _occurrence_start(
        first_activation,
        candidate_index,
        interval_value=interval_value,
        interval_unit=interval_unit,
    ) > current:
        candidate_index -= 1
    while _occurrence_start(
        first_activation,
        candidate_index + 1,
        interval_value=interval_value,
        interval_unit=interval_unit,
    ) <= current:
        candidate_index += 1
    return candidate_index


def _occurrence_start(
    first_activation: datetime,
    occurrence_index: int,
    *,
    interval_value: int,
    interval_unit: str,
) -> datetime:
    if interval_unit == "day":
        return first_activation + timedelta(days=occurrence_index * interval_value)
    if interval_unit == "week":
        return first_activation + timedelta(weeks=occurrence_index * interval_value)
    months = occurrence_index * interval_value * (12 if interval_unit == "year" else 1)
    return _add_calendar_months(first_activation, months)


def _next_occurrence(
    first_activation: datetime,
    occurrence_index: int,
    *,
    interval_value: int,
    interval_unit: str,
    recurrence_until: datetime | None,
) -> datetime | None:
    candidate = _occurrence_start(
        first_activation,
        occurrence_index,
        interval_value=interval_value,
        interval_unit=interval_unit,
    )
    if recurrence_until is not None and candidate > recurrence_until:
        return None
    return candidate


def _add_calendar_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + (value.month - 1) + months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _normalize_optional_positive_int(value: Any, *, label: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = int(text)
    except ValueError as exc:
        raise ValueError(f"{label} must be a positive integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return parsed


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _is_enabled(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return _as_utc(value).strftime("%Y-%m-%d %H:%M")


def _duration_label(minutes: int, translate) -> str:
    if minutes > 0 and minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"


def _recurrence_unit_label(unit: str, translate) -> str:
    labels = {
        "day": translate("Day(s)"),
        "week": translate("Week(s)"),
        "month": translate("Month(s)"),
        "year": translate("Year(s)"),
    }
    return labels.get(unit, unit or "?")


def _field_label(field: str) -> str:
    return {
        "active_from_utc": "Active-from date",
        "active_until_utc": "Active-until date",
        "first_activation_utc": "First activation date",
        "recurrence_until_utc": "Repeat-until date",
    }[field]
