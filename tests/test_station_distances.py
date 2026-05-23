import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, fetch_one, init_db
from app.services.content import get_station_detail, heard_stations, update_station_settings
from app.services.map_service import get_map_station_payload, get_station_detail_track_payload


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


def station_payload(latitude: str = "52.2297", longitude: str = "21.0122") -> dict[str, str]:
    return {
        "callsign": "sq9xyz",
        "ssid": "9",
        "beacon_interface_id": "",
        "beacon_comment": "",
        "beacon_interval_minutes": "30",
        "beacon_path": "",
        "status_text": "",
        "status_interval_minutes": "30",
        "latitude": latitude,
        "longitude": longitude,
        "symbol_table": "/",
        "symbol_code": ">",
        "default_units": "metric",
    }


def insert_position_frame(
    line: str,
    *,
    created_at: str = "2026-01-01T00:00:00+00:00",
    interface_id: int | None = None,
) -> None:
    execute(
        """
        INSERT INTO traffic_frames(source, interface_id, direction, band, format, line, port, command, length, hex, created_at)
        VALUES (?, ?, 'RX', '2m', 'TNC2', ?, '', '', ?, '', ?)
        """,
        ("rf", interface_id, line, len(line), created_at),
    )


def insert_modem(*, name: str, band: str) -> int:
    execute(
        """
        INSERT INTO modems(name, modem_type, band, device_path, enabled, notes, created_at, updated_at)
        VALUES (?, 'TCP', ?, '127.0.0.1:9001', 1, '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (name, band),
    )
    row = fetch_one("SELECT id FROM modems WHERE name = ?", (name,))
    assert row is not None
    return int(row["id"])


class StationDistanceTests(unittest.TestCase):
    def test_mic_e_position_with_ambiguity_space_appears_in_station_list_and_map(self) -> None:
        with temporary_database():
            update_station_settings(station_payload())
            insert_position_frame("SP0DN>UQUQ1L,WIDE1-1,WIDE2-1:`12Xl \x1cy/446.006MHz Dejw wilga. zapraszm do kontaktu i testow_%")

            stations = heard_stations()
            self.assertEqual(len(stations), 1)
            self.assertEqual(stations[0]["display_callsign"], "SP0DN")
            self.assertTrue(bool(stations[0]["latitude"]))
            self.assertTrue(bool(stations[0]["longitude"]))
            self.assertEqual(stations[0]["position_ambiguity_digits"], 1)
            self.assertTrue(bool(stations[0]["position_ambiguous"]))

            map_payload = get_map_station_payload()
            self.assertEqual(len(map_payload["stations"]), 1)
            self.assertEqual(map_payload["stations"][0]["display_callsign"], "SP0DN")
            self.assertEqual(map_payload["stations"][0]["position_ambiguity_digits"], 1)
            self.assertTrue(bool(map_payload["stations"][0]["position_ambiguous"]))

    def test_distance_is_exposed_in_station_list_detail_and_map_payload(self) -> None:
        with temporary_database():
            update_station_settings(station_payload())
            insert_position_frame("SP8ABC-9>APRS:!5218.37N\\02104.87Eu243/002/A=000278Back on track!")

            stations = heard_stations()
            self.assertEqual(len(stations), 1)
            self.assertEqual(stations[0]["display_callsign"], "SP8ABC-9")
            self.assertEqual(stations[0]["distance_km"], 9.7)

            detail = get_station_detail("SP8ABC-9")
            assert detail is not None
            self.assertEqual(detail["distance_km"], 9.7)

            map_payload = get_map_station_payload()
            self.assertEqual(len(map_payload["stations"]), 1)
            self.assertEqual(map_payload["stations"][0]["distance_km"], 9.7)

    def test_distance_is_none_when_station_reference_location_is_missing(self) -> None:
        with temporary_database():
            update_station_settings(station_payload(latitude="", longitude=""))
            insert_position_frame("SP8ABC-9>APRS:!5218.37N\\02104.87Eu243/002/A=000278Back on track!")

            stations = heard_stations()
            self.assertEqual(len(stations), 1)
            self.assertIsNone(stations[0]["distance_km"])

    def test_map_payload_exposes_interface_metadata_for_map_filtering(self) -> None:
        with temporary_database():
            update_station_settings(station_payload(latitude="51.1000", longitude="20.1000"))
            first_interface_id = insert_modem(name="VHF RX", band="2m")
            second_interface_id = insert_modem(name="UHF RX", band="70cm")
            insert_position_frame(
                "SP8AAA-9>APRS:!5218.37N\\02104.87E>Station one",
                created_at="2026-01-01T00:00:00+00:00",
                interface_id=first_interface_id,
            )
            insert_position_frame(
                "SP8BBB-9>APRS:!5219.00N\\02105.30E>Station two",
                created_at="2026-01-01T00:05:00+00:00",
                interface_id=second_interface_id,
            )

            map_payload = get_map_station_payload()
            station_by_callsign = {
                str(item.get("display_callsign") or ""): item
                for item in map_payload["stations"]
            }
            self.assertEqual(station_by_callsign["SP8AAA-9"]["interface_id"], first_interface_id)
            self.assertEqual(station_by_callsign["SP8BBB-9"]["interface_id"], second_interface_id)

            interfaces = map_payload.get("interfaces") or []
            interface_ids = {int(item["modem_id"]) for item in interfaces}
            self.assertEqual(interface_ids, {first_interface_id, second_interface_id})
            by_id = {int(item["modem_id"]): item for item in interfaces}
            self.assertEqual(by_id[first_interface_id]["name"], "VHF RX")
            self.assertEqual(by_id[first_interface_id]["band"], "2m")
            self.assertEqual(by_id[second_interface_id]["name"], "UHF RX")
            self.assertEqual(by_id[second_interface_id]["band"], "70cm")

    def test_map_payload_exposes_mobile_tracks_for_station_history(self) -> None:
        with temporary_database():
            update_station_settings(station_payload())
            interface_id = insert_modem(name="Track TNC", band="2m")
            insert_position_frame(
                "SP8ABC-9>APRS:!5218.37N\\02104.87Eu243/002/A=000278Back on track!",
                created_at="2026-01-01T00:00:00+00:00",
                interface_id=interface_id,
            )
            insert_position_frame(
                "SP8ABC-9>APRS:!5219.00N\\02105.30Eu240/010/A=000300Moving east",
                created_at="2026-01-01T00:05:00+00:00",
                interface_id=interface_id,
            )

            map_payload = get_map_station_payload()
            self.assertIn("mobile_tracks", map_payload)
            self.assertEqual(len(map_payload["mobile_tracks"]), 1)
            track = map_payload["mobile_tracks"][0]
            self.assertEqual(track["display_callsign"], "SP8ABC-9")
            self.assertEqual(len(track["points"]), 2)
            self.assertEqual(track["points"][0]["interface_id"], interface_id)
            self.assertEqual(track["points"][1]["interface_id"], interface_id)
            self.assertEqual(track["points"][0]["heard_at"], "2026-01-01T00:00:00+00:00")
            self.assertEqual(track["points"][1]["heard_at"], "2026-01-01T00:05:00+00:00")

    def test_map_payload_ignores_null_island_points_in_mobile_tracks(self) -> None:
        with temporary_database():
            update_station_settings(station_payload())
            insert_position_frame(
                "SP8ABC-9>APRS:!5218.37N\\02104.87Eu243/002/A=000278Back on track!",
                created_at="2026-01-01T00:00:00+00:00",
            )
            insert_position_frame(
                "SP8ABC-9>APRS:!0000.00N\\00000.00Eu243/002/A=000278No GPS fix",
                created_at="2026-01-01T00:03:00+00:00",
            )
            insert_position_frame(
                "SP8ABC-9>APRS:!5219.00N\\02105.30Eu240/010/A=000300Moving east",
                created_at="2026-01-01T00:05:00+00:00",
            )

            map_payload = get_map_station_payload()
            self.assertEqual(len(map_payload["mobile_tracks"]), 1)
            track = map_payload["mobile_tracks"][0]
            self.assertEqual(len(track["points"]), 2)
            self.assertEqual(track["points"][0]["heard_at"], "2026-01-01T00:00:00+00:00")
            self.assertEqual(track["points"][1]["heard_at"], "2026-01-01T00:05:00+00:00")

    def test_map_payload_builds_tracks_for_position_changes_without_course_speed(self) -> None:
        with temporary_database():
            update_station_settings(station_payload())
            insert_position_frame(
                "SP8ABC-9>APRS:!5218.37N\\02104.87E>First position only",
                created_at="2026-01-01T00:00:00+00:00",
            )
            insert_position_frame(
                "SP8ABC-9>APRS:!5219.00N\\02105.30E>Second position only",
                created_at="2026-01-01T00:05:00+00:00",
            )

            map_payload = get_map_station_payload()
            self.assertEqual(len(map_payload["mobile_tracks"]), 1)
            track = map_payload["mobile_tracks"][0]
            self.assertEqual(track["display_callsign"], "SP8ABC-9")
            self.assertEqual(len(track["points"]), 2)
            self.assertEqual(track["points"][0]["heard_at"], "2026-01-01T00:00:00+00:00")
            self.assertEqual(track["points"][1]["heard_at"], "2026-01-01T00:05:00+00:00")

    def test_map_payload_does_not_draw_track_for_unchanged_position(self) -> None:
        with temporary_database():
            update_station_settings(station_payload())
            insert_position_frame(
                "SP8ABC-9>APRS:!5218.37N\\02104.87E>First position only",
                created_at="2026-01-01T00:00:00+00:00",
            )
            insert_position_frame(
                "SP8ABC-9>APRS:!5218.37N\\02104.87E>Still same position",
                created_at="2026-01-01T00:05:00+00:00",
            )

            map_payload = get_map_station_payload()
            self.assertEqual(len(map_payload["mobile_tracks"]), 0)

    def test_map_payload_exposes_phg_range_for_station_with_phg(self) -> None:
        with temporary_database():
            update_station_settings(station_payload())
            insert_position_frame(
                "SP8ABC-9>APRS:!5218.37N\\02104.87E#PHG5130/WIDE1-1 Digi test",
                created_at="2026-01-01T00:00:00+00:00",
            )

            map_payload = get_map_station_payload()
            self.assertEqual(len(map_payload["stations"]), 1)
            station = map_payload["stations"][0]
            self.assertEqual(station["display_callsign"], "SP8ABC-9")
            self.assertEqual(station["phg_power_w"], 25.0)
            self.assertEqual(station["phg_height_ft"], 20.0)
            self.assertEqual(station["phg_gain_dbi"], 3.0)
            self.assertEqual(station["phg_direction"], "omni")
            self.assertAlmostEqual(float(station["phg_range_km"]), 12.79, places=2)

    def test_map_payload_exposes_qsy_fields_when_present(self) -> None:
        with temporary_database():
            update_station_settings(station_payload(latitude="53.2297", longitude="21.0122"))
            insert_position_frame(
                "SP8ABC-9>APRS:!5218.37N\\02104.87E>145.575MHz C103 +060 R30k SR9ABC",
                created_at="2026-01-01T00:00:00+00:00",
            )

            map_payload = get_map_station_payload()
            self.assertEqual(len(map_payload["stations"]), 1)
            station = map_payload["stations"][0]
            self.assertEqual(station["display_callsign"], "SP8ABC-9")
            self.assertEqual(station["qsy_frequency_mhz"], 145.575)
            self.assertEqual(station["qsy_tone"], "C103")
            self.assertEqual(station["qsy_offset_khz"], 60)
            self.assertEqual(station["qsy_callsign"], "SR9ABC")

    def test_station_detail_track_payload_returns_track_for_selected_mobile_station(self) -> None:
        with temporary_database():
            update_station_settings(station_payload())
            insert_position_frame(
                "SP8ABC-9>APRS:!5218.37N\\02104.87Eu243/002/A=000278Back on track!",
                created_at="2026-01-01T00:00:00+00:00",
            )
            insert_position_frame(
                "SP8ABC-9>APRS:!5219.00N\\02105.30Eu240/010/A=000300Moving east",
                created_at="2026-01-01T00:05:00+00:00",
            )

            track_payload = get_station_detail_track_payload("SP8ABC-9")
            self.assertEqual(track_payload["display_callsign"], "SP8ABC-9")
            self.assertEqual(len(track_payload["points"]), 2)
            self.assertEqual(track_payload["points"][0]["heard_at"], "2026-01-01T00:00:00+00:00")
            self.assertEqual(track_payload["points"][1]["heard_at"], "2026-01-01T00:05:00+00:00")


if __name__ == "__main__":
    unittest.main()
