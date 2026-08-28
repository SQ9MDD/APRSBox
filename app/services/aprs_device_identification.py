from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app import get_version
from app.config import settings
from app.db import get_app_setting, log_event, set_app_setting, utc_now


UPDATE_ATTEMPT_AT_KEY = "aprs_device_identification_last_attempt_at"
UPDATE_SUCCESS_AT_KEY = "aprs_device_identification_last_success_at"
UPDATE_ERROR_KEY = "aprs_device_identification_last_error"
UPDATE_GENERATION_TIME_KEY = "aprs_device_identification_last_generation_time"
AUTO_UPDATE_MAX_AGE = timedelta(days=30)
AUTO_UPDATE_RETRY_DELAY = timedelta(hours=24)

CLASS_FALLBACKS = {
    "app": ("Mobile app", "Mobile phone or tablet APRS app"),
    "daemon": ("Background software", "Computer software without a user interface"),
    "digi": ("Digipeater", "Digipeater software"),
    "dstar": ("D-Star APRS client", "D-Star APRS client"),
    "gadget": ("APRS device", "Small APRS device"),
    "ht": ("Handheld APRS client", "Handheld APRS client"),
    "igate": ("iGate", "iGate software"),
    "network": ("APRS network appliance", "Hardware appliance with built-in APRS networking features"),
    "rig": ("Mobile/desktop APRS client", "Mobile or desktop APRS client"),
    "satellite": ("Satellite", "Satellite-based APRS station"),
    "service": ("Service", "Service, bot, or hosted APRS software"),
    "software": ("Desktop software", "Desktop APRS software"),
    "tracker": ("Tracker", "Tracker device"),
    "wx": ("Weather station", "Dedicated APRS weather station"),
}

_DB_CACHE: dict[str, Any] = {}
_DB_CACHE_LOCK = threading.Lock()
_UPDATE_LOCK = threading.Lock()
_CACHE_MISSING = object()


@dataclass(slots=True)
class DeviceIdentificationDatabase:
    source_key: str
    source_label: str
    source_path: Path
    generation_time: str | None
    tocalls: dict[str, dict[str, Any]]
    wildcard_tocalls: list[tuple[str, dict[str, Any]]]
    mice: dict[str, dict[str, Any]]
    micelegacy: dict[str, dict[str, Any]]
    classes: dict[str, dict[str, Any]]


def get_aprs_device_identification_database() -> DeviceIdentificationDatabase | None:
    cached = _DB_CACHE.get("db", _CACHE_MISSING)
    if cached is not _CACHE_MISSING:
        return cached

    with _DB_CACHE_LOCK:
        cached = _DB_CACHE.get("db", _CACHE_MISSING)
        if cached is not _CACHE_MISSING:
            return cached
        loaded = _load_active_database()
        _DB_CACHE["db"] = loaded
        return loaded


def lookup_aprs_device_identification(
    *,
    destination: str,
    info: str,
    database: DeviceIdentificationDatabase | None = None,
) -> dict[str, Any] | None:
    db = database or get_aprs_device_identification_database()
    if db is None:
        return None

    normalized_destination = _normalize_destination(destination)
    if normalized_destination:
        matched_pattern, entry = _lookup_tocall_entry(db, normalized_destination)
        if entry is not None:
            return _build_lookup_result(
                db,
                entry,
                actual_identifier=normalized_destination,
                matched_pattern=matched_pattern,
                identifier_kind="tocall",
            )

    mic_e_result = _lookup_mic_e_entry(db, info)
    if mic_e_result is None:
        return None
    matched_pattern, actual_identifier, entry = mic_e_result
    return _build_lookup_result(
        db,
        entry,
        actual_identifier=actual_identifier,
        matched_pattern=matched_pattern,
        identifier_kind="mic-e",
    )


def get_aprs_device_identification_status() -> dict[str, Any]:
    db = get_aprs_device_identification_database()
    cache_path = settings.aprs_device_identification_cache_path
    cache_exists = cache_path.exists()
    cache_updated_at = _format_file_timestamp(cache_path) if cache_exists else None

    status_label = "Unavailable"
    source_label = "Unavailable"
    if db is not None:
        source_label = db.source_label
        if db.source_key == "cache":
            status_label = "Local cache active"
        elif cache_exists:
            status_label = "Bundled snapshot fallback"
        else:
            status_label = "Bundled snapshot active"

    return {
        "available": db is not None,
        "status_label": status_label,
        "active_source_label": source_label,
        "generation_time": (db.generation_time if db is not None else None) or get_app_setting(UPDATE_GENERATION_TIME_KEY),
        "cache_exists": cache_exists,
        "cache_updated_at": cache_updated_at,
        "bundle_path": str(settings.aprs_device_identification_bundle_path),
        "cache_path": str(cache_path),
        "update_url": settings.aprs_device_identification_update_url,
        "last_attempt_at": get_app_setting(UPDATE_ATTEMPT_AT_KEY),
        "last_success_at": get_app_setting(UPDATE_SUCCESS_AT_KEY),
        "last_error": get_app_setting(UPDATE_ERROR_KEY),
        "auto_update_due": is_aprs_device_identification_auto_update_due(),
    }


