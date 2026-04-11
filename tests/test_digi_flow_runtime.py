import contextlib
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.services.digi_flows as digi_flows
from app.db import execute, fetch_all, fetch_one, init_db
from app.services.digi_flow_runtime import DigiFlowRuntimeService
from app.services.digi_flows import create_digi_flow, get_digi_flow_event_log, get_digi_flow_execution_summaries, update_digi_flow
from app.services.outbound import claim_next_outbound_job, enqueue_digi_tx_job, get_outbound_job
from app.services.outbound_runtime import OutboundService
from app.services.traffic import TrafficMonitorService


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


def set_local_station_identity(callsign: str = "SQ9MDD", ssid: str = "4") -> None:
    execute(
        """
        UPDATE station_settings
        SET callsign = ?, ssid = ?, updated_at = '2026-01-01T00:00:00+00:00'
        WHERE id = 1
        """,
        (callsign, ssid),
    )


def create_flow(payload: dict) -> int:
    flow_id = create_digi_flow(payload)
    row = fetch_one("SELECT id FROM digi_flows WHERE id = ?", (flow_id,))
    assert row is not None
    return int(row["id"])


def insert_modem(*, name: str = "RF-OUT", device_path: str = "127.0.0.1:9001") -> int:
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


def event_rows_for_frame(frame_uid: str) -> list[dict]:
    rows = fetch_all(
        """
        SELECT frame_uid, event_type, decision, message
        FROM digi_flow_event_log
        WHERE frame_uid = ?
        ORDER BY id ASC
        """,
        (frame_uid,),
    )
    return [dict(row) for row in rows]


class DigiFlowRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_rx_to_log_only_records_runtime_log(self) -> None:
        with temporary_database():
            flow_id = create_flow(
                {
                    "name": "RX LOG",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": "RX only"}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                result = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,WIDE1-1:>Runtime test",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            rows = event_rows_for_frame(str(result["frame_uid"]))
            self.assertEqual(rows[0]["event_type"], "frame_received")
            self.assertTrue(any(row["event_type"] == "output_action" and row["decision"] == "log_only" for row in rows))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "log_only" for row in rows))
            self.assertEqual(sum(1 for row in rows if row["event_type"] == "pipeline_finished"), 1)
            self.assertTrue(get_digi_flow_event_log(flow_id))

    async def test_runtime_matches_rf_source_with_and_without_tnc_prefix(self) -> None:
        with temporary_database():
            flow_id = create_flow(
                {
                    "name": "Alias LOG",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "Bailly",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "Bailly"}},
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                runtime.enqueue_rx_tnc2_frame("SP8ABC-9>APRS,WIDE1-1:>Alias test", source_ref="TNC@Bailly")
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            rows = get_digi_flow_event_log(flow_id)
            self.assertTrue(any(row["event_type"] == "flow_matched" for row in rows))
            self.assertTrue(any(row["event_type"] == "output_action" and row["decision"] == "log_only" for row in rows))

    async def test_duplicate_filter_viscous_delay_drops_same_source_and_payload_even_with_different_paths(self) -> None:
        with temporary_database():
            create_flow(
                {
                    "name": "Viscous delay duplicates",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {
                            "step_type": "filter_dupe",
                            "title": "Duplicate Filter (viscous-delay)",
                            "enabled": 1,
                            "config": {"window_sec": 2},
                        },
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                first = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SQ9MDD-9>APRS,WIDE1-1:>Viscous duplicate",
                )
                second = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SQ9MDD-9>APRS,TRACE2-2:>Viscous duplicate",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            first_rows = event_rows_for_frame(str(first["frame_uid"]))
            second_rows = event_rows_for_frame(str(second["frame_uid"]))
            self.assertTrue(any(row["event_type"] == "filter_dupe" and row["decision"] == "rejected" for row in first_rows))
            self.assertTrue(any(row["event_type"] == "filter_dupe" and row["decision"] == "rejected" for row in second_rows))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "drop" for row in first_rows))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "drop" for row in second_rows))
            self.assertFalse(any(row["event_type"] == "output_action" for row in first_rows))
            self.assertFalse(any(row["event_type"] == "output_action" for row in second_rows))
            self.assertTrue(any("duplicate seen within 2s" in row["message"] for row in second_rows if row["event_type"] == "filter_dupe"))

    async def test_duplicate_filter_viscous_delay_waits_then_allows_unique_fingerprints(self) -> None:
        with temporary_database():
            create_flow(
                {
                    "name": "Viscous delay pass",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {
                            "step_type": "filter_dupe",
                            "title": "Duplicate Filter (viscous-delay)",
                            "enabled": 1,
                            "config": {"window_sec": 2},
                        },
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                first = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SQ9MDD-9>APRS,WIDE1-1:>Window check",
                )
                await asyncio.sleep(0.25)
                first_early_rows = event_rows_for_frame(str(first["frame_uid"]))
                self.assertTrue(any(row["event_type"] == "filter_dupe" and row["decision"] == "waiting" for row in first_early_rows))
                self.assertFalse(any(row["event_type"] == "output_action" for row in first_early_rows))

                second = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SQ8XYZ-1>APRS,TRACE2-2:>Window check",
                )
                third = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SQ9MDD-9>APRS,WIDE2-2:>Different payload",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            for frame_uid in (str(first["frame_uid"]), str(second["frame_uid"]), str(third["frame_uid"])):
                rows = event_rows_for_frame(frame_uid)
                self.assertTrue(any(row["event_type"] == "filter_dupe" and row["decision"] == "passed" for row in rows))
                self.assertTrue(any(row["event_type"] == "output_action" and row["decision"] == "log_only" for row in rows))
                self.assertTrue(any("duplicate window expired" in row["message"] for row in rows if row["event_type"] == "filter_dupe"))
                self.assertFalse(any(row["event_type"] == "filter_dupe" and row["decision"] == "rejected" for row in rows))

    async def test_callsign_filter_logs_pass_and_reject(self) -> None:
        with temporary_database():
            create_flow(
                {
                    "name": "Callsign LOG",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {
                            "step_type": "filter_callsign",
                            "title": "Callsign Filter",
                            "enabled": 1,
                            "config": {"mode": "allow", "callsigns": ["SP8ABC-9"]},
                        },
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                allowed = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,WIDE1-1:>Allowed",
                )
                denied = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP7XYZ-1>APRS,WIDE1-1:>Denied",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            allowed_rows = event_rows_for_frame(str(allowed["frame_uid"]))
            denied_rows = event_rows_for_frame(str(denied["frame_uid"]))
            self.assertTrue(any(row["event_type"] == "filter_callsign" and row["decision"] == "passed" for row in allowed_rows))
            self.assertTrue(any(row["event_type"] == "output_action" and row["decision"] == "log_only" for row in allowed_rows))
            self.assertTrue(any(row["event_type"] == "filter_callsign" and row["decision"] == "rejected" for row in denied_rows))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "drop" for row in denied_rows))

    async def test_callsign_filter_supports_wildcard_patterns(self) -> None:
        with temporary_database():
            create_flow(
                {
                    "name": "Callsign wildcard",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {
                            "step_type": "filter_callsign",
                            "title": "Callsign Filter",
                            "enabled": 1,
                            "config": {"mode": "allow", "callsigns": ["SQ9MDD*", "SQ*"]},
                        },
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                exact_prefix = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SQ9MDD-4>APRS,WIDE1-1:>Wildcard SSID",
                )
                broad_prefix = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SQ5ABC-1>APRS,WIDE1-1:>Wildcard prefix",
                )
                rejected = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,WIDE1-1:>Out of pattern",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            exact_rows = event_rows_for_frame(str(exact_prefix["frame_uid"]))
            broad_rows = event_rows_for_frame(str(broad_prefix["frame_uid"]))
            rejected_rows = event_rows_for_frame(str(rejected["frame_uid"]))
            self.assertTrue(any(row["event_type"] == "filter_callsign" and row["decision"] == "passed" and "matched pattern SQ9MDD*" in row["message"] for row in exact_rows))
            self.assertTrue(any(row["event_type"] == "filter_callsign" and row["decision"] == "passed" and "matched pattern SQ*" in row["message"] for row in broad_rows))
            self.assertTrue(any(row["event_type"] == "filter_callsign" and row["decision"] == "rejected" and "did not match any allow pattern" in row["message"] for row in rejected_rows))

    async def test_packet_type_filter_logs_pass_and_reject(self) -> None:
        with temporary_database():
            flow_id = create_flow(
                {
                    "name": "Packet type LOG",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {
                            "step_type": "filter_packet_type",
                            "title": "Packet Type Filter",
                            "enabled": 1,
                            "config": {"mode": "allow", "packet_types": ["position"]},
                        },
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                allowed = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SQ9MDD-7>URQU02,WIDE1-1:'0SWl \x1c\x1dW[/\"55}Mic-E mobile",
                )
                denied = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,WIDE1-1:>Station online",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            allowed_rows = event_rows_for_frame(str(allowed["frame_uid"]))
            denied_rows = event_rows_for_frame(str(denied["frame_uid"]))
            self.assertTrue(any(row["event_type"] == "filter_packet_type" and row["decision"] == "passed" and "group position" in row["message"] for row in allowed_rows))
            self.assertTrue(any(row["event_type"] == "output_action" and row["decision"] == "log_only" for row in allowed_rows))
            self.assertTrue(any(row["event_type"] == "filter_packet_type" and row["decision"] == "rejected" and "group status" in row["message"] for row in denied_rows))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "drop" for row in denied_rows))

            summaries = get_digi_flow_execution_summaries(flow_id)
            allowed_summary = next(summary for summary in summaries if summary["frame_uid"] == str(allowed["frame_uid"]))
            allowed_step = next(step for step in allowed_summary["steps"] if step["step_type"] == "filter_packet_type")
            self.assertEqual(allowed_step["status"], "passed")
            self.assertIn("group position", allowed_step["description"])

    async def test_icon_filter_logs_pass_and_reject(self) -> None:
        with temporary_database():
            flow_id = create_flow(
                {
                    "name": "Icon LOG",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {
                            "step_type": "filter_icon",
                            "title": "Icon Filter",
                            "enabled": 1,
                            "config": {"mode": "allow", "icons": ["/>"]},
                        },
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                allowed = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,WIDE1-1:!5228.23N/02101.28E>Car icon",
                )
                denied = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,WIDE1-1:=5228.23N\\02101.28E#Digi icon",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            allowed_rows = event_rows_for_frame(str(allowed["frame_uid"]))
            denied_rows = event_rows_for_frame(str(denied["frame_uid"]))
            self.assertTrue(any(row["event_type"] == "filter_icon" and row["decision"] == "passed" and "inspected />" in row["message"] for row in allowed_rows))
            self.assertTrue(any(row["event_type"] == "output_action" and row["decision"] == "log_only" for row in allowed_rows))
            self.assertTrue(any(row["event_type"] == "filter_icon" and row["decision"] == "rejected" and "did not match any allow symbol" in row["message"] for row in denied_rows))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "drop" for row in denied_rows))

            summaries = get_digi_flow_execution_summaries(flow_id)
            allowed_summary = next(summary for summary in summaries if summary["frame_uid"] == str(allowed["frame_uid"]))
            allowed_step = next(step for step in allowed_summary["steps"] if step["step_type"] == "filter_icon")
            self.assertEqual(allowed_step["status"], "passed")
            self.assertIn("inspected />", allowed_step["description"])

    async def test_packet_type_filter_preserves_legacy_frame_type_codes(self) -> None:
        with temporary_database():
            create_flow(
                {
                    "name": "Packet type legacy",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {
                            "step_type": "filter_packet_type",
                            "title": "Packet Type Filter",
                            "enabled": 1,
                            "config": {"mode": "allow", "packet_types": ["M"]},
                        },
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                allowed = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SQ9MDD-7>URQU02,WIDE1-1:'0SWl \x1c\x1dW[/\"55}Mic-E mobile",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            allowed_rows = event_rows_for_frame(str(allowed["frame_uid"]))
            self.assertTrue(any(row["event_type"] == "filter_packet_type" and row["decision"] == "passed" and "matched configured group M" in row["message"] for row in allowed_rows))

    async def test_path_rule_logs_trace_no_trace_and_reject(self) -> None:
        with temporary_database():
            set_local_station_identity()
            create_flow(
                {
                    "name": "Path LOG",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {
                            "step_type": "filter_path",
                            "title": "Path Rule",
                            "enabled": 1,
                            "config": {"mode": "allow", "trace_paths": ["WIDE2-2"], "no_trace_paths": ["SP2-2"]},
                        },
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                trace = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,WIDE2-2:>Trace",
                )
                no_trace = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,SP2-2:>No trace",
                )
                rejected = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,TCPIP:>Reject",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            trace_rows = event_rows_for_frame(str(trace["frame_uid"]))
            no_trace_rows = event_rows_for_frame(str(no_trace["frame_uid"]))
            rejected_rows = event_rows_for_frame(str(rejected["frame_uid"]))
            self.assertTrue(any(row["event_type"] == "path_rule" and row["decision"] == "trace" and "SQ9MDD-4*" in row["message"] for row in trace_rows))
            self.assertTrue(any(row["event_type"] == "path_rule" and row["decision"] == "no_trace" and "SP2-2*,SP2-1" in row["message"] for row in no_trace_rows))
            self.assertTrue(any(row["event_type"] == "path_rule" and row["decision"] == "rejected" for row in rejected_rows))

    async def test_strict_filter_rejects_tcp_nogate_and_rfonly_paths(self) -> None:
        with temporary_database():
            set_local_station_identity()
            create_flow(
                {
                    "name": "Strict APRSIS",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "tx_aprsis",
                    "target_ref": "aprsis",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {"step_type": "filter_strict", "title": "Strict Filter", "enabled": 1, "config": {}},
                        {"step_type": "tx_aprsis", "title": "TX APRS-IS", "enabled": 1, "config": {"aprsis_target": "aprsis"}},
                    ],
                }
            )

            class FakeAprsisClient:
                def __init__(self) -> None:
                    self.lines: list[str] = []

                async def send_tnc2_line(self, line: str) -> tuple[bool, str]:
                    self.lines.append(line)
                    return True, "APRS-IS TX queued."

            fake_client = FakeAprsisClient()
            runtime = DigiFlowRuntimeService(aprsis_client=fake_client)
            await runtime.start()
            try:
                clean = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,WIDE1-1:>Clean",
                )
                tcp = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,TCPIP*:>TCP reject",
                )
                nogate = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,NOGATE:>NOGATE reject",
                )
                rfonly = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,RFONLY:>RFONLY reject",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            clean_rows = event_rows_for_frame(str(clean["frame_uid"]))
            tcp_rows = event_rows_for_frame(str(tcp["frame_uid"]))
            nogate_rows = event_rows_for_frame(str(nogate["frame_uid"]))
            rfonly_rows = event_rows_for_frame(str(rfonly["frame_uid"]))
            self.assertTrue(any(row["event_type"] == "strict_filter" and row["decision"] == "passed" for row in clean_rows))
            self.assertTrue(any(row["event_type"] == "output_action" and row["decision"] == "tx" for row in clean_rows))
            self.assertTrue(any(row["event_type"] == "strict_filter" and row["decision"] == "rejected" and "TCPIP" in row["message"] for row in tcp_rows))
            self.assertTrue(any(row["event_type"] == "strict_filter" and row["decision"] == "rejected" and "NOGATE" in row["message"] for row in nogate_rows))
            self.assertTrue(any(row["event_type"] == "strict_filter" and row["decision"] == "rejected" and "RFONLY" in row["message"] for row in rfonly_rows))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "drop" for row in tcp_rows))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "drop" for row in nogate_rows))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "drop" for row in rfonly_rows))
            self.assertEqual(len(fake_client.lines), 1)
            self.assertIn("qAO,SQ9MDD-4", fake_client.lines[0])

    async def test_path_rule_rejects_when_local_digi_is_already_consumed_in_path(self) -> None:
        with temporary_database():
            set_local_station_identity()
            create_flow(
                {
                    "name": "Path self-repeat guard",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {
                            "step_type": "filter_path",
                            "title": "Path Rule",
                            "enabled": 1,
                            "config": {"mode": "allow", "trace_paths": ["WIDE1-1", "WIDE2-1"], "no_trace_paths": []},
                        },
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                rejected = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,SQ9MDD-4*,WIDE2-1:>Do not repeat self",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            rejected_rows = event_rows_for_frame(str(rejected["frame_uid"]))
            self.assertTrue(
                any(
                    row["event_type"] == "path_rule"
                    and row["decision"] == "rejected"
                    and "already appears as a consumed hop" in row["message"]
                    for row in rejected_rows
                )
            )
            self.assertFalse(any(row["event_type"] == "output_action" for row in rejected_rows))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "drop" for row in rejected_rows))

    async def test_digi_flow_event_log_retains_only_latest_completed_executions_per_flow(self) -> None:
        with temporary_database():
            flow_id = create_flow(
                {
                    "name": "Retention LOG",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            with patch.object(digi_flows, "DIGI_FLOW_EXECUTION_RETENTION_LIMIT", 2):
                await runtime.start()
                try:
                    first = runtime.enqueue_tnc2_frame(
                        source_kind="receiver_rf",
                        source_ref="TNC-1",
                        raw_payload="SP8ABC-9>APRS:>Retention 1",
                    )
                    second = runtime.enqueue_tnc2_frame(
                        source_kind="receiver_rf",
                        source_ref="TNC-1",
                        raw_payload="SP8ABC-9>APRS:>Retention 2",
                    )
                    third = runtime.enqueue_tnc2_frame(
                        source_kind="receiver_rf",
                        source_ref="TNC-1",
                        raw_payload="SP8ABC-9>APRS:>Retention 3",
                    )
                    await runtime.wait_until_idle()
                finally:
                    await runtime.stop()

            remaining = fetch_all(
                """
                SELECT DISTINCT frame_uid
                FROM digi_flow_event_log
                WHERE flow_id = ?
                ORDER BY id ASC
                """,
                (flow_id,),
            )
            remaining_frame_uids = [str(row["frame_uid"]) for row in remaining]
            self.assertEqual(remaining_frame_uids, [str(second["frame_uid"]), str(third["frame_uid"])])

            summaries = get_digi_flow_execution_summaries(flow_id, execution_limit=10)
            self.assertEqual([str(item["frame_uid"]) for item in summaries], [str(third["frame_uid"]), str(second["frame_uid"])])
            self.assertTrue(all(item["final_result"] == "LOGGED" for item in summaries))
            self.assertFalse(any(str(item["frame_uid"]) == str(first["frame_uid"]) for item in summaries))

    async def test_filter_then_path_rule_reaches_rf_tx_queue(self) -> None:
        with temporary_database():
            insert_modem(name="RF-OUT", device_path="127.0.0.1:9003")
            set_local_station_identity()
            flow_id = create_flow(
                {
                    "name": "TX stub",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "tx_rf",
                    "target_ref": "RF-OUT",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {
                            "step_type": "filter_callsign",
                            "title": "Callsign Filter",
                            "enabled": 1,
                            "config": {"mode": "allow", "callsigns": ["SP8ABC-9"]},
                        },
                        {
                            "step_type": "filter_path",
                            "title": "Path Rule",
                            "enabled": 1,
                            "config": {"mode": "allow", "trace_paths": ["WIDE1-1"], "no_trace_paths": []},
                        },
                        {"step_type": "tx_rf", "title": "TX RF", "enabled": 1, "config": {"rf_target": "RF-OUT"}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                result = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,WIDE1-1:>Transmit me",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            rows = event_rows_for_frame(str(result["frame_uid"]))
            self.assertTrue(any(row["event_type"] == "filter_callsign" and row["decision"] == "passed" for row in rows))
            self.assertTrue(any(row["event_type"] == "path_rule" and row["decision"] == "trace" for row in rows))
            self.assertTrue(any(row["event_type"] == "output_action" and row["decision"] == "tx" and "Queued DIGI TX for target RF:RF-OUT." in row["message"] for row in rows))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "tx" for row in rows))
            self.assertEqual(sum(1 for row in rows if row["event_type"] == "pipeline_finished"), 1)
            self.assertEqual(sum(1 for row in rows if row["event_type"] == "output_action"), 1)

            job_row = fetch_one("SELECT kind, status, payload_json FROM outbound_jobs ORDER BY id DESC LIMIT 1")
            assert job_row is not None
            self.assertEqual(job_row["kind"], "digi_tx")
            self.assertEqual(job_row["status"], "queued")
            payload = json.loads(job_row["payload_json"])
            self.assertEqual(payload["frame_uid"], str(result["frame_uid"]))
            self.assertEqual(payload["flow_id"], flow_id)

            summaries = get_digi_flow_execution_summaries(flow_id, execution_limit=5)
            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0]["final_result"], "TX")
            self.assertEqual(summaries[0]["step_path"], "1 -> 2 -> 3 -> 4")
            self.assertEqual(summaries[0]["steps"][1]["status"], "passed")
            self.assertEqual(summaries[0]["steps"][2]["status"], "passed")
            self.assertEqual(summaries[0]["steps"][3]["status"], "executed")

    async def test_outbound_service_sends_digi_tx_job(self) -> None:
        with temporary_database():
            insert_modem(name="RF-OUT", device_path="127.0.0.1:9004")
            success, detail = enqueue_digi_tx_job(
                interface_name="RF-OUT",
                line="SQ9MDD-4>APRS,SQ9MDD-4*,WIDE2-1:>DIGI outbound test",
                flow_id=7,
                frame_uid="frame-123",
            )
            self.assertTrue(success)
            self.assertIn("job #", detail)

            job = claim_next_outbound_job()
            assert job is not None
            self.assertEqual(job["kind"], "digi_tx")

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
                self.assertEqual(port, 9004)
                return object(), FakeWriter()

            outbound_service = OutboundService()
            with patch("app.services.outbound_runtime.asyncio.open_connection", side_effect=fake_open_connection):
                await outbound_service._process_job(job)

            runtime_job = get_outbound_job(int(job["id"]))
            assert runtime_job is not None
            self.assertEqual(runtime_job["status"], "sent")
            self.assertTrue(written_frames)

            monitor = TrafficMonitorService()
            unescaped_payload = monitor._kiss_unescape(written_frames[0][1:-1])
            decoded = monitor._decode_ax25_to_tnc2(unescaped_payload[1:])
            self.assertEqual(decoded, "SQ9MDD-4 > APRS , SQ9MDD-4*,WIDE2-1:>DIGI outbound test")

            traffic_row = fetch_one("SELECT source, line FROM traffic_frames ORDER BY id DESC LIMIT 1")
            assert traffic_row is not None
            self.assertEqual(traffic_row["source"], "RF-OUT")
            self.assertEqual(traffic_row["line"], "SQ9MDD-4>APRS,SQ9MDD-4*,WIDE2-1:>DIGI outbound test")

    async def test_digi_filter_allow_matches_consumed_digi_with_wildcards(self) -> None:
        with temporary_database():
            flow_id = create_flow(
                {
                    "name": "DIGI allow",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {
                            "step_type": "filter_digi",
                            "title": "DIGI Filter",
                            "enabled": 1,
                            "config": {"mode": "allow", "digis": ["SR5ABC", "SR5BCD*", "SR5*"]},
                        },
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                allowed = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,SR5BCD-2*,WIDE1-1:>Allowed digi",
                )
                denied = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,SQ7XYZ-1*,WIDE1-1:>Denied digi",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            allowed_rows = event_rows_for_frame(str(allowed["frame_uid"]))
            denied_rows = event_rows_for_frame(str(denied["frame_uid"]))
            self.assertTrue(any(row["event_type"] == "filter_digi" and row["decision"] == "passed" for row in allowed_rows))
            self.assertTrue(any("SR5BCD*" in row["message"] for row in allowed_rows if row["event_type"] == "filter_digi"))
            self.assertTrue(any(row["event_type"] == "output_action" and row["decision"] == "log_only" for row in allowed_rows))
            self.assertTrue(any(row["event_type"] == "filter_digi" and row["decision"] == "rejected" for row in denied_rows))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "drop" for row in denied_rows))

            summaries = get_digi_flow_execution_summaries(flow_id, execution_limit=5)
            self.assertEqual(len(summaries), 2)
            self.assertEqual(sum(1 for item in summaries if item["final_result"] == "LOGGED"), 1)
            self.assertEqual(sum(1 for item in summaries if item["final_result"] == "REJECTED"), 1)

    async def test_digi_filter_supports_global_wildcard_and_deny_mode(self) -> None:
        with temporary_database():
            flow_id = create_flow(
                {
                    "name": "DIGI deny wildcard",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {
                            "step_type": "filter_digi",
                            "title": "DIGI Filter",
                            "enabled": 1,
                            "config": {"mode": "deny", "digis": ["*"]},
                        },
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                blocked = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,SR5ABC*,WIDE1-1:>Repeated frame",
                )
                passed = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,WIDE1-1:>Not repeated yet",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            blocked_rows = event_rows_for_frame(str(blocked["frame_uid"]))
            passed_rows = event_rows_for_frame(str(passed["frame_uid"]))
            self.assertTrue(any(row["event_type"] == "filter_digi" and row["decision"] == "rejected" for row in blocked_rows))
            self.assertTrue(any("matched pattern *" in row["message"] for row in blocked_rows if row["event_type"] == "filter_digi"))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "drop" for row in blocked_rows))
            self.assertTrue(any(row["event_type"] == "filter_digi" and row["decision"] == "passed" for row in passed_rows))
            self.assertTrue(any(row["event_type"] == "output_action" and row["decision"] == "log_only" for row in passed_rows))

            summaries = get_digi_flow_execution_summaries(flow_id, execution_limit=5)
            self.assertEqual(len(summaries), 2)
            self.assertEqual(sum(1 for item in summaries if item["final_result"] == "REJECTED"), 1)
            self.assertEqual(sum(1 for item in summaries if item["final_result"] == "LOGGED"), 1)

    async def test_direct_only_filter_rejects_any_already_digipeated_frame(self) -> None:
        with temporary_database():
            flow_id = create_flow(
                {
                    "name": "Direct only",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {"step_type": "filter_direct_only", "title": "Direct Only", "enabled": 1, "config": {}},
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                direct = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,WIDE1-1:>Direct frame",
                )
                repeated = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,SP1-1*,WIDE1-1:>Already repeated",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            direct_rows = event_rows_for_frame(str(direct["frame_uid"]))
            repeated_rows = event_rows_for_frame(str(repeated["frame_uid"]))
            self.assertTrue(any(row["event_type"] == "direct_only" and row["decision"] == "passed" for row in direct_rows))
            self.assertTrue(any(row["event_type"] == "output_action" and row["decision"] == "log_only" for row in direct_rows))
            self.assertTrue(any(row["event_type"] == "direct_only" and row["decision"] == "rejected" for row in repeated_rows))
            self.assertTrue(any("SP1-1" in row["message"] for row in repeated_rows if row["event_type"] == "direct_only"))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "drop" for row in repeated_rows))

            summaries = get_digi_flow_execution_summaries(flow_id, execution_limit=5)
            self.assertEqual(len(summaries), 2)
            self.assertEqual(sum(1 for item in summaries if item["final_result"] == "LOGGED"), 1)
            self.assertEqual(sum(1 for item in summaries if item["final_result"] == "REJECTED"), 1)

    async def test_execution_summary_survives_flow_step_id_changes(self) -> None:
        with temporary_database():
            set_local_station_identity()
            flow_id = create_flow(
                {
                    "name": "Mutable LOG",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {
                            "step_type": "filter_callsign",
                            "title": "Callsign Filter",
                            "enabled": 1,
                            "config": {"mode": "allow", "callsigns": ["SP8ABC-9"]},
                        },
                        {
                            "step_type": "filter_path",
                            "title": "Path Rule",
                            "enabled": 1,
                            "config": {"mode": "allow", "trace_paths": ["WIDE1-1"], "no_trace_paths": []},
                        },
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                }
            )
            runtime = DigiFlowRuntimeService()
            await runtime.start()
            try:
                result = runtime.enqueue_tnc2_frame(
                    source_kind="receiver_rf",
                    source_ref="TNC-1",
                    raw_payload="SP8ABC-9>APRS,WIDE1-1:>Before edit",
                )
                await runtime.wait_until_idle()
            finally:
                await runtime.stop()

            update_digi_flow(
                flow_id,
                {
                    "name": "Mutable LOG",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {"step_type": "receiver_rf", "title": "Receiver RF", "enabled": 1, "config": {"rf_port": "TNC-1"}},
                        {
                            "step_type": "filter_digi",
                            "title": "DIGI Filter",
                            "enabled": 1,
                            "config": {"mode": "allow", "digis": ["SR5*"]},
                        },
                        {
                            "step_type": "filter_callsign",
                            "title": "Callsign Filter",
                            "enabled": 1,
                            "config": {"mode": "allow", "callsigns": ["SP8ABC-9"]},
                        },
                        {
                            "step_type": "filter_path",
                            "title": "Path Rule",
                            "enabled": 1,
                            "config": {"mode": "allow", "trace_paths": ["WIDE1-1"], "no_trace_paths": []},
                        },
                        {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
                    ],
                },
            )

            summaries = get_digi_flow_execution_summaries(flow_id, execution_limit=5)
            self.assertEqual(len(summaries), 1)
            self.assertEqual(str(summaries[0]["frame_uid"]), str(result["frame_uid"]))
            self.assertEqual(summaries[0]["final_result"], "LOGGED")
            self.assertTrue(summaries[0]["layout_changed"])
            self.assertIn("before the current flow layout was saved", summaries[0]["layout_note"])
            self.assertEqual(summaries[0]["steps"][0]["status"], "passed")
            self.assertEqual(summaries[0]["steps"][1]["status"], "not_reached")
            self.assertEqual(summaries[0]["steps"][2]["status"], "passed")
            self.assertEqual(summaries[0]["steps"][3]["status"], "passed")
            self.assertEqual(summaries[0]["steps"][4]["status"], "executed")


if __name__ == "__main__":
    unittest.main()
