import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, fetch_all, init_db
from app.services.alarm_groups import (
    get_aprs_alarm_category_thresholds,
    save_aprs_alarm_enabled,
    save_aprs_alarm_category_thresholds,
    save_aprs_alarm_groups,
    save_map_alarm_level_threshold,
)
from app.services.alerts import delete_alert
from app.services.alert_areas import (
    build_alert_area_feature_collection,
    country_code_from_alarm_group,
    get_active_alert_area_feature_collection,
)
from app.services.aprs_warning_identity import build_aprs_alert_identity_key
from app.services.map_service import (
    get_map_alert_areas_payload,
    get_map_station_markers_payload,
)
from app.services.traffic import process_normalized_tnc2_rx


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        try:
            init_db()
            save_aprs_alarm_enabled(True)
            save_aprs_alarm_groups("PL-WARN")
            thresholds = get_aprs_alarm_category_thresholds()
            for values in thresholds.values():
                values["alerts"] = 1
            save_aprs_alarm_category_thresholds(thresholds)
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
    alarm_group: str | None,
    area_codes: list[str],
    *,
    is_active: bool = True,
    valid_until_utc: str | None = None,
    expires_at: str | None = None,
    severity_level: int | None = None,
    event_code: str = "TSTORM1",
) -> None:
    execute(
        """
        INSERT INTO aprs_alerts(
            identity_key, source_callsign, alert_type, message,
            alarm_group, area_codes_json, event_code, severity_level,
            is_active, valid_until_utc, expires_at,
            first_seen_at, last_seen_at, frame_count,
            created_at, updated_at
        )
        VALUES (?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?,
                '2026-01-01T00:00:00+00:00',
                '2026-01-01T00:00:00+00:00',
                1,
                '2026-01-01T00:00:00+00:00',
                '2026-01-01T00:00:00+00:00')
        """,
        (
            build_aprs_alert_identity_key(
                source_callsign=source_callsign,
                alarm_group=alarm_group,
                message_id=f"test-{source_callsign}",
            ),
            source_callsign,
            alarm_group or "EMERGENCY",
            alarm_group,
            json.dumps(area_codes),
            event_code,
            severity_level,
            1 if is_active else 0,
            valid_until_utc,
            expires_at,
        ),
    )


def _receive_group_alert(area_code: str, message_id: str) -> None:
    accepted = process_normalized_tnc2_rx(
        f"PLWXSR>APRS,TCPIP*::PL-WARN  :310100z,TSTORM1,{area_code}{{{message_id}",
        source="APRS-IS · Internet RX",
        source_kind="aprsis",
        timestamp=f"2026-01-30T00:10:{len(message_id):02d}+00:00",
    )
    if not accepted:
        raise AssertionError("Alarm-group frame was rejected")


def _receive_multipart_group_alert(
    *,
    part_number: int,
    parts_total: int,
    area_codes: tuple[str, ...],
    message_id: str,
) -> None:
    content = ",".join(
        (
            "302200z",
            "TSTORM2",
            "@A7F3",
            f"{part_number}/{parts_total}",
            *area_codes,
        )
    )
    accepted = process_normalized_tnc2_rx(
        f"PLWXSR>APRS,TCPIP*::PL-WARN  :{content}{{{message_id}",
        source="APRS-IS · Internet RX",
        source_kind="aprsis",
        timestamp=f"2026-01-30T20:20:0{part_number}+00:00",
    )
    if not accepted:
        raise AssertionError("Multipart alarm-group frame was rejected")