def is_aprs_device_identification_auto_update_due(*, now: datetime | None = None) -> bool:
    reference = _normalize_utc_datetime(now or datetime.now(timezone.utc))
    last_success = _parse_update_timestamp(get_app_setting(UPDATE_SUCCESS_AT_KEY))
    if last_success is not None and reference - last_success < AUTO_UPDATE_MAX_AGE:
        return False

    last_attempt = _parse_update_timestamp(get_app_setting(UPDATE_ATTEMPT_AT_KEY))
    if last_attempt is not None and reference - last_attempt < AUTO_UPDATE_RETRY_DELAY:
        return False
    return True


def refresh_aprs_device_identification_cache() -> dict[str, Any]:
    if not _UPDATE_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "APRS device identification database update is already in progress.", "in_progress": True}

    cache_path = settings.aprs_device_identification_cache_path
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path: Path | None = None
        attempt_at = utc_now()
        try:
            request = Request(
                settings.aprs_device_identification_update_url,
                headers={"User-Agent": f"APRSBox/{get_version()}"},
            )
            with urlopen(request, timeout=20) as response, NamedTemporaryFile(
                mode="wb",
                prefix=".aprs-deviceid-",
                suffix=".json",
                dir=cache_path.parent,
                delete=False,
            ) as temp_file:
                temp_file.write(response.read())
                temp_path = Path(temp_file.name)

            loaded = _load_database_from_path(temp_path, source_key="cache", source_label="Local cache")
            os.replace(temp_path, cache_path)
            loaded.source_path = cache_path
            with _DB_CACHE_LOCK:
                _DB_CACHE["db"] = loaded

            set_app_setting(UPDATE_ATTEMPT_AT_KEY, attempt_at)
            set_app_setting(UPDATE_SUCCESS_AT_KEY, attempt_at)
            set_app_setting(UPDATE_ERROR_KEY, "")
            set_app_setting(UPDATE_GENERATION_TIME_KEY, loaded.generation_time or "")
            log_event("INFO", "aprs_device_identification", f"Updated APRS device identification cache from {settings.aprs_device_identification_update_url}")
            return {
                "ok": True,
                "generation_time": loaded.generation_time,
                "cache_path": str(cache_path),
            }
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            set_app_setting(UPDATE_ATTEMPT_AT_KEY, attempt_at)
            set_app_setting(UPDATE_ERROR_KEY, str(exc))
            log_event("WARNING", "aprs_device_identification", f"Failed to update APRS device identification cache: {exc}")
            return {"ok": False, "error": str(exc)}
    finally:
        _UPDATE_LOCK.release()


