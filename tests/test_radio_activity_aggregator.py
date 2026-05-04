import contextlib
import importlib.util
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import connect, execute, fetch_one, init_db
from app.services.radio_activity import (
    _floor_to_bucket_start,
    run_radio_activity_aggregation,
)

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None


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


def insert_frame(
    *,
    source: str,
    interface_id: int | None,
    direction: str,
    frame_format: str,
    line: str,
    created_at: str,
    command: str = "",
    band: str = "2m",
) -> None:
    execute(
        """
        INSERT INTO traffic_frames(
            source, interface_id, direction, band, format, line, port, command, length, hex, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, '0', ?, ?, '', ?)
        """,
        (
            source,
            interface_id,
            direction,
            band,
            frame_format,
            line,
            command,
            len(line.encode("utf-8")),
            created_at,
        ),
    )


class RadioActivityAggregatorTests(unittest.TestCase):
    def test_init_db_creates_radio_activity_tables(self) -> None:
        with temporary_database():
            connection = connect()
            try:
                activity_columns = {row["name"] for row in connection.execute("PRAGMA table_info(radio_activity_5m)").fetchall()}
                state_columns = {
                    row["name"] for row in connection.execute("PRAGMA table_info(radio_activity_aggregator_state)").fetchall()
                }
                activity_indexes = {
                    row["name"] for row in connection.execute("PRAGMA index_list('radio_activity_5m')").fetchall()
                }
            finally:
                connection.close()

            self.assertIn("bucket_start_utc", activity_columns)
            self.assertIn("bucket_end_utc", activity_columns)
            self.assertIn("source_name", activity_columns)
            self.assertIn("rx_total", activity_columns)
            self.assertIn("duplicate_total", activity_columns)
            self.assertIn("last_processed_bucket_start_utc", state_columns)
            self.assertIn("idx_radio_activity_5m_bucket_start", activity_indexes)
            self.assertIn("idx_radio_activity_5m_bucket_source", activity_indexes)

    def test_bucket_floor_uses_utc_5m_resolution(self) -> None:
        value = datetime(2026, 5, 4, 10, 7, 52, tzinfo=timezone.utc)
        self.assertEqual(
            _floor_to_bucket_start(value, bucket_minutes=5).isoformat(),
            datetime(2026, 5, 4, 10, 5, 0, tzinfo=timezone.utc).isoformat(),
        )

    def test_aggregates_single_closed_bucket_and_saves_state(self) -> None:
        with temporary_database():
            execute(
                """
                UPDATE station_settings
                SET callsign = 'SQ9MDD', ssid = '4', updated_at = ?
                WHERE id = 1
                """,
                (datetime.now(timezone.utc).replace(microsecond=0).isoformat(),),
            )
            execute(
                """
                UPDATE wx_config
                SET callsign = 'SQ9MDD', ssid = '13', enabled = 1, updated_at = ?
                WHERE id = 1
                """,
                (datetime.now(timezone.utc).replace(microsecond=0).isoformat(),),
            )

            bucket_start = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8ABC-9>APRS,WIDE1-1*::SQ9MDD-4 :hello{01",
                created_at=(bucket_start + timedelta(minutes=1)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8ABC-9>APRS::APRS:?APRSD",
                created_at=(bucket_start + timedelta(minutes=2)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="TX",
                frame_format="TNC2-TX",
                line="SQ9MDD-4>APRS:!5218.37N/02104.87E>Own",
                command="TX",
                created_at=(bucket_start + timedelta(minutes=3)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="TX",
                frame_format="TNC2-TX",
                line="SP9XYZ-1>APRS::SQ9MDD-4 :relay{02",
                command="TX",
                created_at=(bucket_start + timedelta(minutes=3, seconds=30)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="TX",
                frame_format="TNC2-TX",
                line="SQ9MDD-4>APRS:>TX skipped",
                command="TX-SKIP",
                created_at=(bucket_start + timedelta(minutes=4)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP7AAA-1>APRS,RFONLY:!5218.37N/02104.87E>Rf",
                created_at=(bucket_start + timedelta(minutes=4, seconds=20)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="not-a-valid-tnc2-line",
                created_at=(bucket_start + timedelta(minutes=4, seconds=40)).isoformat(),
            )

            result = run_radio_activity_aggregation(
                now_utc=datetime(2026, 5, 4, 10, 7, tzinfo=timezone.utc),
                safety_delay_seconds=30,
            )
            self.assertGreaterEqual(int(result.get("processed_buckets") or 0), 1)

            row = fetch_one(
                """
                SELECT *
                FROM radio_activity_5m
                WHERE bucket_start_utc = ?
                  AND source_name = 'Main TNC'
                """,
                (bucket_start.isoformat(),),
            )
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(int(row["rx_total"]), 4)
            self.assertEqual(int(row["tx_total"]), 2)
            self.assertEqual(int(row["digipeated_total"]), 1)
            self.assertEqual(int(row["own_frames_total"]), 2)
            self.assertEqual(int(row["messages_total"]), 2)
            self.assertEqual(int(row["queries_total"]), 1)
            self.assertEqual(int(row["rfonly_total"]), 1)
            self.assertEqual(int(row["parse_error_total"]), 1)
            self.assertEqual(int(row["duplicate_total"]), 0)
            self.assertEqual(int(row["direct_heard_total"]), 2)
            self.assertEqual(int(row["indirect_heard_total"]), 1)
            self.assertEqual(int(row["unique_stations_total"]), 4)

            state = fetch_one(
                """
                SELECT last_processed_bucket_start_utc, last_error
                FROM radio_activity_aggregator_state
                WHERE key = ?
                """,
                ("radio_activity_5m.default",),
            )
            self.assertIsNotNone(state)
            assert state is not None
            self.assertEqual(str(state["last_processed_bucket_start_utc"]), bucket_start.isoformat())
            self.assertFalse(str(state["last_error"] or "").strip())

    def test_reprocessing_bucket_does_not_duplicate_rows(self) -> None:
        with temporary_database():
            bucket_start = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8ABC-9>APRS::APRS:?APRSD",
                created_at=(bucket_start + timedelta(minutes=1)).isoformat(),
            )
            run_radio_activity_aggregation(
                state_key="radio_activity.replay.a",
                now_utc=datetime(2026, 5, 4, 10, 7, tzinfo=timezone.utc),
                safety_delay_seconds=30,
            )
            run_radio_activity_aggregation(
                state_key="radio_activity.replay.b",
                now_utc=datetime(2026, 5, 4, 10, 7, tzinfo=timezone.utc),
                safety_delay_seconds=30,
            )
            count_row = fetch_one(
                """
                SELECT COUNT(*) AS total
                FROM radio_activity_5m
                WHERE bucket_start_utc = ?
                  AND source_name = 'Main TNC'
                """,
                (bucket_start.isoformat(),),
            )
            self.assertIsNotNone(count_row)
            assert count_row is not None
            self.assertEqual(int(count_row["total"]), 1)

    def test_open_bucket_is_not_aggregated(self) -> None:
        with temporary_database():
            bucket_start = datetime(2026, 5, 4, 10, 5, tzinfo=timezone.utc)
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8ABC-9>APRS::APRS:?APRSD",
                created_at=(bucket_start + timedelta(minutes=1)).isoformat(),
            )
            run_radio_activity_aggregation(
                now_utc=datetime(2026, 5, 4, 10, 7, tzinfo=timezone.utc),
                safety_delay_seconds=45,
            )
            row = fetch_one(
                """
                SELECT COUNT(*) AS total
                FROM radio_activity_5m
                WHERE bucket_start_utc = ?
                """,
                (bucket_start.isoformat(),),
            )
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(int(row["total"]), 0)

    def test_dashboard_api_returns_aggregated_series(self) -> None:
        if not FASTAPI_AVAILABLE:
            self.skipTest("fastapi is not installed in this environment")
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            bucket_start = _floor_to_bucket_start(now_utc - timedelta(minutes=10), bucket_minutes=5)
            bucket_end = bucket_start + timedelta(minutes=5)
            execute(
                """
                INSERT INTO radio_activity_5m(
                    bucket_start_utc, bucket_end_utc, interface_id, source_name,
                    rx_total, tx_total, digipeated_total, own_frames_total,
                    messages_total, queries_total, objects_total, wx_total,
                    position_total, mobile_total, fixed_total, unique_stations_total,
                    direct_heard_total, indirect_heard_total, rfonly_total, nogate_total,
                    invalid_total, parse_error_total, duplicate_total, max_hops_seen, avg_hops,
                    created_at_utc, updated_at_utc
                )
                VALUES (
                    ?, ?, 1, 'Main TNC',
                    5, 2, 1, 1,
                    3, 1, 0, 0,
                    4, 1, 2, 3,
                    2, 1, 0, 0,
                    0, 0, 0, 1, 1.0,
                    ?, ?
                )
                """,
                (bucket_start.isoformat(), bucket_end.isoformat(), now_utc.isoformat(), now_utc.isoformat()),
            )

            from fastapi.testclient import TestClient
            from app.dependencies import get_current_user
            from app.main import app
            from app.models import UserIdentity

            app.dependency_overrides[get_current_user] = lambda: UserIdentity(
                id=1,
                username="tester",
                role="admin",
                is_active=True,
            )
            try:
                client = TestClient(app)
                response = client.get("/api/dashboard/radio-activity?range=24h")
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("series", payload)
                self.assertIn("rx_total", payload["series"])
                self.assertGreaterEqual(sum(payload["series"]["rx_total"]), 5)
                self.assertEqual(payload.get("range"), "24h")

                response_7d = client.get("/api/dashboard/radio-activity?range=7d")
                self.assertEqual(response_7d.status_code, 200)
                payload_7d = response_7d.json()
                self.assertEqual(payload_7d.get("range"), "7d")
                self.assertEqual(len(payload_7d.get("labels") or []), 2016)
                self.assertEqual(
                    len(payload_7d.get("labels") or []),
                    len(payload_7d.get("bucket_starts_utc") or []),
                )

                unsupported = client.get("/api/dashboard/radio-activity?range=12h")
                self.assertEqual(unsupported.status_code, 400)
            finally:
                app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