class AlertAreaResolverTests(unittest.TestCase):
    def test_global_alarm_disable_hides_existing_group_alert_areas(self) -> None:
        with temporary_database():
            _insert_alert("PLWX01", "PL-WARN", ["1465"], severity_level=3)
            save_aprs_alarm_enabled(False)

            collection = get_active_alert_area_feature_collection(
                now="2026-01-01T01:00:00+00:00"
            )

        self.assertEqual(collection, {"type": "FeatureCollection", "features": []})

    def test_emergency_frames_are_not_added_to_the_map_alarm_panel(self) -> None:
        with temporary_database():
            _insert_alert("PLWX01", "PL-WARN", ["1465"], severity_level=3)
            _insert_alert("EMERG1", None, [], severity_level=3, event_code="")

            collection = get_active_alert_area_feature_collection(
                now="2026-01-01T01:00:00+00:00"
            )

        self.assertEqual(
            [alert["source_callsign"] for alert in collection["alerts"]],
            ["PLWX01"],
        )

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

    def test_polygon_colors_follow_severity_levels_and_unknown_is_gray(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            geodata_root = Path(temp_dir)
            _write_geodata(
                geodata_root,
                "pl",
                [_feature("area_code", "1465", 20.0)],
            )
            observed_colors = {}
            for severity_level in (1, 2, 3, None, 9):
                collection = build_alert_area_feature_collection(
                    [
                        {
                            "alarm_group": "PL-WARN",
                            "area_codes": ["1465"],
                            "severity_level": severity_level,
                        }
                    ],
                    geodata_root=geodata_root,
                )
                observed_colors[severity_level] = collection["features"][0][
                    "properties"
                ]["aprsbox_alert_color"]

        self.assertEqual(
            observed_colors,
            {
                1: "yellow",
                2: "orange",
                3: "red",
                None: "gray",
                9: "gray",
            },
        )

    def test_legacy_map_threshold_does_not_hide_active_alerts_from_map_panel(self) -> None:
        with temporary_database():
            save_map_alarm_level_threshold(2)
            with tempfile.TemporaryDirectory() as temp_dir:
                geodata_root = Path(temp_dir)
                _write_geodata(
                    geodata_root,
                    "pl",
                    [
                        _feature("area_code", "L1", 20.0),
                        _feature("area_code", "L2", 21.0),
                        _feature("area_code", "L3", 22.0),
                        _feature("area_code", "UNK", 23.0),
                    ],
                )
                _insert_alert("PLWX01", "PL-WARN", ["L1"], severity_level=1)
                _insert_alert("PLWX02", "PL-WARN", ["L2"], severity_level=2)
                _insert_alert("PLWX03", "PL-WARN", ["L3"], severity_level=3)
                _insert_alert("PLWX04", "PL-WARN", ["UNK"], severity_level=None)

                collection = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T01:00:00+00:00",
                )

        self.assertEqual(
            {
                feature["properties"]["aprsbox_area_code"]
                for feature in collection["features"]
            },
            {"L1", "L2", "L3", "UNK"},
        )
        self.assertEqual(
            {alert["source_callsign"] for alert in collection["alerts"]},
            {"PLWX01", "PLWX02", "PLWX03", "PLWX04"},
        )

    def test_legacy_category_map_thresholds_do_not_filter_map_panel(self) -> None:
        with temporary_database():
            thresholds = get_aprs_alarm_category_thresholds()
            thresholds["HEAT"]["map"] = 3
            thresholds["THUNDERSTORM"]["map"] = 1
            thresholds["HAIL"]["map"] = "off"
            save_aprs_alarm_category_thresholds(thresholds)
            with tempfile.TemporaryDirectory() as temp_dir:
                geodata_root = Path(temp_dir)
                _write_geodata(
                    geodata_root,
                    "pl",
                    [
                        _feature("area_code", "HEAT2", 20.0),
                        _feature("area_code", "HEAT3", 21.0),
                        _feature("area_code", "STORM1", 22.0),
                        _feature("area_code", "HAIL3", 23.0),
                    ],
                )
                _insert_alert(
                    "PLWX01",
                    "PL-WARN",
                    ["HEAT2"],
                    severity_level=2,
                    event_code="HEAT2",
                )
                _insert_alert(
                    "PLWX02",
                    "PL-WARN",
                    ["HEAT3"],
                    severity_level=3,
                    event_code="HEAT3",
                )
                _insert_alert(
                    "PLWX03",
                    "PL-WARN",
                    ["STORM1"],
                    severity_level=1,
                    event_code="TSTORM1",
                )
                _insert_alert(
                    "PLWX04",
                    "PL-WARN",
                    ["HAIL3"],
                    severity_level=3,
                    event_code="HAIL3",
                )

                collection = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T01:00:00+00:00",
                )

        self.assertEqual(
            {
                feature["properties"]["aprsbox_area_code"]
                for feature in collection["features"]
            },
            {"HEAT2", "HEAT3", "STORM1", "HAIL3"},
        )

    def test_shared_area_uses_highest_active_severity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            geodata_root = Path(temp_dir)
            _write_geodata(
                geodata_root,
                "pl",
                [_feature("area_code", "1465", 20.0)],
            )
            collection = build_alert_area_feature_collection(
                [
                    {
                        "id": 11,
                        "alarm_group": "PL-WARN",
                        "area_codes": ["1465"],
                        "severity_level": 1,
                    },
                    {
                        "id": 12,
                        "alarm_group": "PL-WARN",
                        "area_codes": ["1465"],
                        "severity_level": 3,
                    },
                    {
                        "id": 13,
                        "alarm_group": "PL-WARN",
                        "area_codes": ["1465"],
                        "severity_level": 2,
                    },
                ],
                geodata_root=geodata_root,
            )

        self.assertEqual(len(collection["features"]), 1)
        self.assertEqual(
            collection["features"][0]["properties"]["aprsbox_severity_level"],
            3,
        )
        self.assertEqual(
            collection["features"][0]["properties"]["aprsbox_alert_color"],
            "red",
        )
        self.assertEqual(
            {
                contributor["id"]
                for contributor in collection["features"][0]["properties"][
                    "aprsbox_alerts"
                ]
            },
            {11, 12, 13},
        )

    def test_shared_area_downgrades_after_stronger_alert_expires(self) -> None:
        with temporary_database():
            with tempfile.TemporaryDirectory() as temp_dir:
                geodata_root = Path(temp_dir)
                _write_geodata(
                    geodata_root,
                    "pl",
                    [_feature("area_code", "1465", 20.0)],
                )
                _insert_alert(
                    "PLWX1",
                    "PL-WARN",
                    ["1465"],
                    severity_level=1,
                    expires_at="2026-01-01T02:00:00+00:00",
                )
                _insert_alert(
                    "PLWX3",
                    "PL-WARN",
                    ["1465"],
                    severity_level=3,
                    expires_at="2026-01-01T00:30:00+00:00",
                )

                before = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T00:20:00+00:00",
                )
                after = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T00:40:00+00:00",
                )

        self.assertEqual(
            before["features"][0]["properties"]["aprsbox_alert_color"],
            "red",
        )
        self.assertEqual(
            after["features"][0]["properties"]["aprsbox_alert_color"],
            "yellow",
        )

    def test_polygon_disappears_after_last_alert_expires(self) -> None:
        with temporary_database():
            with tempfile.TemporaryDirectory() as temp_dir:
                geodata_root = Path(temp_dir)
                _write_geodata(
                    geodata_root,
                    "pl",
                    [_feature("area_code", "1465", 20.0)],
                )
                _insert_alert(
                    "PLWX3",
                    "PL-WARN",
                    ["1465"],
                    severity_level=3,
                    expires_at="2026-01-01T00:30:00+00:00",
                )

                before = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T00:20:00+00:00",
                )
                after = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T00:40:00+00:00",
                )

        self.assertEqual(len(before["features"]), 1)
        self.assertEqual(after["features"], [])

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
                    SET valid_until_utc = '2026-01-01T02:00:00+00:00',
                        is_active = 1
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

    def test_three_area_alerts_are_visible_together_and_delete_independently(self) -> None:
        with temporary_database():
            with tempfile.TemporaryDirectory() as temp_dir:
                geodata_root = Path(temp_dir)
                _write_geodata(
                    geodata_root,
                    "pl",
                    [
                        _feature("area_code", "1465", 20.0),
                        _feature("area_code", "2401", 21.0),
                        _feature("area_code", "3262", 22.0),
                    ],
                )
                for area_code, message_id in (
                    ("1465", "129AA"),
                    ("2401", "82BCD"),
                    ("3262", "F913A"),
                ):
                    _receive_group_alert(area_code, message_id)

                together = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T01:00:00+00:00",
                )
                alerts = fetch_all(
                    "SELECT id, area_code FROM aprs_alerts ORDER BY id"
                )
                removed_id = next(
                    int(row["id"])
                    for row in alerts
                    if row["area_code"] == "2401"
                )
                self.assertTrue(delete_alert(removed_id))
                after_delete = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T01:00:00+00:00",
                )

        self.assertEqual(
            {
                feature["properties"]["aprsbox_area_code"]
                for feature in together["features"]
            },
            {"1465", "2401", "3262"},
        )
        self.assertEqual(
            {
                feature["properties"]["aprsbox_area_code"]
                for feature in after_delete["features"]
            },
            {"1465", "3262"},
        )

    def test_incomplete_logical_alert_draws_all_areas_received_in_its_parts(self) -> None:
        with temporary_database():
            with tempfile.TemporaryDirectory() as temp_dir:
                geodata_root = Path(temp_dir)
                _write_geodata(
                    geodata_root,
                    "pl",
                    [
                        _feature("area_code", "1465", 20.0),
                        _feature("area_code", "1466", 21.0),
                        _feature("area_code", "1412", 22.0),
                    ],
                )
                _receive_multipart_group_alert(
                    part_number=2,
                    parts_total=3,
                    area_codes=("1412", "1466"),
                    message_id="77BD1",
                )
                _receive_multipart_group_alert(
                    part_number=1,
                    parts_total=3,
                    area_codes=("1465", "1466"),
                    message_id="91AC2",
                )

                parent = fetch_all(
                    """
                    SELECT received_parts, parts_total, completion_status,
                           area_codes_json
                    FROM aprs_alerts
                    """
                )[0]
                collection = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T01:00:00+00:00",
                )

        self.assertEqual(int(parent["received_parts"]), 2)
        self.assertEqual(int(parent["parts_total"]), 3)
        self.assertEqual(parent["completion_status"], "incomplete")
        self.assertEqual(
            json.loads(parent["area_codes_json"]),
            ["1465", "1466", "1412"],
        )
        self.assertEqual(
            {
                feature["properties"]["aprsbox_area_code"]
                for feature in collection["features"]
            },
            {"1465", "1466", "1412"},
        )

    def test_shared_area_remains_until_last_active_alarm_is_removed(self) -> None:
        with temporary_database():
            with tempfile.TemporaryDirectory() as temp_dir:
                geodata_root = Path(temp_dir)
                _write_geodata(
                    geodata_root,
                    "pl",
                    [_feature("area_code", "1465", 20.0)],
                )
                _receive_group_alert("1465", "129AA")
                _receive_group_alert("1465", "82BCD")
                alert_ids = [
                    int(row["id"])
                    for row in fetch_all("SELECT id FROM aprs_alerts ORDER BY id")
                ]

                both_active = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T01:00:00+00:00",
                )
                self.assertTrue(delete_alert(alert_ids[0]))
                one_active = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T01:00:00+00:00",
                )
                self.assertTrue(delete_alert(alert_ids[1]))
                none_active = get_active_alert_area_feature_collection(
                    geodata_root=geodata_root,
                    now="2026-01-01T01:00:00+00:00",
                )

        self.assertEqual(len(both_active["features"]), 1)
        self.assertEqual(len(one_active["features"]), 1)
        self.assertEqual(none_active["features"], [])

    def test_active_area_uses_a_dedicated_map_refresh_payload(self) -> None:
        with temporary_database():
            _insert_alert("PLWXSR", "PL-WARN", ["1465"])

            station_payload = get_map_station_markers_payload()
            payload = get_map_alert_areas_payload()

        self.assertNotIn("alert_areas", station_payload)
        self.assertTrue(payload["revision"])
        alert_areas = payload["alert_areas"]
        self.assertEqual(alert_areas["type"], "FeatureCollection")
        self.assertEqual(len(alert_areas["features"]), 1)
        self.assertEqual(
            alert_areas["features"][0]["properties"]["aprsbox_area_code"],
            "1465",
        )
        self.assertEqual(len(alert_areas["alerts"]), 1)
        self.assertEqual(
            alert_areas["alerts"][0]["source_callsign"],
            "PLWXSR",
        )
        self.assertTrue(alert_areas["alerts"][0]["has_geometry"])
        self.assertEqual(
            alert_areas["features"][0]["properties"]["aprsbox_alerts"][0]["id"],
            alert_areas["alerts"][0]["id"],
        )

    def test_map_alert_area_revision_changes_only_with_source_data(self) -> None:
        with temporary_database():
            _insert_alert(
                "PLWXREV",
                "PL-WARN",
                ["1465"],
                severity_level=1,
            )

            first = get_map_alert_areas_payload()
            unchanged = get_map_alert_areas_payload()
            execute(
                """
                UPDATE aprs_alerts
                SET severity_level = 3,
                    updated_at = '2026-01-01T00:01:00+00:00'
                WHERE source_callsign = 'PLWXREV'
                """
            )
            changed = get_map_alert_areas_payload()

        self.assertEqual(first["revision"], unchanged["revision"])
        self.assertNotEqual(first["revision"], changed["revision"])
        self.assertEqual(
            changed["alert_areas"]["features"][0]["properties"][
                "aprsbox_alert_color"
            ],
            "red",
        )

    def test_map_script_uses_a_noninteractive_layer_between_tiles_and_markers(self) -> None:
        source = Path("app/static/js/map.js").read_text(encoding="utf-8")

        self.assertIn('const alertAreasPaneName = "alert-areas-pane";', source)
        self.assertIn('alertAreasPane.style.zIndex = "350";', source)
        self.assertIn("alertAreasPane.style.pointerEvents = \"none\";", source)
        self.assertIn("alertAreaLayer.clearLayers();", source)
        self.assertIn("alertAreaLayer.addData(featureCollection);", source)
        self.assertIn("aprsbox_alert_color", source)
        self.assertIn('["yellow", "orange", "red", "gray"]', source)
        self.assertIn("color,", source)
        self.assertIn("fillColor: color", source)
        self.assertIn("weight: 2", source)
        self.assertIn("fillOpacity: 0.10", source)
        self.assertIn("dashArray: null", source)
        self.assertIn("reconcileAlertAreas(payload.alert_areas);", source)
        self.assertIn('const alertAreasEndpoint = root.dataset.alertAreasEndpoint || "";', source)
        self.assertIn('headers["If-None-Match"] = alertAreasEtag;', source)
        self.assertIn("function scheduleInitialAlertLoad()", source)
        self.assertIn("!firstStationRefreshSettled", source)
        self.assertIn("!firstMapTileLoaded && !initialAlertTileFallbackElapsed", source)
        self.assertIn("runWhenBrowserIdle", source)

    def test_map_toolbar_opens_panel_with_per_alert_visibility_switches(self) -> None:
        source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        template = Path("app/templates/map.html").read_text(encoding="utf-8")
        base_template = Path("app/templates/base.html").read_text(encoding="utf-8")
        styles = Path("app/static/css/map.css").read_text(encoding="utf-8")

        self.assertIn('id="map-toggle-alarm-areas"', template)
        self.assertIn('id="map-toggle-alarm-areas-icon"', template)
        self.assertIn('id="map-alerts-overlay"', template)
        self.assertIn('id="map-alerts-overlay-list"', template)
        self.assertIn('class="map-alerts-overlay-bottom-gap"', template)
        self.assertIn('aria-controls="map-alerts-overlay"', template)
        self.assertIn("alarm-light-outline.svg", template)
        self.assertIn("data-i18n-show-alarm-list", template)
        self.assertIn("data-i18n-hide-alarm-list", template)
        self.assertIn("data-i18n-visible-on-map", template)
        self.assertTrue(Path("app/static/icons/alarm-light-outline.svg").is_file())
        self.assertTrue(
            Path("app/static/icons/alarm-light-off-outline.svg").is_file()
        )

        self.assertIn(
            'const mapHiddenAlertIdsStorageKey = "aprsbox-map-hidden-alert-ids";',
            source,
        )
        self.assertIn(
            'const mapAlertsOverlayOpenStorageKey = "aprsbox-map-alerts-overlay-open";',
            source,
        )
        self.assertIn("function resolveHiddenAlertIds()", source)
        self.assertIn("function resolveAlertsOverlayOpen()", source)
        self.assertIn("function persistAlertsOverlayOpen()", source)
        self.assertIn("function visibleAlertAreaFeatureCollection()", source)
        self.assertIn("if (!alertsOverlayOpen)", source)
        self.assertIn("function renderAlertPanel()", source)
        self.assertIn("const maximumVisibleAlertCards = 4;", source)
        self.assertIn("function constrainAlertPanelListHeight()", source)
        self.assertIn("function positionAlertPanelBelowLeafletControls()", source)
        self.assertIn("function alertPanelSignature()", source)
        self.assertIn('mapCanvas.querySelector(".leaflet-control-zoom")', source)
        self.assertIn('alertsOverlayList.dataset.scrollable = shouldScroll ? "true" : "false";', source)
        self.assertIn('checkbox.setAttribute("role", "switch");', source)
        self.assertIn("hiddenAlertIds.add(alertId);", source)
        self.assertIn("hiddenAlertIds.delete(alertId);", source)
        self.assertIn('item.dataset.visible = checkbox.checked ? "true" : "false";', source)
        self.assertIn("lastAlertPanelSignature = alertPanelSignature();", source)
        self.assertIn("setAlertsOverlayOpen(opening);", source)
        self.assertIn("startInitialAlertLoad();", source)
        self.assertIn("renderVisibleAlertAreas();", source)
        self.assertIn("setAlertsOverlayOpen(alertsOverlayOpen, { persist: false });", source)
        self.assertIn("top: var(--map-alert-overlay-top, 5.35rem);", styles)
        self.assertIn("max-height: var(--map-alert-list-limit, none);", styles)
        self.assertIn('.map-alerts-overlay-list[data-scrollable="true"]', styles)
        self.assertIn("padding: 0.56rem 0.56rem 0;", styles)
        self.assertIn("flex: 0 0 1.25rem;", styles)
        self.assertIn('data-alert-areas-endpoint="{{ map_alert_areas_endpoint }}"', template)
        self.assertIn("-deferred-alerts-1", template)
        self.assertIn("-map-alert-panel-8", base_template)


if __name__ == "__main__":
    unittest.main()
