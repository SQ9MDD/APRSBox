import contextlib
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import get_version
from app.db import execute, fetch_all, fetch_one, init_db, set_app_setting
from app.services.content import update_station_settings
from app.services.messages import (
    HEARD_FRESH_SECONDS,
    HEARD_WARN_SECONDS,
    MESSAGE_STATUS_ACKED,
    MESSAGE_STATUS_FAILED,
    MESSAGE_STATUS_RECEIVED,
    MESSAGE_STATUS_SENT,
    QUERY_MESSAGE_KIND,
    _format_heard_parts,
    _heard_recently_state,
    get_unread_inbox_count,
    get_messages_page_data,
    mark_conversation_read,
    normalize_aprs_message_text,
    process_incoming_tnc2_message,
    queue_outgoing_message,
    retry_failed_message,
)
from app.services.outbound import build_beacon_tnc2, build_message_tnc2, build_status_tnc2, claim_next_outbound_job
from app.services.outbound_runtime import OutboundService

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
if FASTAPI_AVAILABLE:
    from app.template_helpers import build_template_context
    from starlette.requests import Request


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


def station_payload(interface_id: int, *, ssid: str = "4") -> dict[str, str]:
    return {
        "callsign": "SQ9MDD",
        "ssid": ssid,
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

    def test_heard_recently_state_uses_expected_thresholds(self) -> None:
        self.assertEqual(_heard_recently_state(HEARD_FRESH_SECONDS), "fresh")
        self.assertEqual(_heard_recently_state(HEARD_FRESH_SECONDS + 1), "warn")
        self.assertEqual(_heard_recently_state(HEARD_WARN_SECONDS), "warn")
        self.assertEqual(_heard_recently_state(HEARD_WARN_SECONDS + 1), "stale")
        self.assertEqual(_heard_recently_state(None), "none")

    def test_format_heard_parts_returns_human_readable_timestamp_and_age(self) -> None:
        with patch("app.services.messages.datetime") as datetime_mock:
            from datetime import datetime, timezone

            datetime_mock.now.return_value = datetime(2026, 4, 1, 12, 12, 0, tzinfo=timezone.utc)
            datetime_mock.fromisoformat.side_effect = datetime.fromisoformat
            label, relative = _format_heard_parts("2026-04-01T12:00:00+00:00")

        self.assertEqual(label, "2026.04.01 12:00 UTC")
        self.assertEqual(relative, "12 minut temu")

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

    async def test_ack_for_local_ssid_zero_matches_when_remote_omits_dash_zero(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id, ssid="0"))

            message = queue_outgoing_message(callsign="SP8ABC", message_text="Test SSID 0", path="WIDE1-1")
            self.assertEqual(message["status"], "queued")
            self.assertEqual(message["message_number"], "00")

            job = claim_next_outbound_job()
            assert job is not None
            self.assertEqual(build_message_tnc2(job["payload"]), "SQ9MDD>APBOX0,WIDE1-1::SP8ABC   :Test SSID 0{00")

            class FakeWriter:
                def write(self, _data: bytes) -> None:
                    return None

                async def drain(self) -> None:
                    return None

                def close(self) -> None:
                    return None

                async def wait_closed(self) -> None:
                    return None

            async def fake_open_connection(_host: str, _port: int):
                return object(), FakeWriter()

            with patch("app.services.outbound_runtime.asyncio.open_connection", side_effect=fake_open_connection):
                await OutboundService()._process_job(job)

            ack_line = build_message_tnc2(
                {
                    "callsign": "SP8ABC",
                    "ssid": "",
                    "message_kind": "ack",
                    "addressee": "SQ9MDD",
                    "message_text": "ack00",
                }
            )
            process_incoming_tnc2_message(ack_line, timestamp="2026-01-01T00:00:15+00:00")

            acked_row = fetch_one("SELECT status, acked_at FROM aprs_messages WHERE id = ?", (int(message["id"]),))
            assert acked_row is not None
            self.assertEqual(acked_row["status"], MESSAGE_STATUS_ACKED)
            self.assertEqual(acked_row["acked_at"], "2026-01-01T00:00:15+00:00")

    def test_incoming_message_with_closed_brace_suffix_is_acked(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            inbound_line = "SQ9MDD>APQTH1,RFONLY::SQ9MDD-4 :test{02}"
            process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:01:00+00:00")

            row = fetch_one(
                """
                SELECT direction, sender, addressee, message_text, message_number, status
                FROM aprs_messages
                ORDER BY id DESC
                LIMIT 1
                """
            )
            assert row is not None
            self.assertEqual(row["direction"], "rx")
            self.assertEqual(row["sender"], "SQ9MDD")
            self.assertEqual(row["addressee"], "SQ9MDD-4")
            self.assertEqual(row["message_text"], "test")
            self.assertEqual(row["message_number"], "02")
            self.assertEqual(row["status"], MESSAGE_STATUS_RECEIVED)

            ack_jobs = fetch_all(
                """
                SELECT payload_json
                FROM outbound_jobs
                WHERE kind = 'message'
                ORDER BY id ASC
                """
            )
            self.assertEqual(len(ack_jobs), 2)
            self.assertTrue(all('"message_text":"ack02"' in str(job["payload_json"]) for job in ack_jobs))

    def test_incoming_message_with_single_char_suffix_number_is_normalized_and_acked(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            inbound_line = "SP8ABC>APRS::SQ9MDD-4 :ide na spacerek :){8"
            process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:01:00+00:00")

            row = fetch_one(
                """
                SELECT direction, sender, addressee, message_text, message_number, status
                FROM aprs_messages
                ORDER BY id DESC
                LIMIT 1
                """
            )
            assert row is not None
            self.assertEqual(row["direction"], "rx")
            self.assertEqual(row["sender"], "SP8ABC")
            self.assertEqual(row["addressee"], "SQ9MDD-4")
            self.assertEqual(row["message_text"], "ide na spacerek :)")
            self.assertEqual(row["message_number"], "08")
            self.assertEqual(row["status"], MESSAGE_STATUS_RECEIVED)

            ack_jobs = fetch_all(
                """
                SELECT payload_json
                FROM outbound_jobs
                WHERE kind = 'message'
                ORDER BY id ASC
                """
            )
            self.assertEqual(len(ack_jobs), 2)
            self.assertTrue(all('"message_text":"ack08"' in str(job["payload_json"]) for job in ack_jobs))

    def test_incoming_third_party_message_uses_inner_sender(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            inbound_line = "SR0DZ>APDW16,SR5NWA*,WIDE1*:}SQ2IBK>APRS,TCPIP,SR0DZ*::SQ9MDD-4 :relay test{34"
            process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:01:00+00:00")

            row = fetch_one(
                """
                SELECT direction, sender, addressee, message_text, message_number, status
                FROM aprs_messages
                ORDER BY id DESC
                LIMIT 1
                """
            )
            assert row is not None
            self.assertEqual(row["direction"], "rx")
            self.assertEqual(row["sender"], "SQ2IBK")
            self.assertEqual(row["addressee"], "SQ9MDD-4")
            self.assertEqual(row["message_text"], "relay test")
            self.assertEqual(row["message_number"], "34")
            self.assertEqual(row["status"], MESSAGE_STATUS_RECEIVED)

    def test_incoming_malformed_third_party_message_is_ignored(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            inbound_line = "SR0DZ>APDW16,SR5NWA*,WIDE1*:}NOT_A_VALID_FRAME"
            process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:01:00+00:00")

            row = fetch_one("SELECT COUNT(*) AS total FROM aprs_messages")
            assert row is not None
            self.assertEqual(int(row["total"]), 0)

    def test_single_char_ack_number_matches_outbound_message(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))
            set_app_setting("messages.next_message_number", "08")

            message = queue_outgoing_message(callsign="SP8ABC", message_text="Test single char ACK", path="WIDE1-1")
            self.assertEqual(message["status"], "queued")
            self.assertEqual(message["message_number"], "08")

            ack_line = build_message_tnc2(
                {
                    "callsign": "SP8ABC",
                    "ssid": "",
                    "message_kind": "ack",
                    "addressee": "SQ9MDD-4",
                    "message_text": "ack8",
                }
            )
            process_incoming_tnc2_message(ack_line, timestamp="2026-01-01T00:00:15+00:00")

            acked_row = fetch_one("SELECT status, acked_at FROM aprs_messages WHERE id = ?", (int(message["id"]),))
            assert acked_row is not None
            self.assertEqual(acked_row["status"], MESSAGE_STATUS_ACKED)
            self.assertEqual(acked_row["acked_at"], "2026-01-01T00:00:15+00:00")

    async def test_queue_send_query_without_message_number_and_retry(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            message = queue_outgoing_message(callsign="SP8ABC", message_text="?APRSP", path="WIDE1-1")
            self.assertEqual(message["status"], "queued")
            self.assertIsNone(message["message_number"])

            queued_job = fetch_one(
                """
                SELECT payload_json
                FROM outbound_jobs
                WHERE aprs_message_id = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (int(message["id"]),),
            )
            assert queued_job is not None
            self.assertIn('"message_kind":"query"', str(queued_job["payload_json"]))
            self.assertNotIn('"message_number"', str(queued_job["payload_json"]))

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

            self.assertEqual(str(job["payload"].get("message_kind")), QUERY_MESSAGE_KIND)
            self.assertEqual(build_message_tnc2(job["payload"]), "SQ9MDD-4>APBOX0,WIDE1-1::SP8ABC   :?APRSP")

            retry_job = fetch_one(
                """
                SELECT id
                FROM outbound_jobs
                WHERE aprs_message_id = ?
                  AND status = 'queued'
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(message["id"]),),
            )
            self.assertIsNone(retry_job)

    def test_incoming_message_matches_exact_local_ssid_and_persists(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            inbound_line = build_message_tnc2(
                {
                    "callsign": "SP8ABC",
                    "ssid": "",
                    "message_kind": "direct_message",
                    "addressee": "SQ9MDD-4",
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
            self.assertEqual(row["addressee"], "SQ9MDD-4")
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

    def test_incoming_message_to_other_local_ssid_is_ignored(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            inbound_line = build_message_tnc2(
                {
                    "callsign": "SP8ABC",
                    "ssid": "",
                    "message_kind": "direct_message",
                    "addressee": "SQ9MDD-2",
                    "message_text": "Should be ignored",
                    "message_number": "AA",
                }
            )
            process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:01:00+00:00")

            row = fetch_one("SELECT COUNT(*) AS total FROM aprs_messages")
            assert row is not None
            self.assertEqual(int(row["total"]), 0)

    def test_incoming_bulletin_is_visible_in_sender_conversation_without_ack_jobs(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            inbound_line = "SP5XYZ-9>APRS::BLN1     :Net starts at 19:30"
            process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:01:00+00:00")

            row = fetch_one(
                """
                SELECT m.direction, m.sender, m.addressee, m.message_text, m.message_number, m.status,
                       c.remote_callsign, c.remote_ssid
                FROM aprs_messages m
                JOIN aprs_message_conversations c ON c.id = m.conversation_id
                ORDER BY m.id DESC
                LIMIT 1
                """
            )
            assert row is not None
            self.assertEqual(row["direction"], "rx")
            self.assertEqual(row["sender"], "SP5XYZ-9")
            self.assertEqual(row["addressee"], "BLN1")
            self.assertEqual(row["message_text"], "BLN1: Net starts at 19:30")
            self.assertEqual(row["message_number"], None)
            self.assertEqual(row["status"], MESSAGE_STATUS_RECEIVED)
            self.assertEqual(row["remote_callsign"], "SP5XYZ")
            self.assertEqual(row["remote_ssid"], "9")

            jobs = fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs")
            assert jobs is not None
            self.assertEqual(int(jobs["total"]), 0)

            view = get_messages_page_data()
            self.assertEqual(len(view["conversations"]), 1)
            self.assertEqual(view["conversations"][0]["callsign"], "SP5XYZ-9")
            self.assertEqual(view["conversations"][0]["messages"][0]["text"], "BLN1: Net starts at 19:30")

            process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:06:00+00:00")
            total = fetch_one("SELECT COUNT(*) AS total FROM aprs_messages")
            assert total is not None
            self.assertEqual(int(total["total"]), 1)

    def test_incoming_announcement_is_visible_in_sender_conversation_without_ack_jobs(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            inbound_line = "SP5XYZ>APRS::BLNA     :System maintenance 19:30 UTC"
            process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:01:00+00:00")

            row = fetch_one("SELECT addressee, message_text, message_number FROM aprs_messages ORDER BY id DESC LIMIT 1")
            assert row is not None
            self.assertEqual(row["addressee"], "BLNA")
            self.assertEqual(row["message_text"], "BLNA: System maintenance 19:30 UTC")
            self.assertEqual(row["message_number"], None)

            jobs = fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs")
            assert jobs is not None
            self.assertEqual(int(jobs["total"]), 0)

    def test_incoming_aprs_query_returns_supported_query_list(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            inbound_line = build_message_tnc2(
                {
                    "callsign": "SP8ABC",
                    "ssid": "",
                    "message_kind": "query",
                    "addressee": "SQ9MDD-4",
                    "message_text": "?APRS",
                }
            )
            process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:01:00+00:00")

            job = claim_next_outbound_job()
            assert job is not None
            self.assertEqual(job["kind"], "message")
            self.assertEqual(str(job["payload"].get("message_kind")), QUERY_MESSAGE_KIND)
            self.assertEqual(
                build_message_tnc2(job["payload"]),
                "SQ9MDD-4>APBOX0,WIDE2-1::SP8ABC   :Queries: ?APRS ?APRSP ?APRSS ?APRSV ?VER",
            )

            rows = fetch_all(
                """
                SELECT direction, message_text, status
                FROM aprs_messages
                ORDER BY id ASC
                """
            )
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["direction"], "rx")
            self.assertEqual(rows[0]["message_text"], "?APRS")
            self.assertEqual(rows[1]["direction"], "tx")
            self.assertEqual(rows[1]["message_text"], "Queries: ?APRS ?APRSP ?APRSS ?APRSV ?VER")

    def test_incoming_numbered_aprs_query_is_accepted_and_shown_in_conversation(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            inbound_line = "SQ9MDD-7>APK005,RFONLY::SQ9MDD-4 :?APRS{49"
            process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:01:00+00:00")

            rows = fetch_all(
                """
                SELECT direction, message_text, message_number
                FROM aprs_messages
                ORDER BY id ASC
                """
            )
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["direction"], "rx")
            self.assertEqual(rows[0]["message_text"], "?APRS")
            self.assertEqual(rows[0]["message_number"], "49")
            self.assertEqual(rows[1]["direction"], "tx")
            self.assertEqual(rows[1]["message_text"], "Queries: ?APRS ?APRSP ?APRSS ?APRSV ?VER")

            view = get_messages_page_data()
            self.assertEqual(len(view["conversations"]), 1)
            self.assertEqual(len(view["conversations"][0]["messages"]), 2)
            self.assertEqual(view["conversations"][0]["messages"][0]["text"], "?APRS")
            self.assertEqual(view["conversations"][0]["messages"][1]["text"], "Queries: ?APRS ?APRSP ?APRSS ?APRSV ?VER")

            row = fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'message'")
            assert row is not None
            self.assertEqual(int(row["total"]), 3)

            jobs = fetch_all(
                """
                SELECT status, scheduled_at, payload_json
                FROM outbound_jobs
                WHERE kind = 'message'
                ORDER BY id ASC
                """
            )
            self.assertEqual(len(jobs), 3)
            ack_now_job = next(job for job in jobs if '"message_text":"ack49"' in str(job["payload_json"]) and '"trigger":"ack-now"' in str(job["payload_json"]))
            response_job = next(job for job in jobs if '"message_text":"Queries: ?APRS ?APRSP ?APRSS ?APRSV ?VER"' in str(job["payload_json"]))
            self.assertGreater(str(response_job["scheduled_at"]), str(ack_now_job["scheduled_at"]))

    def test_incoming_aprsp_query_queues_single_position_response(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            inbound_line = build_message_tnc2(
                {
                    "callsign": "SP8ABC",
                    "ssid": "",
                    "message_kind": "query",
                    "addressee": "SQ9MDD-4",
                    "message_text": "?APRSP",
                }
            )
            process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:01:00+00:00")

            job = claim_next_outbound_job()
            assert job is not None
            self.assertEqual(job["kind"], "beacon")
            self.assertEqual(
                build_beacon_tnc2(job["payload"]),
                "SQ9MDD-4>APBOX0,WIDE2-1:=5213.78N/02100.73E>",
            )
            rows = fetch_all("SELECT direction, message_text, status FROM aprs_messages ORDER BY id ASC")
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["message_text"], "?APRSP")
            self.assertEqual(rows[1]["message_text"], "=5213.78N/02100.73E>")

    def test_incoming_aprss_query_queues_single_status_response(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(interface_id)
            payload["status_text"] = "Station online"
            update_station_settings(payload)

            inbound_line = build_message_tnc2(
                {
                    "callsign": "SP8ABC",
                    "ssid": "",
                    "message_kind": "query",
                    "addressee": "SQ9MDD-4",
                    "message_text": "?APRSS",
                }
            )
            process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:01:00+00:00")

            job = claim_next_outbound_job()
            assert job is not None
            self.assertEqual(job["kind"], "status")
            self.assertEqual(build_status_tnc2(job["payload"]), "SQ9MDD-4>APBOX0:>Station online")
            rows = fetch_all("SELECT direction, message_text, status FROM aprs_messages ORDER BY id ASC")
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["message_text"], "?APRSS")
            self.assertEqual(rows[1]["message_text"], ">Station online")

    def test_incoming_version_queries_return_single_text_response(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            for query_text in ("?APRSV", "?VER"):
                inbound_line = build_message_tnc2(
                    {
                        "callsign": "SP8ABC",
                        "ssid": "",
                        "message_kind": "query",
                        "addressee": "SQ9MDD-4",
                        "message_text": query_text,
                    }
                )
                process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:01:00+00:00")

            jobs = fetch_all(
                """
                SELECT id
                FROM outbound_jobs
                WHERE kind = 'message'
                ORDER BY id ASC
                """
            )
            self.assertEqual(len(jobs), 2)

            first_job = claim_next_outbound_job()
            second_job = claim_next_outbound_job()
            assert first_job is not None
            assert second_job is not None
            expected_line = f"SQ9MDD-4>APBOX0,WIDE2-1::SP8ABC   :APRSBox {get_version()}"
            self.assertEqual(build_message_tnc2(first_job["payload"]), expected_line)
            self.assertEqual(build_message_tnc2(second_job["payload"]), expected_line)
            rows = fetch_all("SELECT direction, message_text FROM aprs_messages ORDER BY id ASC")
            self.assertEqual(len(rows), 4)

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

    @unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is required for template helper rendering tests")
    def test_sidebar_messages_icon_switches_when_inbox_has_unread_messages(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))

            inbound_line = build_message_tnc2(
                {
                    "callsign": "SP8ABC",
                    "ssid": "",
                    "message_kind": "direct_message",
                    "addressee": "SQ9MDD-4",
                    "message_text": "Unread test",
                    "message_number": "AA",
                }
            )
            process_incoming_tnc2_message(inbound_line, timestamp="2026-01-01T00:01:00+00:00")

            self.assertEqual(get_unread_inbox_count(), 1)

            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/dashboard",
                    "root_path": "",
                    "headers": [],
                    "query_string": b"",
                    "client": ("127.0.0.1", 12345),
                    "server": ("testserver", 80),
                    "scheme": "http",
                }
            )
            current_user = SimpleNamespace(role="admin", username="admin")

            context = build_template_context(request, page_title="Dashboard", current_user=current_user, active_nav="dashboard")
            messages_item = next(item for item in context["navigation"] if item.get("key") == "messages")
            self.assertEqual(messages_item["icon"], "message-alert-outline.svg")

            conversation = fetch_one("SELECT id FROM aprs_message_conversations ORDER BY id ASC LIMIT 1")
            assert conversation is not None
            mark_conversation_read(int(conversation["id"]))

            self.assertEqual(get_unread_inbox_count(), 0)

            context = build_template_context(request, page_title="Dashboard", current_user=current_user, active_nav="dashboard")
            messages_item = next(item for item in context["navigation"] if item.get("key") == "messages")
            self.assertEqual(messages_item["icon"], "message-reply-text-outline.svg")

    def test_messages_page_data_exposes_heard_recently_state(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id))
            queue_outgoing_message(callsign="DL1XYZ-9", message_text="QSL", path="")
            execute(
                """
                INSERT INTO traffic_frames(source, format, line, port, command, length, hex, created_at)
                VALUES (?, 'TNC2', ?, '', '', ?, '', ?)
                """,
                (
                    "DL1XYZ-9",
                    "DL1XYZ-9>APRS:>status",
                    len("DL1XYZ-9>APRS:>status"),
                    "2099-01-01T00:00:00+00:00",
                ),
            )

            with patch("app.services.messages._heard_age_seconds", return_value=12 * 60):
                view = get_messages_page_data()

            conversation = view["conversations"][0]
            self.assertTrue(conversation["recently_heard"])
            self.assertEqual(conversation["heard_recently_state"], "warn")
            self.assertIn("(", conversation["heard_recently_label"])
            self.assertIn(")", conversation["heard_recently_label"])

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
