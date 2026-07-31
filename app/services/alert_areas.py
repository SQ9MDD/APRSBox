from __future__ import annotations

import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from app.db import fetch_all, utc_now
from app.services.alarm_groups import get_aprs_alarm_enabled
from app.services.alert_event_icons import resolve_alert_event_icon
from app.services.alerts import expire_aprs_alerts
from app.services.aprs_warning_identity import normalize_warning_area_codes


GEODATA_ROOT = Path(__file__).resolve().parents[1] / "static" / "geodata"
_COUNTRY_WARNING_GROUP_RE = re.compile(r"^(?P<country>[A-Z]{2})-WARN$", re.IGNORECASE | re.ASCII)
_FEATURE_ID_SENTINEL = "\0feature-id"
_EXPLICIT_IDENTIFIER_KEYS = (
    "area_code_property",
    "areaCodeProperty",
    "id_property",
    "idProperty",
    "identifier_property",
    "identifierProperty",
)
ALERT_SEVERITY_COLORS = {
    1: "yellow",
    2: "orange",
    3: "red",
}
UNKNOWN_ALERT_SEVERITY_COLOR = "gray"


def country_code_from_alarm_group(alarm_group: Any) -> str | None:
    match = _COUNTRY_WARNING_GROUP_RE.fullmatch(str(alarm_group or "").strip())
    if match is None:
        return None
    return match.group("country").lower()


def _normalize_identifier(value: Any) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    return str(value).strip().casefold()


