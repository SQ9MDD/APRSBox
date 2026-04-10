import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import execute, init_db
from app.services.content import get_heard_station_snapshots, get_related_ssids, get_station_detail, get_visible_station_snapshots


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


def sample_snapshot() -> dict[str, object]:
    return {
        "callsign": "SP8ABC",
        "ssid": "9",
        "display_callsign": "SP8ABC-9",
        "origin": "heard",
        "activity_label": "Last heard",
        "activity_age_label": "Last heard age",
        "last_heard_at": "2026-01-01T00:00:00+00:00",
        "last_heard_age_s": 0,
        "last_heard_label": "2026.01.01 01:00:00",
        "last_heard_date": "2026.01.01 01:00:00",
        "last_heard_relative": "teraz",
        "source": "SP8ABC-9",
        "destination": "APRS",
        "path": "WIDE1-1",
        "raw_text": "SP8ABC-9>APRS:!5222.00N/02100.00E>Test",
        "entity_class": "stationary",
        "frame_type": "position",
        "frame_type_label": "Position",
        "symbol": "/>",
        "symbol_table": "/",
        "symbol_code": ">",
        "symbol_icon": "icons/verG/64.gif",
        "comment": "Test",
        "data_raw": {},
        "latitude": "52.36667",
        "longitude": "21.00000",
        "distance_km": 0.0,
        "aprs_device": None,
        "aprs_device_short": "",
    }


class StationSnapshotPerformanceTests(unittest.TestCase):
    def test_heard_station_snapshot_query_limits_scanned_rows(self) -> None:
        with temporary_database():
            with patch("app.services.content.fetch_all", return_value=[]) as fetch_all_mock:
                get_heard_station_snapshots(limit=25)

            query, params = fetch_all_mock.call_args[0]
            self.assertIn("LIMIT ?", query)
            self.assertEqual(params[-1], 4000)

    def test_station_detail_helpers_can_reuse_prebuilt_snapshots(self) -> None:
        snapshots = [sample_snapshot()]
        with patch("app.services.content.get_visible_station_snapshots", side_effect=AssertionError("unexpected lookup")):
            detail = get_station_detail("SP8ABC-9", snapshots=snapshots)
            related = get_related_ssids("SP8ABC", snapshots=snapshots)

        assert detail is not None
        self.assertEqual(detail["display_callsign"], "SP8ABC-9")
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]["display_callsign"], "SP8ABC-9")

    def test_visible_station_snapshots_uses_cache_when_source_data_is_unchanged(self) -> None:
        snapshots = [sample_snapshot()]
        with patch("app.services.content.get_heard_station_snapshots", return_value=snapshots) as heard_mock, patch(
            "app.services.content.get_local_tx_station_snapshots",
            return_value=[],
        ) as local_mock, patch(
            "app.services.content.get_station_settings",
            return_value={"latitude": "52.2297", "longitude": "21.0122"},
        ), patch(
            "app.services.content._latest_station_snapshot_frame_id",
            return_value=123,
        ):
            first = get_visible_station_snapshots(limit=500)
            second = get_visible_station_snapshots(limit=500)

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(heard_mock.call_count, 1)
        self.assertEqual(local_mock.call_count, 1)

    def test_heard_station_snapshots_map_third_party_position_to_inner_sender(self) -> None:
        with temporary_database():
            line = "SR0DZ>APDW16,SR5NWA*,WIDE1*:}SQ2IBK>U2QU28,TCPIP,SR0DZ*:`0SZl4{[/>145.575MHz&"
            execute(
                """
                INSERT INTO traffic_frames(
                    source, interface_id, direction, band, format, line, port, command, length, hex, created_at
                )
                VALUES (?, NULL, 'rx', '2m', 'TNC2', ?, '0', 'RX', ?, '', '2026-01-01T00:00:00+00:00')
                """,
                ("TNC-2m", line, len(line)),
            )

            snapshots = get_heard_station_snapshots(limit=50)
            display_callsigns = {str(item.get("display_callsign") or "") for item in snapshots}
            self.assertIn("SQ2IBK", display_callsigns)
            self.assertNotIn("SR0DZ", display_callsigns)

            station = next(item for item in snapshots if str(item.get("display_callsign") or "") == "SQ2IBK")
            self.assertEqual(station["callsign"], "SQ2IBK")
            self.assertTrue(str(station.get("latitude") or ""))
            self.assertTrue(str(station.get("longitude") or ""))


if __name__ == "__main__":
    unittest.main()
