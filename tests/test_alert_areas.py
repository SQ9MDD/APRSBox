import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, init_db
from app.services.alert_areas import (
    build_alert_area_feature_collection,
    country_code_from_alarm_group,
    get_active_alert_area_feature_collection,
)
from app.services.map_service import get_map_station_markers_payload


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        try:
            init_db()
            yield database_path
        finally:
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


def _polygon(offset: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [offset, 50.0],
                [offset + 0.1, 50.0],
                [offset + 0.1, 50.1],
                [offset, 50.0],
            ]
        ],
    }


def _feature(code_property: str, code: str, offset: float) -> dict:
    return {
        "type": "Feature",
        "properties": {
            code_property: code,
            "display_name": f"Area {code}",
        },
        "geometry": _polygon(offset),
    }


def _write_geodata(
    root: Path,
    country: str,
    features: list[dict],
    *,
    filename: str = "arbitrary-name.geojson",
    metadata: dict | None = None,
) -> Path:
    country_directory = root / country
    country_directory.mkdir(parents=True, exist_ok=True)
    document = {
        "type": "FeatureCollection",
        "features": features,
    }
    if metadata:
        document.update(metadata)
    path = country_directory / filename
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _insert_alert(
    source_callsign: str,
    alarm_group: str,
    area_codes: list[str],
    *,
    is_active: bool = True,
    valid_until_utc: str | None = None,
) -> None:
    execute(
        """
        INSERT INTO aprs_alerts(
            source_callsign, alert_type, message,
            alarm_group, area_codes_json, is_active, valid_until_utc,
            first_seen_at, last_seen_at, frame_count,
            created_at, updated_at
        )
        VALUES (?, ?, '', ?, ?, ?, ?,
                '2026-01-01T00:00:00+00:00',
                '2026-01-01T00:00:00+00:00',
                1,
                '2026-01-01T00:00:00+00:00',
                '2026-01-01T00:00:00+00:00')
        """,
        (
            source_callsign,
            alarm_group,
            alarm_group,
            json.dumps(area_codes),
            1 if is_active else 0,
            valid_until_utc,
        ),
    )


