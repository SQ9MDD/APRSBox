import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, fetch_all, fetch_one, init_db
from app.services.digi_flow_runtime import DigiFlowRuntimeService
from app.services.digi_flows import create_digi_flow, get_digi_flow_event_log


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
            self.assertTrue(get_digi_flow_event_log(flow_id))

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

    async def test_filter_then_path_rule_reaches_tx_stub(self) -> None:
        with temporary_database():
            set_local_station_identity()
            create_flow(
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
            self.assertTrue(any(row["event_type"] == "output_action" and row["decision"] == "tx" and "would transmit to target RF:RF-OUT" in row["message"] for row in rows))
            self.assertTrue(any(row["event_type"] == "pipeline_finished" and row["decision"] == "tx" for row in rows))


if __name__ == "__main__":
    unittest.main()
