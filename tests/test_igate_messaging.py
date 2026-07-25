import asyncio
import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, fetch_one, init_db, utc_now
from app.services.aprsis_rf import APRSIS_FLOW_SOURCE_KIND, get_aprsis_rf_stats
from app.services.content import parse_tnc2_frame
from app.services.digi_flow_runtime import DigiFlowRuntimeService
from app.services.digi_flows import (
    create_digi_flow,
    get_digi_flow_execution_summaries,
    set_digi_flow_enabled,
)
from app.services.igate_messaging import (
    evaluate_message_delivery,
    message_return_capable_for_rf_source,
    prune_igate_runtime_state,
    record_aprsis_station_presence,
    record_rf_heard_station,
)
from app.services.messages import queue_outgoing_message
from app.services.outbound import claim_next_outbound_job
from app.services.outbound_runtime import OutboundService
from app.services.traffic import process_normalized_tnc2_rx


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


def insert_interface(name: str, modem_type: str) -> int:
    execute(
        """
        INSERT INTO modems(
            name, modem_type, band, device_path, enabled, tx_blocked,
            notes, created_at, updated_at
        )
        VALUES (?, ?, '2m', ?, 1, 0, '', '2026-07-23T12:00:00+00:00', '2026-07-23T12:00:00+00:00')
        """,
        (name, modem_type, "127.0.0.1:9001" if modem_type == "TCP" else "m/20"),
    )
    row = fetch_one("SELECT id FROM modems WHERE name = ?", (name,))
    assert row is not None
    return int(row["id"])


def set_station_identity() -> None:
    execute(
        """
        UPDATE station_settings
        SET callsign = 'SQ9MDD', ssid = '4',
            latitude = '52.2297', longitude = '21.0122',
            updated_at = '2026-07-23T12:00:00+00:00'
        WHERE id = 1
        """
    )


def return_flow_payload(*, target: str = "RF-OUT", enabled: int = 1) -> dict:
    return {
        "name": "APRS-IS messages to RF",
        "description": "",
        "source_kind": APRSIS_FLOW_SOURCE_KIND,
        "source_ref": "APRSIS-RX",
        "target_kind": "tx_rf",
        "target_ref": target,
        "enabled": enabled,
        "steps": [
            {
                "step_type": APRSIS_FLOW_SOURCE_KIND,
                "title": "Receiver APRS-IS",
                "enabled": 1,
                "config": {"aprsis_source": "APRSIS-RX"},
            },
            {
                "step_type": "filter_rf_guard",
                "title": "APRS-IS Input Safety Rule",
                "enabled": 1,
                "config": {},
            },
            {
                "step_type": "filter_aprsis_message_delivery",
                "title": "APRS-IS Message Delivery Rule",
                "enabled": 1,
                "config": {},
            },
            {
                "step_type": "filter_allow_rules",
                "title": "APRS-IS Callsign and Radius Rule",
                "enabled": 1,
                "config": {"callsigns": [], "radius_km": ""},
            },
            {
                "step_type": "filter_rf_tx_guard",
                "title": "APRS-IS to RF TX Safety Rule",
                "enabled": 1,
                "config": {
                    "viscous_delay_sec": 5,
                    "flow_rate_per_minute": 6,
                    "flow_burst": 3,
                    "source_rate_per_minute": 2,
                    "source_burst": 2,
                    "duplicate_window_sec": 30,
                },
            },
            {
                "step_type": "tx_rf",
                "title": "TX RF",
                "enabled": 1,
                "config": {"rf_target": target, "rf_path": ""},
            },
        ],
    }


def rf_to_aprsis_flow_payload() -> dict:
    return {
        "name": "RF to APRS-IS",
        "description": "",
        "source_kind": "receiver_rf",
        "source_ref": "RF-OUT",
        "target_kind": "tx_aprsis",
        "target_ref": "aprsis",
        "enabled": 1,
        "steps": [
            {
                "step_type": "receiver_rf",
                "title": "Receiver RF",
                "enabled": 1,
                "config": {"rf_port": "RF-OUT"},
            },
            {
                "step_type": "filter_strict",
                "title": "APRS-IS Uplink Safety Rule",
                "enabled": 1,
                "config": {},
            },
            {
                "step_type": "tx_aprsis",
                "title": "TX APRS-IS",
                "enabled": 1,
                "config": {"aprsis_target": "aprsis"},
            },
        ],
    }


