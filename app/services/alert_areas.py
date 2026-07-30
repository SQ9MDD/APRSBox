from __future__ import annotations

import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from app.db import fetch_all, utc_now
from app.services.alerts import normalize_alert_area_codes


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
    return normalize_alert_area_codes(value)


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
    requested_codes: set[str],
) -> list[dict[str, Any]]:
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
        properties.update(
            {
                "aprsbox_country": country_code,
                "aprsbox_area_code": str(identifier).strip(),
            }
        )
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
    codes_by_country: dict[str, set[str]] = {}
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
        if normalized_codes:
            codes_by_country.setdefault(country_code, set()).update(normalized_codes)

    output_features: list[dict[str, Any]] = []
    seen_geometries: set[str] = set()
    for country_code in sorted(codes_by_country):
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
                requested_codes=codes_by_country[country_code],
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
                if deduplication_key in seen_geometries:
                    continue
                seen_geometries.add(deduplication_key)
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
    timestamp = str(now or utc_now())
    try:
        rows = fetch_all(
            """
            SELECT id, alarm_group, area_codes_json
            FROM aprs_alerts
            WHERE is_active = 1
              AND (
                    valid_until_utc IS NULL
                    OR julianday(valid_until_utc) > julianday(?)
              )
            ORDER BY id ASC
            """,
            (timestamp,),
        )
    except sqlite3.OperationalError:
        return {"type": "FeatureCollection", "features": []}
    return build_alert_area_feature_collection(
        [dict(row) for row in rows],
        geodata_root=geodata_root,
    )
