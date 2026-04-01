import contextlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.db import execute, fetch_one, init_db
from app.services.bulletin_scheduler import BulletinSchedulerService
from app.services.content import update_station_settings
from app.services.outbound import build_message_tnc2, claim_next_outbound_job, get_outbound_job
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


def insert_modem(*, name: str = "Test TNC", device_path: str = "127.0.0.1:9011") -> int:
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


def insert_message_record(*, message_kind: str = "group_bulletin") -> int:
    execute(
        """
        INSERT INTO bulletins(message_kind, addressee, bulletin_code, group_name, is_enabled, interval_minutes, message_text, updated_at)
        VALUES (?, '', '1', 'WX', 1, 30, 'Wind 15 km/h', '2026-01-01T00:00:00+00:00')
        """,
        (message_kind,),
    )
    row = fetch_one("SELECT id FROM bulletins ORDER BY id DESC LIMIT 1")
    assert row is not None
    return int(row["id"])


class BulletinOutboundFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_queues_message_job_with_jitter(self) -> None:
        with temporary_database():
            insert_modem()
            insert_message_record()
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

            scheduler = BulletinSchedulerService()
            baseline = datetime.now(timezone.utc).replace(microsecond=0)
            with patch("app.services.bulletin_scheduler.random.randint", return_value=6), patch(
                "app.services.bulletin_scheduler.latest_message_dispatch_at",
                return_value=baseline,
            ):
                scheduler._tick()

            row = fetch_one(
                "SELECT kind, status, scheduled_at, payload_json FROM outbound_jobs WHERE kind = 'message' ORDER BY id DESC LIMIT 1"
            )
            assert row is not None
            self.assertEqual(row["kind"], "message")
            self.assertEqual(row["status"], "queued")
            self.assertEqual(row["scheduled_at"], (baseline + timedelta(seconds=6)).isoformat())

            payload = json.loads(row["payload_json"])
            self.assertEqual(payload["message_kind"], "group_bulletin")
            self.assertEqual(payload["bulletin_code"], "1")
            self.assertEqual(payload["group_name"], "WX")
            self.assertEqual(payload["trigger"], "scheduled")

    async def test_outbound_runtime_sends_message_jobs(self) -> None:
        with temporary_database():
            insert_modem(device_path="127.0.0.1:9012")
            insert_message_record(message_kind="announcement")
            execute("UPDATE bulletins SET bulletin_code = 'A', group_name = '', message_text = 'System maintenance 19:30 UTC'")
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

            scheduler = BulletinSchedulerService()
            scheduler._tick()
            job = claim_next_outbound_job()
            assert job is not None
            self.assertEqual(job["kind"], "message")

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
                self.assertEqual(port, 9012)
                return object(), FakeWriter()

            outbound_service = OutboundService()
            with patch("app.services.outbound_runtime.asyncio.open_connection", side_effect=fake_open_connection):
                await outbound_service._process_job(job)

            row = fetch_one(
                "SELECT id, status, payload_json FROM outbound_jobs WHERE kind = 'message' ORDER BY id DESC LIMIT 1"
            )
            assert row is not None
            self.assertEqual(row["status"], "sent")
            payload = json.loads(row["payload_json"])
            self.assertEqual(payload["message_kind"], "announcement")
            self.assertNotIn("addressee", payload)

            runtime_job = get_outbound_job(int(row["id"]))
            assert runtime_job is not None
            expected_line = build_message_tnc2(runtime_job["payload"])
            self.assertTrue(written_frames)
            self.assertGreater(len(written_frames[0]), 0)

            traffic_row = fetch_one("SELECT line FROM traffic_frames ORDER BY id DESC LIMIT 1")
            assert traffic_row is not None
            self.assertEqual(traffic_row["line"], expected_line)


if __name__ == "__main__":
    unittest.main()