def _parse_update_timestamp(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _normalize_utc_datetime(parsed)


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _load_active_database() -> DeviceIdentificationDatabase | None:
    cache_path = settings.aprs_device_identification_cache_path
    if cache_path.exists():
        try:
            return _load_database_from_path(cache_path, source_key="cache", source_label="Local cache")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            log_event("WARNING", "aprs_device_identification", f"Ignoring invalid APRS device identification cache {cache_path}: {exc}")

    bundle_path = settings.aprs_device_identification_bundle_path
    if not bundle_path.exists():
        return None
    try:
        return _load_database_from_path(bundle_path, source_key="bundle", source_label="Bundled snapshot")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        log_event("ERROR", "aprs_device_identification", f"Failed to load bundled APRS device identification snapshot {bundle_path}: {exc}")
        return None


def _load_database_from_path(path: Path, *, source_key: str, source_label: str) -> DeviceIdentificationDatabase:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _parse_database_payload(payload, source_key=source_key, source_label=source_label, source_path=path)


def _parse_database_payload(
    payload: dict[str, Any],
    *,
    source_key: str,
    source_label: str,
    source_path: Path,
) -> DeviceIdentificationDatabase:
    if not isinstance(payload, dict):
        raise ValueError("Device identification database root must be a JSON object.")

    tocalls = payload.get("tocalls")
    if not isinstance(tocalls, dict):
        raise ValueError("Device identification database has no TOCALL entries.")

    mice = payload.get("mice") or {}
    micelegacy = payload.get("micelegacy") or {}
    classes = payload.get("classes") or {}
    meta = payload.get("meta") or {}
    if not isinstance(mice, dict) or not isinstance(micelegacy, dict) or not isinstance(classes, dict):
        raise ValueError("Device identification database has invalid section types.")

    exact_tocalls: dict[str, dict[str, Any]] = {}
    wildcard_tocalls: list[tuple[str, dict[str, Any]]] = []
    for raw_pattern, raw_entry in tocalls.items():
        pattern = str(raw_pattern or "").strip().upper()
        if not pattern or not isinstance(raw_entry, dict):
            continue
        entry = {str(key): value for key, value in raw_entry.items()}
        if "?" in pattern:
            wildcard_tocalls.append((pattern, entry))
        else:
            exact_tocalls[pattern] = entry

    wildcard_tocalls.sort(key=lambda item: (item[0].count("?"), item[0]))

    return DeviceIdentificationDatabase(
        source_key=source_key,
        source_label=source_label,
        source_path=source_path,
        generation_time=str(meta.get("generation_time") or "").strip() or None,
        tocalls=exact_tocalls,
        wildcard_tocalls=wildcard_tocalls,
        mice={str(key): dict(value) for key, value in mice.items() if isinstance(value, dict)},
        micelegacy={str(key): dict(value) for key, value in micelegacy.items() if isinstance(value, dict)},
        classes={str(key): dict(value) for key, value in classes.items() if isinstance(value, dict)},
    )


def _normalize_destination(destination: str) -> str:
    value = str(destination or "").strip().upper()
    base, separator, suffix = value.partition("-")
    if separator and suffix.isdigit():
        value = base
    return value


def _lookup_tocall_entry(db: DeviceIdentificationDatabase, destination: str) -> tuple[str, dict[str, Any] | None]:
    entry = db.tocalls.get(destination)
    if entry is not None:
        return destination, entry
    for pattern, wildcard_entry in db.wildcard_tocalls:
        if _pattern_matches(pattern, destination):
            return pattern, wildcard_entry
    return destination, None


def _lookup_mic_e_entry(db: DeviceIdentificationDatabase, info: str) -> tuple[str, str, dict[str, Any]] | None:
    raw_info = str(info or "")
    if not raw_info or raw_info[0] not in {"`", "'"} or len(raw_info) < 10:
        return None

    text = raw_info[9:].rstrip()
    if not text:
        return None

    prefix = text[0]
    suffix = text[-1] if len(text) > 1 else ""
    if prefix in {">", "]"}:
        exact_key = f"{prefix}{suffix}"
        if exact_key in db.micelegacy:
            return exact_key, exact_key, db.micelegacy[exact_key]
        if prefix in db.micelegacy:
            return prefix, prefix, db.micelegacy[prefix]

    if len(text) >= 2:
        manufacturer_version = text[-2:]
        entry = db.mice.get(manufacturer_version)
        if entry is not None:
            return manufacturer_version, manufacturer_version, entry
    return None


def _pattern_matches(pattern: str, value: str) -> bool:
    if len(pattern) != len(value):
        return False
    return all(left == "?" or left == right for left, right in zip(pattern, value))


def _build_lookup_result(
    db: DeviceIdentificationDatabase,
    entry: dict[str, Any],
    *,
    actual_identifier: str,
    matched_pattern: str,
    identifier_kind: str,
) -> dict[str, Any]:
    vendor = _clean_text(entry.get("vendor"))
    model = _clean_text(entry.get("model"))
    os_name = _clean_text(entry.get("os"))
    contact = _clean_text(entry.get("contact"))
    class_code = _clean_text(entry.get("class")).casefold()
    features = [str(item).strip() for item in entry.get("features") or [] if str(item).strip()]

    class_meta = db.classes.get(class_code) or {}
    class_label, class_description = _resolve_class_labels(class_code, class_meta)
    identified_as = model or vendor or matched_pattern or actual_identifier
    short_name = model or vendor or actual_identifier

    return {
        "identifier_kind": identifier_kind,
        "actual_identifier": actual_identifier,
        "matched_pattern": matched_pattern,
        "identified_as": identified_as,
        "short_name": short_name,
        "vendor": vendor,
        "model": model,
        "class_code": class_code,
        "class_label": class_label,
        "class_description": class_description,
        "os": os_name,
        "contact": contact,
        "features": features,
        "message_capable": "messaging" in {feature.casefold() for feature in features},
    }


def _resolve_class_labels(class_code: str, class_meta: dict[str, Any]) -> tuple[str | None, str | None]:
    fallback_label, fallback_description = CLASS_FALLBACKS.get(class_code, (None, None))
    shown = fallback_label or _clean_text(class_meta.get("shown"))
    description = fallback_description or _clean_text(class_meta.get("description"))
    return shown, description


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _format_file_timestamp(path: Path) -> str | None:
    try:
        timestamp = path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()
