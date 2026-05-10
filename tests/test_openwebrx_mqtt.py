import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, fetch_one, init_db, utc_now
from app.services.mqtt_url import OPENWEBRX_MQTT_MODEM_TYPE, mask_mqtt_url, parse_mqtt_url
from app.services.outbound import build_tnc2_kiss_frame
from app.services.content import get_section_row, safe_create_section_row
from app.services.traffic import _TrafficModemRuntime


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


def insert_openwebrx_modem(*, name: str = "OWRX-1", device_path: str = "mqtt://127.0.0.1:1883/rxqwe/APRS") -> int:
    execute(
        """
        INSERT INTO modems(name, modem_type, band, device_path, enabled, tx_blocked, notes, created_at, updated_at)
        VALUES (?, ?, '2m', ?, 1, 1, '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (name, OPENWEBRX_MQTT_MODEM_TYPE, device_path),
    )
    row = fetch_one("SELECT id FROM modems WHERE name = ?", (name,))
    assert row is not None
    return int(row["id"])


def build_openwebrx_raw_hex(tnc2_line: str) -> str:
    kiss_frame = build_tnc2_kiss_frame(tnc2_line)
    escaped_payload = kiss_frame[2:-1]
    runtime = _TrafficModemRuntime()
    payload = runtime._kiss_unescape(escaped_payload)
    return payload.hex().upper()


class OpenWebRxMqttUrlTests(unittest.TestCase):
    def test_parse_mqtt_url_without_credentials(self) -> None:
        endpoint = parse_mqtt_url("mqtt://host:1883/rxqwe/APRS")
        self.assertEqual(endpoint.scheme, "mqtt")
        self.assertEqual(endpoint.host, "host")
        self.assertEqual(endpoint.port, 1883)
        self.assertEqual(endpoint.topic, "rxqwe/APRS")
        self.assertIsNone(endpoint.username)
        self.assertIsNone(endpoint.password)

    def test_parse_mqtt_url_with_credentials(self) -> None:
        endpoint = parse_mqtt_url("mqtt://user:pass@host:1883/rxqwe/APRS")
        self.assertEqual(endpoint.scheme, "mqtt")
        self.assertEqual(endpoint.username, "user")
        self.assertEqual(endpoint.password, "pass")
        self.assertEqual(endpoint.masked_url, "mqtt://user:***@host:1883/rxqwe/APRS")

    def test_parse_mqtts_url_with_credentials(self) -> None:
        endpoint = parse_mqtt_url("mqtts://user:pass@host:8883/rxqwe/APRS")
        self.assertEqual(endpoint.scheme, "mqtts")
        self.assertTrue(endpoint.use_tls)
        self.assertEqual(endpoint.port, 8883)
        self.assertEqual(endpoint.topic, "rxqwe/APRS")

    def test_mask_mqtt_url_masks_password(self) -> None:
        masked = mask_mqtt_url("mqtt://user:pass@host:1883/rxqwe/APRS")
        self.assertEqual(masked, "mqtt://user:***@host:1883/rxqwe/APRS")

    def test_modem_row_masks_password_in_ui_value(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "modems",
                {
                    "name": "OWRX-UI",
                    "band": "2m",
                    "modem_type": "OPENWEBRX_MQTT",
                    "device_path": "mqtt://user:pass@host:1883/rxqwe/APRS",
                    "enabled": "1",
                    "tx_min_gap_seconds": "0.35",
                    "serial_rx_silence_reconnect_seconds": "150",
                },
            )
            self.assertTrue(success, error)
            row = get_section_row("modems", 1)
            assert row is not None
            self.assertEqual(row["device_path"], "mqtt://user:***@host:1883/rxqwe/APRS")


class OpenWebRxMqttPayloadTests(unittest.TestCase):
    def test_maps_openwebrx_json_to_tnc2_using_raw_hex(self) -> None:
        source_line = "SP5CWC>URQS52,SR5NWA*,WIDE1*,WIDE2-1:>OpenWebRX frame"
        raw_hex = build_openwebrx_raw_hex(source_line)
        packet = {
            "source": "SP5CWC",
            "destination": "URQS52",
            "path": ["SR5NWA*", "WIDE1*", "WIDE2-1"],
            "raw": raw_hex,
            "mode": "APRS",
            "freq": 144800000,
            "comment": "OpenWebRX frame",
        }

        runtime = _TrafficModemRuntime()
        line, diagnostic_hex = runtime._map_openwebrx_packet_to_tnc2_line(packet, json.dumps(packet))

        self.assertIsNotNone(line)
        assert line is not None
        self.assertIn("SP5CWC > URQS52", line)
        self.assertIn("WIDE2-1", line)
        self.assertIn("OpenWebRX frame", line)
        self.assertTrue(bool(diagnostic_hex))

    def test_invalid_json_payload_increments_dropped_counter(self) -> None:
        with temporary_database():
            modem_id = insert_openwebrx_modem()
            modem = fetch_one("SELECT * FROM modems WHERE id = ?", (modem_id,))
            assert modem is not None
            runtime = _TrafficModemRuntime(modem_id=modem_id)
            runtime._set_state(status="connected", detail="test", modem=dict(modem), error=None)

            runtime._record_openwebrx_mqtt_message(
                modem=dict(modem),
                topic="/rxqwe/APRS",
                payload_text="{broken-json",
                received_monotonic=10.0,
                received_at=utc_now(),
            )

            snapshot = runtime.runtime_snapshot()
            mqtt_stats = dict(snapshot.get("mqtt_stats") or {})
            self.assertEqual(int(mqtt_stats.get("invalid_json_dropped") or 0), 1)
            frame_count_row = fetch_one("SELECT COUNT(*) AS total FROM traffic_frames")
            assert frame_count_row is not None
            self.assertEqual(int(frame_count_row["total"]), 0)

    def test_duplicate_frames_are_dropped_within_three_second_window(self) -> None:
        with temporary_database():
            modem_id = insert_openwebrx_modem()
            modem = fetch_one("SELECT * FROM modems WHERE id = ?", (modem_id,))
            assert modem is not None
            runtime = _TrafficModemRuntime(modem_id=modem_id)
            runtime._set_state(status="connected", detail="test", modem=dict(modem), error=None)

            source_line = "SP5CWC>URQS52,SR5NWA*,WIDE1*,WIDE2-1:>OpenWebRX frame"
            raw_hex = build_openwebrx_raw_hex(source_line)
            payload = json.dumps(
                {
                    "source": "SP5CWC",
                    "destination": "URQS52",
                    "path": ["SR5NWA*", "WIDE1*", "WIDE2-1"],
                    "raw": raw_hex,
                    "mode": "APRS",
                    "freq": 144800000,
                }
            )

            runtime._record_openwebrx_mqtt_message(
                modem=dict(modem),
                topic="/rxqwe/APRS",
                payload_text=payload,
                received_monotonic=10.0,
                received_at=utc_now(),
            )
            runtime._record_openwebrx_mqtt_message(
                modem=dict(modem),
                topic="/rxqwe/APRS",
                payload_text=payload,
                received_monotonic=12.0,
                received_at=utc_now(),
            )

            frame_count_row = fetch_one("SELECT COUNT(*) AS total FROM traffic_frames")
            assert frame_count_row is not None
            self.assertEqual(int(frame_count_row["total"]), 1)

            snapshot = runtime.runtime_snapshot()
            mqtt_stats = dict(snapshot.get("mqtt_stats") or {})
            self.assertEqual(int(mqtt_stats.get("frames_received") or 0), 2)
            self.assertEqual(int(mqtt_stats.get("duplicates_dropped") or 0), 1)
