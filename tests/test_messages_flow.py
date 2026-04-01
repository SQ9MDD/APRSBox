import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import execute, fetch_all, fetch_one, init_db
from app.services.content import update_station_settings
from app.services.messages import (
    MESSAGE_STATUS_ACKED,
    MESSAGE_STATUS_FAILED,
    MESSAGE_STATUS_RECEIVED,
    MESSAGE_STATUS_SENT,
    get_messages_page_data,
    normalize_aprs_message_text,
    process_incoming_tnc2_message,
    queue_outgoing_message,
    retry_failed_message,
)
from app.services.outbound import build_message_tnc2, claim_next_outbound_job
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


def insert_modem(*, name: str = "Test TNC", device_path: str = "127.0.0.1:9201") -> int:
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


def station_payload(interface_id: int) -> dict[str, str]:
    return {
        "callsign": "SQ9MDD",
        "ssid": "4",
        "beacon_interface_id": str(interface_id),
        "beacon_comment": "",
        "beacon_interval_minutes": "30",
        "beacon_path": "WIDE2-1",
        "latitude": "52.2297",
        "longitude": "21.0122",
        "symbol_table": "/",
        "symbol_code": ">",
        "default_units": "metric",
    }


class MessagesFlowTests(unittest.IsolatedAsyncioTestCase):
    def test_message_text_allows_extended_printable_ascii_punctuation(self) -> None:
        allowed = r''',.:?/\()<>-_+=[]{}"'&$@#!'''
        self.assertEqual(normalize_aprs_message_text(allowed), allowed)

    async def test_queue_send_and_ack_direct_message(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            message = queue_outgoing_message(callsign="SP8ABC", message_text="Test direct message", path="WIDE1-1")
            self.assertEqual(message["status"], "queued")
            self.assertEqual(message["message_number"], "00")

            conversation_row = fetch_one("SELECT remote_callsign, remote_ssid, path FROM aprs_message_conversations")
            assert conversation_row is not None
            self.assertEqual(conversation_row["remote_callsign"], "SP8ABC")
            self.assertEqual(conversation_row["remote_ssid"], "")
            self.assertEqual(conversation_row["path"], "WIDE1-1")

            queued_job = fetch_one(
                """
                SELECT kind, status, aprs_message_id
                FROM outbound_jobs
                WHERE aprs_message_id = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (int(message["id"]),),
            )
            assert queued_job is not None
            self.assertEqual(queued_job["kind"], "message")
            self.assertEqual(queued_job["status"], "queued")

            job = claim_next_outbound_job()
            assert job is not None
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
                self.assertEqual(port, 9201)
                return object(), FakeWriter()

            with patch("app.services.outbound_runtime.asyncio.open_connection", side_effect=fake_open_connection):
                await OutboundService()._process_job(job)

            message_row = fetch_one(
                """
                SELECT status, tx_attempt_count
                FROM aprs_messages
                WHERE id = ?
                """,
                (int(message["id"]),),
            )
            assert message_row is not None
            self.assertEqual(message_row["status"], MESSAGE_STATUS_SENT)
            self.assertEqual(int(message_row["tx_attempt_count"]), 1)
            self.assertTrue(written_frames)

            retry_job = fetch_one(
                """
                SELECT id, status
                FROM outbound_jobs
                WHERE aprs_message_id = ?
                  AND status = 'queued'
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(message["id"]),),
            )
            assert retry_job is not None

            ack_line = build_message_tnc2(
                {
                    "callsign": "SP8ABC",
                    "ssid": "",
                    "message_kind": "ack",
                    "addressee": "SQ9MDD-4",
                    "message_text": "ack00",
                }
            )
            process_incoming_tnc2_message(ack_line, timestamp="2026-01-01T00:00:15+00:00")

            acked_row = fetch_one("SELECT status, acked_at FROM aprs_messages WHERE id = ?", (int(message["id"]),))
            assert acked_row is not None
            self.assertEqual(acked_row["status"], MESSAGE_STATUS_ACKED)
            self.assertEqual(acked_row["acked_at"], "2026-01-01T00:00:15+00:00")

            cancelled_retry = fetch_one("SELECT status FROM outbound_jobs WHERE id = ?", (int(retry_job["id"]),))
            assert cancelled_retry is not None
            self.assertEqual(cancelled_retry["status"], "cancelled")

    def test_incoming_message_matches_local_ssid_family_and_persists(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            inbound_line = build_message_tnc2(
                {
                    "callsign": "SP8ABC",
                    "ssid": "",
                    "message_kind": "direct_message",
                    "addressee": "SQ9MDD-2",
                    "message_text": "Inbound test",
                    "message_number": "AA",
                }
            )
            process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:01:00+00:00")

            row = fetch_one(
                """
                SELECT m.direction, m.addressee, m.message_text, m.message_number, m.status, c.remote_callsign, c.remote_ssid
                FROM aprs_messages m
                JOIN aprs_message_conversations c ON c.id = m.conversation_id
                ORDER BY m.id DESC
                LIMIT 1
                """
            )
            assert row is not None
            self.assertEqual(row["direction"], "rx")
            self.assertEqual(row["addressee"], "SQ9MDD-2")
            self.assertEqual(row["message_text"], "Inbound test")
            self.assertEqual(row["message_number"], "AA")
            self.assertEqual(row["status"], MESSAGE_STATUS_RECEIVED)
            self.assertEqual(row["remote_callsign"], "SP8ABC")
            self.assertEqual(row["remote_ssid"], "")

            ack_jobs = fetch_all(
                """
                SELECT status, payload_json
                FROM outbound_jobs
                WHERE kind = 'message'
                ORDER BY id ASC
                """
            )
            self.assertEqual(len(ack_jobs), 2)

    def test_messages_page_data_uses_persisted_rows(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))
            queue_outgoing_message(callsign="DL1XYZ-9", message_text="QSL", path="")

            view = get_messages_page_data()
            self.assertEqual(len(view["conversations"]), 1)
            conversation = view["conversations"][0]
            self.assertEqual(conversation["callsign"], "DL1XYZ-9")
            self.assertEqual(conversation["messages"][0]["text"], "QSL")
            self.assertEqual(conversation["messages"][0]["delivery_state"], "queued")

    def test_local_echo_to_another_local_ssid_is_not_shown_as_incoming_self_conversation(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            local_echo_line = build_message_tnc2(
                {
                    "callsign": "SQ9MDD",
                    "ssid": "4",
                    "message_kind": "direct_message",
                    "addressee": "SQ9MDD-7",
                    "message_text": "Echo should be ignored",
                    "message_number": "AB",
                }
            )
            process_incoming_tnc2_message(local_echo_line, timestamp="2026-01-01T00:02:00+00:00")

            message_count = fetch_one("SELECT COUNT(*) AS total FROM aprs_messages")
            assert message_count is not None
            self.assertEqual(int(message_count["total"]), 0)

            view = get_messages_page_data()
            self.assertEqual(view["conversations"], [])

    def test_retry_failed_message_requeues_same_record(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))
            message = queue_outgoing_message(callsign="SP8ABC", message_text="Retry me", path="WIDE1-1")

            execute(
                """
                UPDATE aprs_messages
                SET status = ?, tx_attempt_count = 4, failed_at = '2026-01-01T00:10:00+00:00', failure_reason = 'No ACK', updated_at = '2026-01-01T00:10:00+00:00'
                WHERE id = ?
                """,
                (MESSAGE_STATUS_FAILED, int(message["id"])),
            )
            execute("DELETE FROM outbound_jobs WHERE aprs_message_id = ?", (int(message["id"]),))

            retried = retry_failed_message(int(message["id"]))
            self.assertEqual(retried["status"], "queued")
            self.assertEqual(int(retried["tx_attempt_count"]), 0)

            queued_job = fetch_one(
                """
                SELECT status
                FROM outbound_jobs
                WHERE aprs_message_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(message["id"]),),
            )
            assert queued_job is not None
            self.assertEqual(queued_job["status"], "queued")


if __name__ == "__main__":
    unittest.main()
