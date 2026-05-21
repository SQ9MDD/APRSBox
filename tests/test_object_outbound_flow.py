import contextlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.db import execute, fetch_one, init_db
from app.services.content import update_station_settings
from app.services.object_scheduler import ObjectSchedulerService
from app.services.outbound import claim_next_outbound_job, get_outbound_job
from app.services.outbound_runtime import OutboundService


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


def insert_modem(*, name: str = "Test TNC", device_path: str = "127.0.0.1:9001") -> int:
    execute(
        """
        INSERT INTO modems(name, modem_type, band, device_path, enabled, notes, created_at, updated_at)
        VALUES (?, 'TCP', '2m', ?, 1, '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (name, device_path),
    )
    row = fetch_one("SELECT id FROM modems WHERE name = ?", (name,))
    assert row is not None
    return int(row["id"])


def insert_object(
    *,
    lifetime: str = "temporary",
    interval_minutes: int = 30,
    valid_until_utc: str | None = None,
    symbol_table: str = "/",
    symbol_code: str = "I",
    symbol_overlay: str | None = None,
) -> int:
    execute(
        """
        INSERT INTO aprs_objects(
            name, lifetime, state, is_enabled, interval_minutes, latitude, longitude,
            valid_until_utc, symbol_table, symbol_code, symbol_overlay, path, comment, updated_at
        )
        VALUES (?, ?, 'live', 1, ?, '52.2501', '20.9268', ?, ?, ?, ?, 'WIDE2-2', 'http://hamspirit.pl:14501 Server T2', '2026-01-01T00:00:00+00:00')
        """,
        ("T2WARSPL", lifetime, interval_minutes, valid_until_utc, symbol_table, symbol_code, symbol_overlay),
    )
    row = fetch_one("SELECT id FROM aprs_objects WHERE name = ?", ("T2WARSPL",))
    assert row is not None
    return int(row["id"])


class ObjectOutboundFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_object_scheduler_queues_object_job_with_jitter(self) -> None:
        with temporary_database():
            insert_modem()
            insert_object(lifetime="permanent", interval_minutes=45)
            update_station_settings(
                {
                    "callsign": "SQ9MDD",
                    "ssid": "4",
                    "beacon_interface_id": "1",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "latitude": "52.2501",
                    "longitude": "20.9268",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": None,
                }
            )
            scheduler = ObjectSchedulerService()
            baseline = datetime.now(timezone.utc).replace(microsecond=0)
            with patch("app.services.object_scheduler.random.randint", return_value=7), patch(
                "app.services.object_scheduler.latest_object_dispatch_at",
                return_value=baseline,
            ):
                scheduler._tick()

            row = fetch_one(
                "SELECT kind, status, scheduled_at, payload_json FROM outbound_jobs WHERE kind = 'object' ORDER BY id DESC LIMIT 1"
            )
            assert row is not None
            self.assertEqual(row["kind"], "object")
            self.assertEqual(row["status"], "queued")
            self.assertEqual(row["scheduled_at"], (baseline + timedelta(seconds=7)).isoformat())

            payload = json.loads(row["payload_json"])
            self.assertEqual(payload["object_id"], 1)
            self.assertEqual(payload["object_timestamp"], "111111z")
            self.assertEqual(payload["trigger"], "scheduled")
            self.assertIsNone(payload["symbol_overlay"])

    async def test_outbound_runtime_sends_object_jobs(self) -> None:
        with temporary_database():
            insert_modem()
            insert_object(lifetime="permanent", interval_minutes=30)
            update_station_settings(
                {
                    "callsign": "SQ9MDD",
                    "ssid": "4",
                    "beacon_interface_id": "1",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "latitude": "52.2501",
                    "longitude": "20.9268",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": None,
                }
            )

            scheduler = ObjectSchedulerService()
            scheduler._tick()
            job = claim_next_outbound_job()
            assert job is not None
            self.assertEqual(job["kind"], "object")

            written_frames: list[bytes] = []

            class FakeWriter:
                def write(self, data: bytes) -> None:
                    written_frames.append(data)

                async def drain(self) -> None:
                    return None

                def close(self) -> None:
                    return None

                async def wait_closed(self) -> None:
                    return None

            async def fake_open_connection(host: str, port: int):
                self.assertEqual(host, "127.0.0.1")
                self.assertEqual(port, 9001)
                return object(), FakeWriter()

            outbound_service = OutboundService()
            with patch("app.services.outbound_runtime.asyncio.open_connection", side_effect=fake_open_connection):
                await outbound_service._process_job(job)

            row = fetch_one(
                "SELECT id, status, payload_json FROM outbound_jobs WHERE kind = 'object' ORDER BY id DESC LIMIT 1"
            )
            assert row is not None
            self.assertEqual(row["status"], "sent")
            payload = json.loads(row["payload_json"])
            self.assertEqual(payload["object_timestamp"], "111111z")

            runtime_job = get_outbound_job(int(row["id"]))
            assert runtime_job is not None
            self.assertTrue(written_frames)
            traffic_row = fetch_one("SELECT line FROM traffic_frames ORDER BY id DESC LIMIT 1")
            assert traffic_row is not None
            self.assertIn(";T2WARSPL *111111z", traffic_row["line"])

    async def test_outbound_runtime_applies_overlay_for_alternate_object_symbol(self) -> None:
        with temporary_database():
            insert_modem()
            insert_object(
                lifetime="permanent",
                interval_minutes=30,
                symbol_table="\\",
                symbol_code="A",
                symbol_overlay="3",
            )
            update_station_settings(
                {
                    "callsign": "SQ9MDD",
                    "ssid": "4",
                    "beacon_interface_id": "1",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "latitude": "52.2501",
                    "longitude": "20.9268",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": None,
                }
            )

            scheduler = ObjectSchedulerService()
            scheduler._tick()
            job = claim_next_outbound_job()
            assert job is not None

            class FakeWriter:
                def write(self, data: bytes) -> None:
                    _ = data

                async def drain(self) -> None:
                    return None

                def close(self) -> None:
                    return None

                async def wait_closed(self) -> None:
                    return None

            async def fake_open_connection(host: str, port: int):
                self.assertEqual(host, "127.0.0.1")
                self.assertEqual(port, 9001)
                return object(), FakeWriter()

            outbound_service = OutboundService()
            with patch("app.services.outbound_runtime.asyncio.open_connection", side_effect=fake_open_connection):
                await outbound_service._process_job(job)

            traffic_row = fetch_one("SELECT line FROM traffic_frames ORDER BY id DESC LIMIT 1")
            assert traffic_row is not None
            self.assertIn("5215.01N302055.61EA", str(traffic_row["line"]))

    async def test_object_scheduler_disables_expired_object_without_queueing(self) -> None:
        with temporary_database():
            object_id = insert_object(valid_until_utc="2000-01-01 00:00")
            insert_modem()
            update_station_settings(
                {
                    "callsign": "SQ9MDD",
                    "ssid": "4",
                    "beacon_interface_id": "1",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "latitude": "52.2501",
                    "longitude": "20.9268",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": None,
                }
            )
            scheduler = ObjectSchedulerService()
            scheduler._tick()

            queued_job = fetch_one("SELECT id FROM outbound_jobs WHERE kind = 'object' ORDER BY id DESC LIMIT 1")
            self.assertIsNone(queued_job)
            row = fetch_one("SELECT is_enabled FROM aprs_objects WHERE id = ?", (object_id,))
            assert row is not None
            self.assertEqual(int(row["is_enabled"]), 0)

    async def test_outbound_runtime_skips_expired_object_job_and_disables_source(self) -> None:
        with temporary_database():
            insert_modem(device_path="127.0.0.1:9003")
            object_id = insert_object(lifetime="permanent", interval_minutes=30, valid_until_utc="2099-12-31 23:59")
            update_station_settings(
                {
                    "callsign": "SQ9MDD",
                    "ssid": "4",
                    "beacon_interface_id": "1",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "latitude": "52.2501",
                    "longitude": "20.9268",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": None,
                }
            )

            scheduler = ObjectSchedulerService()
            scheduler._tick()
            job = claim_next_outbound_job()
            assert job is not None
            execute("UPDATE aprs_objects SET valid_until_utc = '2000-01-01 00:00', is_enabled = 1 WHERE id = ?", (object_id,))

            outbound_service = OutboundService()
            with patch("app.services.outbound_runtime.asyncio.open_connection") as open_connection_mock:
                await outbound_service._process_job(job)

            open_connection_mock.assert_not_called()
            job_row = fetch_one("SELECT status, last_error FROM outbound_jobs WHERE id = ?", (int(job["id"]),))
            assert job_row is not None
            self.assertEqual(job_row["status"], "sent")
            self.assertIn("expired on 2000-01-01 00:00 UTC", str(job_row["last_error"]))
            source_row = fetch_one("SELECT is_enabled FROM aprs_objects WHERE id = ?", (object_id,))
            assert source_row is not None
            self.assertEqual(int(source_row["is_enabled"]), 0)


if __name__ == "__main__":
    unittest.main()