def local_tx_to_aprsis_flow_payload() -> dict:
    return {
        "name": "Local TX to APRS-IS",
        "description": "",
        "source_kind": "receiver_local_tx",
        "source_ref": "local_tx",
        "target_kind": "tx_aprsis",
        "target_ref": "aprsis",
        "enabled": 1,
        "steps": [
            {
                "step_type": "receiver_local_tx",
                "title": "Local TX",
                "enabled": 1,
                "config": {"local_tx_source": "local_tx"},
            },
            {
                "step_type": "filter_strict",
                "title": "APRS-IS Uplink Safety Rule",
                "enabled": 1,
                "config": {},
            },
            {
                "step_type": "tx_aprsis",
                "title": "TX APRS-IS",
                "enabled": 1,
                "config": {"aprsis_target": "aprsis"},
            },
        ],
    }


class IgateMessagingPolicyTests(unittest.TestCase):
    def test_exact_local_recipient_is_authorized_but_other_ssid_is_not(self) -> None:
        with temporary_database():
            set_station_identity()
            insert_interface("RF-OUT", "TCP")
            interface_id = insert_interface("RF-AUX", "SERIAL")
            heard = parse_tnc2_frame("SQ9MDD-7>APRS:>local")
            assert heard is not None
            record_rf_heard_station(
                heard,
                interface_id=interface_id,
                timestamp="2026-07-23T13:00:00+00:00",
            )

            exact = evaluate_message_delivery(
                parse_tnc2_frame("SP5ABC>APRS,TCPIP*,qAC,SERVER::SQ9MDD-7:hello{42"),
                flow_id=1,
                local_igate="SQ9MDD-4",
                now=_dt("2026-07-23T13:10:00+00:00"),
            )
            other_ssid = evaluate_message_delivery(
                parse_tnc2_frame("SP5ABC>APRS,TCPIP*,qAC,SERVER::SQ9MDD-1:hello{43"),
                flow_id=1,
                local_igate="SQ9MDD-4",
                now=_dt("2026-07-23T13:10:00+00:00"),
            )
            self.assertEqual(exact["route"], "message")
            self.assertEqual(exact["recipient"], "SQ9MDD-7")
            self.assertEqual(other_ssid["route"], "drop")
            self.assertEqual(other_ssid["reason"], "message_recipient_not_heard_rf")

            execute("UPDATE modems SET tx_blocked = 1 WHERE id = ?", (interface_id,))
            blocked_interface = evaluate_message_delivery(
                parse_tnc2_frame("SP5ABC>APRS,TCPIP*,qAC,SERVER::SQ9MDD-7:hello{44"),
                flow_id=1,
                local_igate="SQ9MDD-4",
                now=_dt("2026-07-23T13:10:00+00:00"),
            )
            self.assertEqual(blocked_interface["route"], "drop")
            self.assertEqual(
                blocked_interface["reason"],
                "message_recipient_not_heard_rf",
            )

            execute("UPDATE modems SET tx_blocked = 0 WHERE id = ?", (interface_id,))
            indirect = parse_tnc2_frame("SQ9MDD-7>APRS,WIDE1-1*:>local through digi")
            assert indirect is not None
            record_rf_heard_station(
                indirect,
                interface_id=interface_id,
                timestamp="2026-07-23T13:01:00+00:00",
            )
            indirect_recipient = evaluate_message_delivery(
                parse_tnc2_frame("SP5ABC>APRS,TCPIP*,qAC,SERVER::SQ9MDD-7:hello{45"),
                flow_id=1,
                local_igate="SQ9MDD-4",
                now=_dt("2026-07-23T13:10:00+00:00"),
            )
            self.assertEqual(indirect_recipient["route"], "drop")
            self.assertEqual(
                indirect_recipient["reason"],
                "message_recipient_not_heard_rf",
            )

    def test_recipient_seen_as_direct_internet_station_is_rejected(self) -> None:
        with temporary_database():
            interface_id = insert_interface("RF-OUT", "TCP")
            heard = parse_tnc2_frame("SQ9MDD-7>APRS:>local")
            internet = parse_tnc2_frame("SQ9MDD-7>APRS,TCPIP*,qAC,SERVER:>online")
            assert heard is not None and internet is not None
            record_rf_heard_station(
                heard,
                interface_id=interface_id,
                timestamp="2026-07-23T13:00:00+00:00",
            )
            record_aprsis_station_presence(
                internet,
                timestamp="2026-07-23T13:05:00+00:00",
            )
            result = evaluate_message_delivery(
                parse_tnc2_frame("SP5ABC>APRS,TCPIP*,qAC,SERVER::SQ9MDD-7:hello{42"),
                flow_id=1,
                local_igate="SQ9MDD-4",
                now=_dt("2026-07-23T13:10:00+00:00"),
            )
            self.assertEqual(result["route"], "drop")
            self.assertEqual(result["reason"], "message_recipient_seen_internet")

    def test_sender_heard_on_local_rf_is_rejected(self) -> None:
        with temporary_database():
            interface_id = insert_interface("RF-OUT", "TCP")
            for callsign in ("SQ9MDD-7", "SP5ABC"):
                parsed = parse_tnc2_frame(f"{callsign}>APRS:>local")
                assert parsed is not None
                record_rf_heard_station(
                    parsed,
                    interface_id=interface_id,
                    timestamp="2026-07-23T13:00:00+00:00",
                )

            result = evaluate_message_delivery(
                parse_tnc2_frame("SP5ABC>APRS,TCPIP*,qAC,SERVER::SQ9MDD-7:hello{42"),
                flow_id=1,
                local_igate="SQ9MDD-4",
                now=_dt("2026-07-23T13:10:00+00:00"),
            )
            self.assertEqual(result["route"], "drop")
            self.assertEqual(result["reason"], "message_sender_heard_local_rf")

    def test_rf_third_party_packet_marks_inner_station_as_internet_origin(self) -> None:
        with temporary_database():
            interface_id = insert_interface("RF-OUT", "TCP")
            parsed = parse_tnc2_frame(
                "SR5IGT>APRS:}SP5ABC-2>APRS,TCPIP,SR5IGT*:>from Internet"
            )
            assert parsed is not None

            record_rf_heard_station(
                parsed,
                interface_id=interface_id,
                timestamp="2026-07-23T13:00:00+00:00",
            )

            rf_row = fetch_one(
                "SELECT station_key FROM aprsis_igate_rf_heard WHERE station_key = 'SR5IGT'"
            )
            internet_row = fetch_one(
                """
                SELECT station_key
                FROM aprsis_igate_station_state
                WHERE station_key = 'SP5ABC-2'
                """
            )
            wrong_outer_row = fetch_one(
                """
                SELECT station_key
                FROM aprsis_igate_station_state
                WHERE station_key = 'SR5IGT'
                """
            )
            self.assertIsNotNone(rf_row)
            self.assertIsNotNone(internet_row)
            self.assertIsNone(wrong_outer_row)

    def test_stale_igate_state_is_pruned(self) -> None:
        with temporary_database():
            interface_id = insert_interface("RF-OUT", "TCP")
            parsed = parse_tnc2_frame("SQ9MDD-7>APRS:>local")
            internet = parse_tnc2_frame("SP5ABC>APRS,TCPIP*,qAC,SERVER:>online")
            assert parsed is not None and internet is not None
            record_rf_heard_station(
                parsed,
                interface_id=interface_id,
                timestamp="2026-07-23T10:00:00+00:00",
            )
            record_aprsis_station_presence(
                internet,
                timestamp="2026-07-23T10:00:00+00:00",
            )

            deleted = prune_igate_runtime_state(
                now=_dt("2026-07-23T13:00:01+00:00"),
            )

            self.assertEqual(deleted["aprsis_igate_rf_heard"], 1)
            self.assertEqual(deleted["aprsis_igate_station_state"], 1)


class IgateMessagingRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_aprsis_message_to_local_station_returns_ack_only_through_local_tx_uplink(self) -> None:
        with temporary_database():
            set_station_identity()
            aprsis_interface_id = insert_interface("APRSIS-RX", "APRSIS")
            rf_interface_id = insert_interface("RF-OUT", "TCP")
            execute(
                "UPDATE station_settings SET beacon_interface_id = ? WHERE id = 1",
                (rf_interface_id,),
            )
            create_digi_flow(local_tx_to_aprsis_flow_payload())

            class FakeAprsisClient:
                def __init__(self) -> None:
                    self.lines: list[str] = []

                async def send_tnc2_line(self, line: str) -> tuple[bool, str]:
                    self.lines.append(line)
                    return True, "queued"

            fake_client = FakeAprsisClient()
            routing_runtime = DigiFlowRuntimeService(aprsis_client=fake_client)
            await routing_runtime.start()
            try:
                self.assertTrue(
                    process_normalized_tnc2_rx(
                        "SQ5BIH-1>APBOX0,TCPIP*,qAC,T2WARSPL::SQ9MDD-4 :test{3P",
                        source="APRS-IS · APRSIS-RX",
                        source_kind="aprsis",
                        source_interface_id=aprsis_interface_id,
                    )
                )
                job = claim_next_outbound_job()
                self.assertIsNotNone(job)
                assert job is not None
                self.assertIsNone(job["interface_id"])
                self.assertTrue(job["payload"]["internal_tx_only"])

                await OutboundService(digi_flow_runtime=routing_runtime)._process_job(job)
                await routing_runtime.wait_until_idle()
            finally:
                await routing_runtime.stop()

            self.assertEqual(
                fake_client.lines,
                ["SQ9MDD-4>APBOX0,TCPIP*::SQ5BIH-1 :ack3P"],
            )
            aprsis_tx = fetch_one(
                """
                SELECT source, source_kind, interface_id, direction, format, line, command
                FROM traffic_frames
                WHERE direction = 'tx' AND source_kind = 'aprsis'
                ORDER BY id DESC
                LIMIT 1
                """
            )
            self.assertIsNotNone(aprsis_tx)
            assert aprsis_tx is not None
            self.assertEqual(
                (
                    aprsis_tx["source"],
                    aprsis_tx["source_kind"],
                    aprsis_tx["interface_id"],
                    aprsis_tx["direction"],
                    aprsis_tx["format"],
                    aprsis_tx["line"],
                    aprsis_tx["command"],
                ),
                (
                    "APRS-IS",
                    "aprsis",
                    None,
                    "tx",
                    "TNC2-TX",
                    "SQ9MDD-4>APBOX0,TCPIP*::SQ5BIH-1 :ack3P",
                    "TX",
                ),
            )
            rf_tx = fetch_one(
                """
                SELECT COUNT(*) AS total
                FROM traffic_frames
                WHERE direction = 'tx' AND interface_id = ?
                """,
                (rf_interface_id,),
            )
            self.assertEqual(int((rf_tx or {"total": -1})["total"]), 0)

    async def test_manual_message_is_transmitted_on_rf_and_forwarded_to_aprsis_as_local_tx(self) -> None:
        with temporary_database():
            set_station_identity()
            insert_interface("APRSIS-RX", "APRSIS")
            rf_interface_id = insert_interface("RF-OUT", "TCP")
            execute(
                "UPDATE station_settings SET beacon_interface_id = ? WHERE id = 1",
                (rf_interface_id,),
            )
            create_digi_flow(local_tx_to_aprsis_flow_payload())
            queue_outgoing_message(
                callsign="SQ5BIH-1",
                message_text="test",
                path="WIDE1-1",
            )

            class FakeAprsisClient:
                def __init__(self) -> None:
                    self.lines: list[str] = []

                async def send_tnc2_line(self, line: str) -> tuple[bool, str]:
                    self.lines.append(line)
                    return True, "queued"

            class FakeTrafficMonitor:
                def __init__(self) -> None:
                    self.frames: list[tuple[int | None, bytes]] = []

                async def send_outbound_frame(self, *, interface_id: int | None, frame: bytes) -> bool:
                    self.frames.append((interface_id, frame))
                    return True

            fake_client = FakeAprsisClient()
            fake_monitor = FakeTrafficMonitor()
            routing_runtime = DigiFlowRuntimeService(aprsis_client=fake_client)
            await routing_runtime.start()
            try:
                job = claim_next_outbound_job()
                self.assertIsNotNone(job)
                assert job is not None
                self.assertEqual(job["interface_id"], rf_interface_id)
                self.assertFalse(bool(job["payload"].get("internal_tx_only")))

                await OutboundService(
                    traffic_monitor=fake_monitor,
                    digi_flow_runtime=routing_runtime,
                )._process_job(job)
                await routing_runtime.wait_until_idle()
            finally:
                await routing_runtime.stop()

            self.assertEqual(len(fake_monitor.frames), 1)
            self.assertEqual(fake_monitor.frames[0][0], rf_interface_id)
            self.assertEqual(len(fake_client.lines), 1)
            self.assertTrue(fake_client.lines[0].startswith("SQ9MDD-4>APBOX0,TCPIP*::SQ5BIH-1 :test{"))

    async def test_empty_allowlist_still_delivers_local_message_and_next_sender_position_once(self) -> None:
        with temporary_database():
            set_station_identity()
            insert_interface("APRSIS-RX", "APRSIS")
            target_id = insert_interface("RF-OUT", "TCP")
            flow_id = create_digi_flow(return_flow_payload())
            local = parse_tnc2_frame("SQ9MDD-7>APRS:>local")
            assert local is not None
            record_rf_heard_station(
                local,
                interface_id=target_id,
                timestamp=utc_now(),
            )

            runtime = DigiFlowRuntimeService(aprsis_rf_delay_override=0)
            await runtime.start()
            try:
                runtime.enqueue_tnc2_frame(
                    source_kind=APRSIS_FLOW_SOURCE_KIND,
                    source_ref="APRSIS-RX",
                    raw_payload="SP5ABC>APRS,TCPIP*,qAC,SERVER::SQ9MDD-7:hello{42",
                )
                await runtime.wait_until_idle()
                runtime.enqueue_tnc2_frame(
                    source_kind=APRSIS_FLOW_SOURCE_KIND,
                    source_ref="APRSIS-RX",
                    raw_payload="SP5ABC>APRS,TCPIP*,qAC,SERVER:!5213.78N/02100.72E>sender",
                )
                await runtime.wait_until_idle()
                runtime.enqueue_tnc2_frame(
                    source_kind=APRSIS_FLOW_SOURCE_KIND,
                    source_ref="APRSIS-RX",
                    raw_payload="SP5ABC>APRS,TCPIP*,qAC,SERVER:!5213.79N/02100.73E>second",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            jobs = fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs")
            assert jobs is not None
            self.assertEqual(int(jobs["total"]), 2)
            first = fetch_one("SELECT payload_json FROM outbound_jobs ORDER BY id ASC LIMIT 1")
            assert first is not None
            self.assertIn("}SP5ABC>APRS,TCPIP,SQ9MDD-4*::SQ9MDD-7:hello{42", str(first["payload_json"]))
            stats = get_aprsis_rf_stats(flow_id)
            self.assertEqual(stats["matched_message_rule"], 1)
            self.assertEqual(stats["matched_associated_position"], 1)
            self.assertEqual(stats["dropped_no_allow_rule"], 1)
            message_summary = next(
                summary
                for summary in get_digi_flow_execution_summaries(flow_id)
                if "hello{42" in str(summary["raw_packet"])
            )
            self.assertEqual(
                [step["status"] for step in message_summary["steps"]],
                ["passed", "passed", "passed", "skipped", "passed", "executed"],
            )

    async def test_optional_allow_traffic_cannot_exhaust_message_rate_bucket(self) -> None:
        with temporary_database():
            set_station_identity()
            insert_interface("APRSIS-RX", "APRSIS")
            target_id = insert_interface("RF-OUT", "TCP")
            payload = return_flow_payload()
            allow_step = next(
                step for step in payload["steps"] if step["step_type"] == "filter_allow_rules"
            )
            allow_step["config"] = {"callsigns": ["SP5POS"], "radius_km": "5"}
            tx_guard = next(
                step for step in payload["steps"] if step["step_type"] == "filter_rf_tx_guard"
            )
            tx_guard["config"].update(
                {
                    "flow_rate_per_minute": 1,
                    "flow_burst": 1,
                    "source_rate_per_minute": 1,
                    "source_burst": 1,
                }
            )
            create_digi_flow(payload)
            local = parse_tnc2_frame("SQ9MDD-7>APRS:>local")
            assert local is not None
            record_rf_heard_station(
                local,
                interface_id=target_id,
                timestamp=utc_now(),
            )

            runtime = DigiFlowRuntimeService(aprsis_rf_delay_override=0)
            await runtime.start()
            try:
                runtime.enqueue_tnc2_frame(
                    source_kind=APRSIS_FLOW_SOURCE_KIND,
                    source_ref="APRSIS-RX",
                    raw_payload=(
                        "SP5POS>APRS,TCPIP*,qAC,SERVER:"
                        "!5213.78N/02100.72E>optional allow traffic"
                    ),
                )
                await runtime.wait_until_idle()
                runtime.enqueue_tnc2_frame(
                    source_kind=APRSIS_FLOW_SOURCE_KIND,
                    source_ref="APRSIS-RX",
                    raw_payload="SP5MSG>APRS,TCPIP*,qAC,SERVER::SQ9MDD-7:hello{42",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            jobs = fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs")
            assert jobs is not None
            self.assertEqual(int(jobs["total"]), 2)

    async def test_q_construct_tracks_active_message_return_flow_and_local_tx_uses_tcpip(self) -> None:
        with temporary_database():
            set_station_identity()
            insert_interface("APRSIS-RX", "APRSIS")
            insert_interface("RF-OUT", "TCP")
            return_flow_id = create_digi_flow(return_flow_payload())
            self.assertEqual(message_return_capable_for_rf_source("RF-OUT")[0], True)
            self.assertEqual(
                message_return_capable_for_rf_source("RF-OUT", consumed_hops=1)[0],
                False,
            )
            execute("UPDATE modems SET tx_blocked = 1 WHERE name = 'RF-OUT'")
            self.assertEqual(message_return_capable_for_rf_source("RF-OUT")[0], False)
            execute("UPDATE modems SET tx_blocked = 0 WHERE name = 'RF-OUT'")
            create_digi_flow(rf_to_aprsis_flow_payload())
            create_digi_flow(local_tx_to_aprsis_flow_payload())

            class FakeAprsisClient:
                def __init__(self) -> None:
                    self.lines: list[str] = []

                async def send_tnc2_line(self, line: str) -> tuple[bool, str]:
                    self.lines.append(line)
                    return True, "queued"

            fake_client = FakeAprsisClient()
            runtime = DigiFlowRuntimeService(aprsis_client=fake_client)
            await runtime.start()
            try:
                runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="RF-OUT",
                    raw_payload="SP5AAA>APRS,WIDE1-1:>qAR",
                )
                await runtime.wait_until_idle()
                runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="RF-OUT",
                    raw_payload="SP5AAB>APRS,WIDE1-1*:>qAO indirect",
                )
                await runtime.wait_until_idle()
                set_digi_flow_enabled(return_flow_id, False)
                runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="RF-OUT",
                    raw_payload="SP5BBB>APRS,WIDE1-1:>qAO",
                )
                await runtime.wait_until_idle()
                runtime.enqueue_tnc2_frame(
                    source_kind="receiver_local_tx",
                    source_ref="local_tx",
                    raw_payload="SQ9MDD-4>APRS,WIDE1-1:>local",
                    metadata={
                        "origin": "local_generated",
                        "local_generated": True,
                        "frame_purpose": "beacon",
                    },
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            self.assertEqual(len(fake_client.lines), 4)
            self.assertIn(",qAR,SQ9MDD-4:", fake_client.lines[0])
            self.assertIn(",qAO,SQ9MDD-4:", fake_client.lines[1])
            self.assertIn(",qAO,SQ9MDD-4:", fake_client.lines[2])
            self.assertEqual(fake_client.lines[3], "SQ9MDD-4>APRS,TCPIP*:>local")


def _dt(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)


if __name__ == "__main__":
    unittest.main()
