import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import execute, fetch_one, init_db, reset_runtime_operational_data
from app.services import content
from app.services.content import projected_station_list, station_summary
from app.services.map_service import get_map_station_markers_payload
from app.services.map_station_state import (
    expire_map_station_state,
    read_map_station_rf_snapshots,
    rebuild_map_station_state,
)
from app.services.outbound import persist_outbound_frame
from app.services.traffic import process_normalized_tnc2_rx


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        try:
            init_db()
            content._STATION_SNAPSHOT_CACHE.clear()
            content._VISIBLE_STATION_SNAPSHOT_TTL_CACHE.clear()
            yield database_path
        finally:
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


class MapStationStateTests(unittest.TestCase):
    def test_rebuild_materializes_existing_history(self) -> None:
        with temporary_database():
            line = "SP8OLD>APRS:!5222.00N/02100.00E>History"
            execute(
                """
                INSERT INTO traffic_frames(
                    source, source_kind, direction, format, line, length, created_at
                ) VALUES ('RF', 'rf', 'rx', 'TNC2', ?, ?, '2026-01-01T00:00:00+00:00')
                """,
                (line, len(line)),
            )
            result = rebuild_map_station_state(force=True)
            payload = get_map_station_markers_payload()
            self.assertEqual(result["station_count"], 1)
            self.assertEqual(payload["stations"][0]["display_callsign"], "SP8OLD")

    def test_map_request_reads_projection_without_parsing_history(self) -> None:
        with temporary_database():
            rebuild_map_station_state(force=True)
            self.assertTrue(process_normalized_tnc2_rx(
                "SP8ABC-9>APRS:!5222.00N/02100.00E>Test",
                source="RF", source_kind="rf", timestamp="2026-01-01T00:00:00+00:00",
            ))
            with patch("app.services.content.parse_tnc2_frame", side_effect=AssertionError("history parsed")):
                payload = get_map_station_markers_payload()
            self.assertEqual([row["display_callsign"] for row in payload["stations"]], ["SP8ABC-9"])

    def test_station_list_and_summary_read_projection_without_parsing_history(self) -> None:
        with temporary_database():
            rebuild_map_station_state(force=True)
            process_normalized_tnc2_rx(
                "SP8ABC-9>APRS:!5222.00N/02100.00E>Test",
                source="RF", source_kind="rf", timestamp="2026-01-01T00:00:00+00:00",
            )
            with patch("app.services.content.parse_tnc2_frame", side_effect=AssertionError("history parsed")):
                stations = projected_station_list()["stations"]
                summary = station_summary(read_map_station_rf_snapshots())
            self.assertEqual([row["display_callsign"] for row in stations], ["SP8ABC-9"])
            self.assertEqual(summary["total"], 1)

    def test_delta_contains_only_changed_station(self) -> None:
        with temporary_database():
            rebuild_map_station_state(force=True)
            process_normalized_tnc2_rx(
                "SP8AAA>APRS:!5222.00N/02100.00E>A",
                source="RF", source_kind="rf", timestamp="2026-01-01T00:00:00+00:00",
            )
            revision = int(fetch_one("SELECT revision FROM map_station_state_meta WHERE id = 1")["revision"])
            process_normalized_tnc2_rx(
                "SP8BBB>APRS:!5223.00N/02101.00E>B",
                source="IS", source_kind="aprsis", timestamp="2026-01-01T00:01:00+00:00",
            )
            payload = get_map_station_markers_payload(since_revision=revision)
            self.assertFalse(payload["full_snapshot"])
            self.assertEqual([row["display_callsign"] for row in payload["stations"]], ["SP8BBB"])
            self.assertEqual(payload["removed_station_keys"], [])
            station_list = projected_station_list(since_revision=revision)
            self.assertFalse(station_list["full_snapshot"])
            self.assertEqual(
                [row["display_callsign"] for row in station_list["stations"]],
                ["SP8BBB"],
            )

    def test_killed_object_is_returned_as_delta_tombstone(self) -> None:
        with temporary_database():
            rebuild_map_station_state(force=True)
            process_normalized_tnc2_rx(
                "SP8ABC>APRS:;OBJTEST  *010203z5228.23N/02101.28E#Object",
                source="RF", source_kind="rf", timestamp="2026-01-01T00:00:00+00:00",
            )
            revision = int(fetch_one("SELECT revision FROM map_station_state_meta WHERE id = 1")["revision"])
            process_normalized_tnc2_rx(
                "SP8ABC>APRS:;OBJTEST  _010204z5228.23N/02101.28E#Object",
                source="RF", source_kind="rf", timestamp="2026-01-01T00:01:00+00:00",
            )
            payload = get_map_station_markers_payload(since_revision=revision)
            self.assertEqual(payload["stations"], [])
            self.assertEqual(payload["removed_station_keys"], ["OBJTEST"])

    def test_rf_status_and_local_tx_update_existing_projection(self) -> None:
        with temporary_database():
            rebuild_map_station_state(force=True)
            process_normalized_tnc2_rx(
                "SP8ABC>APRS,WIDE1-1:!5222.00N/02100.00E>Position",
                source="RF", source_kind="rf", timestamp="2026-01-01T00:00:00+00:00",
            )
            process_normalized_tnc2_rx(
                "SP8ABC>APRS:>Station online",
                source="RF", source_kind="rf", timestamp="2026-01-01T00:01:00+00:00",
            )
            persist_outbound_frame(
                source="RF-OUT",
                line="SP8ABC>APRS:!5224.00N/02102.00E>Local TX",
            )
            row = fetch_one("SELECT snapshot_json FROM map_station_state WHERE station_key = 'SP8ABC'")
            self.assertIsNotNone(row)
            self.assertIn('"status_text":"Station online"', str(row["snapshot_json"]))
            self.assertEqual(get_map_station_markers_payload()["station_count"], 1)

    def test_runtime_history_reset_invalidates_projection(self) -> None:
        with temporary_database():
            rebuild_map_station_state(force=True)
            process_normalized_tnc2_rx(
                "SP8ABC>APRS:!5222.00N/02100.00E>Position",
                source="RF", source_kind="rf", timestamp="2026-01-01T00:00:00+00:00",
            )
            reset_runtime_operational_data()
            payload = get_map_station_markers_payload()
            self.assertEqual(payload["stations"], [])
            self.assertEqual(payload["revision"], 0)

    def test_retention_expiry_produces_delta_tombstone(self) -> None:
        with temporary_database():
            rebuild_map_station_state(force=True)
            process_normalized_tnc2_rx(
                "SP8ABC>APRS:!5222.00N/02100.00E>Position",
                source="RF", source_kind="rf", timestamp="2026-01-01T00:00:00+00:00",
            )
            revision = int(fetch_one("SELECT revision FROM map_station_state_meta WHERE id = 1")["revision"])
            self.assertEqual(expire_map_station_state(cutoff="2026-01-01T01:00:00+00:00"), 1)
            payload = get_map_station_markers_payload(since_revision=revision)
            self.assertEqual(payload["removed_station_keys"], ["SP8ABC"])

    def test_retention_expiry_removes_only_stale_source_component(self) -> None:
        with temporary_database():
            rebuild_map_station_state(force=True)
            process_normalized_tnc2_rx(
                "SP8ABC>APRS:!5222.00N/02100.00E>RF",
                source="RF", source_kind="rf", timestamp="2026-01-01T00:00:00+00:00",
            )
            process_normalized_tnc2_rx(
                "SP8ABC>APRS:!5223.00N/02101.00E>IS",
                source="IS", source_kind="aprsis", timestamp="2026-01-01T02:00:00+00:00",
            )
            self.assertEqual(expire_map_station_state(cutoff="2026-01-01T01:00:00+00:00"), 1)
            station = get_map_station_markers_payload()["stations"][0]
            self.assertEqual(station["source_kind"], "aprsis")
            self.assertFalse(station["is_rf"])

    def test_projection_failure_does_not_rollback_traffic_history(self) -> None:
        with temporary_database(), patch(
            "app.services.map_station_state.update_map_station_state_for_frame",
            side_effect=RuntimeError("projection failed"),
        ):
            self.assertTrue(process_normalized_tnc2_rx(
                "SP8ABC>APRS:!5222.00N/02100.00E>Position",
                source="RF", source_kind="rf", timestamp="2026-01-01T00:00:00+00:00",
            ))
            self.assertEqual(int(fetch_one("SELECT COUNT(*) AS total FROM traffic_frames")["total"]), 1)


if __name__ == "__main__":
    unittest.main()