class AlertAreaResolverTests(unittest.TestCase):
    def test_country_directory_is_derived_dynamically_from_warning_group(self) -> None:
        self.assertEqual(country_code_from_alarm_group("PL-WARN"), "pl")
        self.assertEqual(country_code_from_alarm_group("de-warn"), "de")
        self.assertEqual(country_code_from_alarm_group(" ES-WARN "), "es")
        self.assertIsNone(country_code_from_alarm_group("LOCALWARN"))
        self.assertIsNone(country_code_from_alarm_group("POL-WARN"))
        self.assertIsNone(country_code_from_alarm_group("PL-ALERT"))

        with tempfile.TemporaryDirectory() as temp_dir:
            geodata_root = Path(temp_dir)
            _write_geodata(
                geodata_root,
                "de",
                [_feature("region_code", "DE-091", 10.0)],
                filename="administrative-regions.geojson",
            )
            collection = build_alert_area_feature_collection(
                [{"alarm_group": "DE-WARN", "area_codes_json": '["DE-091"]'}],
                geodata_root=geodata_root,
            )

        self.assertEqual(len(collection["features"]), 1)
        self.assertEqual(
            collection["features"][0]["properties"]["aprsbox_country"],
            "de",
        )

    def test_unknown_country_missing_geojson_and_invalid_geojson_are_silent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            geodata_root = Path(temp_dir)
            (geodata_root / "de").mkdir()
            (geodata_root / "es").mkdir()
            (geodata_root / "es" / "broken.geojson").write_text("{", encoding="utf-8")

            collection = build_alert_area_feature_collection(
                [
                    {"alarm_group": "ZZ-WARN", "area_codes_json": '["001"]'},
                    {"alarm_group": "DE-WARN", "area_codes_json": '["001"]'},
                    {"alarm_group": "ES-WARN", "area_codes_json": '["001"]'},
                    {"alarm_group": "NOT-A-WARNING-GROUP", "area_codes_json": '["001"]'},
                ],
                geodata_root=geodata_root,
            )

        self.assertEqual(collection, {"type": "FeatureCollection", "features": []})

    def test_leading_zeroes_are_preserved_during_matching(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            geodata_root = Path(temp_dir)
            _write_geodata(
                geodata_root,
                "pl",
                [
                    _feature("administrative_identifier", "0012", 20.0),
                    _feature("administrative_identifier", "12", 21.0),
                ],
                metadata={"area_code_property": "administrative_identifier"},
            )
            collection = build_alert_area_feature_collection(
                [{"alarm_group": "PL-WARN", "area_codes_json": '["0012"]'}],
                geodata_root=geodata_root,
            )

        self.assertEqual(len(collection["features"]), 1)
        self.assertEqual(
            collection["features"][0]["properties"]["aprsbox_area_code"],
            "0012",
        )

    def test_multiple_countries_and_alerts_are_combined_without_duplicate_polygons(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            geodata_root = Path(temp_dir)
            pl_features = [
                _feature("code", "0001", 20.0),
                _feature("code", "0002", 21.0),
            ]
            _write_geodata(geodata_root, "pl", pl_features, filename="first.geojson")
            _write_geodata(
                geodata_root,
                "pl",
                [pl_features[0]],
                filename="duplicate-copy.geojson",
            )
            _write_geodata(
                geodata_root,
                "de",
                [_feature("GID", "DE-01", 10.0)],
            )

            collection = build_alert_area_feature_collection(
                [
                    {"alarm_group": "PL-WARN", "area_codes_json": '["0001"]'},
                    {"alarm_group": "PL-WARN", "area_codes_json": '["0001", "0002"]'},
                    {"alarm_group": "DE-WARN", "area_codes_json": '["DE-01"]'},
                ],
                geodata_root=geodata_root,
            )

        self.assertEqual(len(collection["features"]), 3)
        self.assertEqual(
            {
                (
                    feature["properties"]["aprsbox_country"],
                    feature["properties"]["aprsbox_area_code"],
                )
                for feature in collection["features"]
            },
            {("pl", "0001"), ("pl", "0002"), ("de", "DE-01")},
        )

    def test_inactive_expired_and_deleted_alerts_remove_their_areas(self) -> None:
        with temporary_database():
            with tempfile.TemporaryDirectory() as temp_dir:
                geodata_root = Path(temp_dir)
                _write_geodata(
                    geodata_root,
                    "pl",
                    [_feature("area_ref", "1465", 20.0)],
                )
                _insert_alert("PLWXSR", "PL-WARN", ["1465"])

                active = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T01:00:00+00:00",
                )
                self.assertEqual(len(active["features"]), 1)

                execute("UPDATE aprs_alerts SET is_active = 0 WHERE source_callsign = 'PLWXSR'")
                inactive = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T01:00:00+00:00",
                )
                self.assertEqual(inactive["features"], [])

                execute(
                    """
                    UPDATE aprs_alerts
                    SET is_active = 1,
                        valid_until_utc = '2026-01-01T00:30:00+00:00'
                    WHERE source_callsign = 'PLWXSR'
                    """
                )
                expired = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T01:00:00+00:00",
                )
                self.assertEqual(expired["features"], [])

                execute(
                    """
                    UPDATE aprs_alerts
                    SET valid_until_utc = '2026-01-01T02:00:00+00:00'
                    WHERE source_callsign = 'PLWXSR'
                    """
                )
                future = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T01:00:00+00:00",
                )
                self.assertEqual(len(future["features"]), 1)

                execute("DELETE FROM aprs_alerts WHERE source_callsign = 'PLWXSR'")
                deleted = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T01:00:00+00:00",
                )
                self.assertEqual(deleted["features"], [])

    def test_active_area_is_exposed_in_the_existing_map_refresh_payload(self) -> None:
        with temporary_database():
            _insert_alert("PLWXSR", "PL-WARN", ["1465"])

            payload = get_map_station_markers_payload()

        self.assertEqual(payload["alert_areas"]["type"], "FeatureCollection")
        self.assertEqual(len(payload["alert_areas"]["features"]), 1)
        self.assertEqual(
            payload["alert_areas"]["features"][0]["properties"]["aprsbox_area_code"],
            "1465",
        )

    def test_map_script_uses_a_noninteractive_layer_between_tiles_and_markers(self) -> None:
        source = Path("app/static/js/map.js").read_text(encoding="utf-8")

        self.assertIn('const alertAreasPaneName = "alert-areas-pane";', source)
        self.assertIn('alertAreasPane.style.zIndex = "350";', source)
        self.assertIn("alertAreasPane.style.pointerEvents = \"none\";", source)
        self.assertIn("alertAreaLayer.clearLayers();", source)
        self.assertIn("alertAreaLayer.addData(featureCollection);", source)
        self.assertIn('color: "red"', source)
        self.assertIn('fillColor: "red"', source)
        self.assertIn("fillOpacity: 0.10", source)
        self.assertIn("dashArray: null", source)
        self.assertIn("reconcileAlertAreas(payload.alert_areas);", source)


if __name__ == "__main__":
    unittest.main()