def _decode_area_codes(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    return normalize_warning_area_codes(value)


def _alert_severity_level(value: Any) -> int | None:
    try:
        severity_level = int(value)
    except (TypeError, ValueError):
        return None
    return severity_level if severity_level in ALERT_SEVERITY_COLORS else None


def _is_position(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 2
        and all(
            isinstance(coordinate, (int, float)) and not isinstance(coordinate, bool)
            for coordinate in value[:2]
        )
    )


def _is_linear_ring(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 4
        and all(_is_position(position) for position in value)
    )


def _is_polygon_coordinates(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_is_linear_ring(ring) for ring in value)


def _is_area_geometry(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    geometry_type = value.get("type")
    coordinates = value.get("coordinates")
    if geometry_type == "Polygon":
        return _is_polygon_coordinates(coordinates)
    if geometry_type == "MultiPolygon":
        return (
            isinstance(coordinates, list)
            and bool(coordinates)
            and all(_is_polygon_coordinates(polygon) for polygon in coordinates)
        )
    return False


@lru_cache(maxsize=32)
def _load_geojson_cached(
    path_text: str,
    modified_ns: int,
    size_bytes: int,
) -> Mapping[str, Any] | None:
    del modified_ns, size_bytes
    try:
        document = json.loads(Path(path_text).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        return None
    if not isinstance(document.get("features"), list):
        return None
    return document


def _load_geojson(path: Path) -> Mapping[str, Any] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return _load_geojson_cached(str(path), stat.st_mtime_ns, stat.st_size)


def _explicit_identifier_property(document: Mapping[str, Any]) -> str | None:
    containers = [document]
    metadata = document.get("metadata")
    if isinstance(metadata, dict):
        containers.append(metadata)
    for container in containers:
        for key in _EXPLICIT_IDENTIFIER_KEYS:
            value = str(container.get(key) or "").strip()
            if value:
                return value
    return None


def _feature_identifier(feature: Mapping[str, Any], property_name: str) -> Any:
    if property_name == _FEATURE_ID_SENTINEL:
        return feature.get("id")
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        return None
    return properties.get(property_name)


def _identifier_name_score(property_name: str) -> int:
    normalized = re.sub(r"[^a-z0-9]+", "_", property_name.casefold()).strip("_")
    if normalized in {"id", "code", "area_id", "area_code", "region_id", "region_code"}:
        return 4
    tokens = {token for token in normalized.split("_") if token}
    if tokens.intersection({"code", "kod", "identifier"}):
        return 3
    if "id" in tokens or normalized.endswith("id"):
        return 2
    return 1


def _select_identifier_property(
    document: Mapping[str, Any],
    features: list[Mapping[str, Any]],
    requested_codes: set[str],
) -> str | None:
    explicit = _explicit_identifier_property(document)
    if explicit:
        return explicit

    candidate_names: set[str] = set()
    if any(_normalize_identifier(feature.get("id")) in requested_codes for feature in features):
        candidate_names.add(_FEATURE_ID_SENTINEL)
    for feature in features:
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            continue
        for property_name, value in properties.items():
            if _normalize_identifier(value) in requested_codes:
                candidate_names.add(str(property_name))
    if not candidate_names:
        return None

    def score(property_name: str) -> tuple[int, int, str]:
        matched_codes = {
            _normalize_identifier(_feature_identifier(feature, property_name))
            for feature in features
        }.intersection(requested_codes)
        name_score = 5 if property_name == _FEATURE_ID_SENTINEL else _identifier_name_score(property_name)
        return len(matched_codes), name_score, property_name.casefold()

    return max(candidate_names, key=score)


def _matching_features(
    document: Mapping[str, Any],
    *,
    country_code: str,
    severity_by_code: Mapping[str, int],
    alerts_by_code: Mapping[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    requested_codes = set(severity_by_code)
    features = [
        feature
        for feature in document.get("features", [])
        if isinstance(feature, dict)
        and feature.get("type") == "Feature"
        and _is_area_geometry(feature.get("geometry"))
    ]
    identifier_property = _select_identifier_property(document, features, requested_codes)
    if identifier_property is None:
        return []

    matched: list[dict[str, Any]] = []
    for feature in features:
        identifier = _feature_identifier(feature, identifier_property)
        normalized_identifier = _normalize_identifier(identifier)
        if normalized_identifier not in requested_codes:
            continue
        properties = dict(feature.get("properties") or {})
        severity_level = severity_by_code.get(normalized_identifier, 0)
        properties.update(
            {
                "aprsbox_country": country_code,
                "aprsbox_area_code": str(identifier).strip(),
                "aprsbox_severity_level": severity_level or None,
                "aprsbox_alert_color": ALERT_SEVERITY_COLORS.get(
                    severity_level,
                    UNKNOWN_ALERT_SEVERITY_COLOR,
                ),
            }
        )
        contributing_alerts = list(
            (alerts_by_code or {}).get(normalized_identifier, [])
        )
        if contributing_alerts:
            properties["aprsbox_alerts"] = contributing_alerts
        matched.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": feature["geometry"],
            }
        )
    return matched


def build_alert_area_feature_collection(
    alerts: list[Mapping[str, Any]],
    *,
    geodata_root: Path | None = None,
) -> dict[str, Any]:
    root = Path(geodata_root) if geodata_root is not None else GEODATA_ROOT
    severity_by_country_code: dict[str, dict[str, int]] = {}
    alerts_by_country_code: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for alert in alerts:
        country_code = country_code_from_alarm_group(alert.get("alarm_group"))
        if country_code is None:
            continue
        raw_area_codes = (
            alert.get("area_codes_json")
            if "area_codes_json" in alert
            else alert.get("area_codes")
        )
        normalized_codes = {
            _normalize_identifier(code)
            for code in _decode_area_codes(raw_area_codes)
            if _normalize_identifier(code)
        }
        severity_level = _alert_severity_level(alert.get("severity_level")) or 0
        country_severities = severity_by_country_code.setdefault(country_code, {})
        country_alerts = alerts_by_country_code.setdefault(country_code, {})
        try:
            alert_id = int(alert.get("id"))
        except (TypeError, ValueError):
            alert_id = None
        for normalized_code in normalized_codes:
            country_severities[normalized_code] = max(
                country_severities.get(normalized_code, 0),
                severity_level,
            )
            if alert_id is not None:
                contributors = country_alerts.setdefault(normalized_code, [])
                if not any(item["id"] == alert_id for item in contributors):
                    contributors.append(
                        {
                            "id": alert_id,
                            "severity_level": severity_level or None,
                        }
                    )

    output_features: list[dict[str, Any]] = []
    feature_indexes_by_geometry: dict[str, int] = {}
    for country_code in sorted(severity_by_country_code):
        country_directory = root / country_code
        if not country_directory.is_dir():
            continue
        try:
            geojson_paths = sorted(
                path
                for path in country_directory.glob("*.geojson")
                if path.is_file()
            )
        except OSError:
            continue
        for geojson_path in geojson_paths:
            document = _load_geojson(geojson_path)
            if document is None:
                continue
            for feature in _matching_features(
                document,
                country_code=country_code,
                severity_by_code=severity_by_country_code[country_code],
                alerts_by_code=alerts_by_country_code.get(country_code),
            ):
                try:
                    geometry_key = json.dumps(
                        feature["geometry"],
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                except (TypeError, ValueError):
                    continue
                deduplication_key = f"{country_code}:{geometry_key}"
                existing_index = feature_indexes_by_geometry.get(deduplication_key)
                if existing_index is not None:
                    existing_feature = output_features[existing_index]
                    existing_properties = existing_feature["properties"]
                    existing_severity = int(
                        existing_properties.get(
                            "aprsbox_severity_level"
                        )
                        or 0
                    )
                    candidate_severity = int(
                        feature["properties"].get("aprsbox_severity_level") or 0
                    )
                    if candidate_severity > existing_severity:
                        existing_properties["aprsbox_severity_level"] = (
                            feature["properties"].get("aprsbox_severity_level")
                        )
                        existing_properties["aprsbox_alert_color"] = feature[
                            "properties"
                        ].get("aprsbox_alert_color")
                    candidate_contributors = feature["properties"].get(
                        "aprsbox_alerts",
                        [],
                    )
                    existing_contributors = existing_properties.get(
                        "aprsbox_alerts",
                        [],
                    )
                    if not existing_contributors and not candidate_contributors:
                        continue
                    existing_properties["aprsbox_alerts"] = existing_contributors
                    existing_ids = {
                        int(item["id"])
                        for item in existing_contributors
                        if isinstance(item, dict) and item.get("id") is not None
                    }
                    for contributor in candidate_contributors:
                        if int(contributor["id"]) not in existing_ids:
                            existing_contributors.append(contributor)
                            existing_ids.add(int(contributor["id"]))
                    continue
                feature_indexes_by_geometry[deduplication_key] = len(output_features)
                output_features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": output_features,
    }


def get_active_alert_area_feature_collection(
    *,
    geodata_root: Path | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    if not get_aprs_alarm_enabled():
        return {"type": "FeatureCollection", "features": []}
    timestamp = str(now or utc_now())
    try:
        expire_aprs_alerts(now=timestamp)
        rows = fetch_all(
            """
            SELECT
                id,
                source_callsign,
                alert_type,
                alarm_group,
                area_codes_json,
                event_code,
                severity_level,
                expires_at,
                valid_until_utc,
                last_seen_at
            FROM aprs_alerts
            WHERE is_active = 1
              AND alarm_group IS NOT NULL
              AND TRIM(alarm_group) != ''
              AND superseded_by_alert_id IS NULL
              AND (
                    expires_at IS NULL
                    OR julianday(expires_at) > julianday(?)
              )
              AND (
                    valid_until_utc IS NULL
                    OR julianday(valid_until_utc) > julianday(?)
              )
            ORDER BY last_seen_at DESC, id DESC
            """,
            (timestamp, timestamp),
        )
    except sqlite3.OperationalError:
        return {"type": "FeatureCollection", "features": []}
    alerts = [dict(row) for row in rows]
    collection = build_alert_area_feature_collection(
        alerts,
        geodata_root=geodata_root,
    )
    alert_ids_with_geometry = {
        int(contributor["id"])
        for feature in collection["features"]
        for contributor in feature.get("properties", {}).get("aprsbox_alerts", [])
        if isinstance(contributor, dict) and contributor.get("id") is not None
    }
    collection["alerts"] = [
        {
            "id": int(alert["id"]),
            "source_callsign": str(
                alert.get("source_callsign") or ""
            ).strip().upper(),
            "alarm_group": str(alert.get("alarm_group") or "").strip().upper(),
            "event_code": str(
                alert.get("event_code") or alert.get("alert_type") or ""
            ).strip().upper(),
            "event_icon": resolve_alert_event_icon(
                alert.get("event_code"),
                alert_type=alert.get("alert_type"),
            ),
            "severity_level": _alert_severity_level(alert.get("severity_level")),
            "area_count": len(_decode_area_codes(alert.get("area_codes_json"))),
            "expires_at": str(
                alert.get("expires_at") or alert.get("valid_until_utc") or ""
            ),
            "detail_href": f"/alerts/{int(alert['id'])}",
            "has_geometry": int(alert["id"]) in alert_ids_with_geometry,
        }
        for alert in alerts
    ]
    return collection
