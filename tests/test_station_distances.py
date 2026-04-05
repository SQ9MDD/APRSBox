import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, init_db
from app.services.content import get_station_detail, heard_stations, update_station_settings
from app.services.map_service import get_map_station_payload


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


def insert_position_frame(line: str) -> None:
    execute(
        """
        INSERT INTO traffic_frames(source, interface_id, direction, band, format, line, port, command, length, hex, created_at)
        VALUES (?, NULL, 'RX', '2m', 'TNC2', ?, '', '', ?, '', '2026-01-01T00:00:00+00:00')
        """,
        ("rf", line, len(line)),
    )


class StationDistanceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
