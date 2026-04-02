import contextlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db import connect, init_db
from app.services.digi_flows import create_digi_flow, get_digi_flow, normalize_digi_flow_payload


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


def sample_flow_payload() -> dict:
    return {
        "name": "RF ingress",
        "description": "Simple flow",
        "source_kind": "receiver_rf",
        "source_ref": "TNC-1",
        "target_kind": "tx_aprsis",
        "target_ref": "APRS-IS Main",
        "enabled": 1,
        "steps": [
            {
                "step_type": "receiver_rf",
                "title": "Receiver RF",
                "enabled": 1,
                "config": {"rf_port": "TNC-1"},
            },
            {
                "step_type": "filter_path",
                "title": "Path Filter",
                "enabled": 1,
                "config": {"mode": "allow", "trace_paths": ["WIDE1-1"], "no_trace_paths": ["SP2-2"]},
            },
            {
                "step_type": "tx_aprsis",
                "title": "TX APRS-IS",
                "enabled": 1,
                "config": {"aprsis_target": "APRS-IS Main"},
            },
        ],
    }


class DigiFlowsTests(unittest.TestCase):
    def test_init_db_creates_digi_flow_tables_and_constraints(self) -> None:
        with temporary_database():
            connection = connect()
            try:
                table_names = {
                    row["name"]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                }
                self.assertIn("digi_flows", table_names)
                self.assertIn("digi_flow_steps", table_names)

                create_digi_flow(sample_flow_payload())
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """
                        INSERT INTO digi_flows (
                            name, description, source_kind, source_ref, target_kind, target_ref, enabled, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "Duplicate",
                            "",
                            "receiver_rf",
                            "TNC-1",
                            "tx_aprsis",
                            "APRS-IS Main",
                            1,
                            "2026-01-01T00:00:00+00:00",
                            "2026-01-01T00:00:00+00:00",
                        ),
                    )
            finally:
                connection.close()

    def test_normalize_digi_flow_requires_source_first_and_target_last(self) -> None:
        payload = sample_flow_payload()
        payload["steps"] = [payload["steps"][1], payload["steps"][0], payload["steps"][2]]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "First flow step must be a source step"):
                normalize_digi_flow_payload(payload)

    def test_create_digi_flow_persists_steps(self) -> None:
        with temporary_database():
            flow_id = create_digi_flow(sample_flow_payload())
            flow = get_digi_flow(flow_id)
            assert flow is not None
            self.assertEqual(flow["source_kind"], "receiver_rf")
            self.assertEqual(flow["target_kind"], "tx_aprsis")
            self.assertEqual(len(flow["steps"]), 3)
            self.assertEqual(flow["steps"][0]["step_type"], "receiver_rf")
            self.assertEqual(flow["steps"][1]["step_type"], "filter_path")
            self.assertEqual(flow["steps"][2]["step_type"], "tx_aprsis")

    def test_new_filter_types_and_packet_type_mode_are_accepted(self) -> None:
        payload = sample_flow_payload()
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_digi",
                "title": "DIGI Filter",
                "enabled": 1,
                "config": {"mode": "deny", "digis": ["WIDE1-1", "TRACE2-2"]},
            },
            {
                "step_type": "filter_path",
                "title": "Path Filter",
                "enabled": 1,
                "config": {"mode": "allow", "trace_paths": ["WIDE1-1"], "no_trace_paths": ["SP2-2"]},
            },
            {
                "step_type": "filter_packet_type",
                "title": "Packet Type Filter",
                "enabled": 1,
                "config": {"mode": "allow", "packet_types": ["position", "message"]},
            },
            {
                "step_type": "filter_icon",
                "title": "Icon Filter",
                "enabled": 1,
                "config": {"mode": "allow", "icons": ["/>", "\\#"]},
            },
            {
                "step_type": "filter_rate_limit_per_callsign",
                "title": "Rate Limit Per Callsign",
                "enabled": 1,
                "config": {"packets_per_minute": 5},
            },
            payload["steps"][2],
        ]
        with temporary_database():
            normalized = normalize_digi_flow_payload(payload)
            self.assertEqual(normalized["steps"][1]["config"]["mode"], "deny")
            self.assertEqual(normalized["steps"][2]["config"]["trace_paths"], ["WIDE1-1"])
            self.assertEqual(normalized["steps"][3]["config"]["mode"], "allow")
            self.assertEqual(normalized["steps"][4]["config"]["icons"], ["/>", "\\#"])
            self.assertEqual(normalized["steps"][5]["config"]["packets_per_minute"], 5)

    def test_path_filter_uses_trace_and_no_trace_fields(self) -> None:
        payload = sample_flow_payload()
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_path",
                "title": "Path Filter",
                "enabled": 1,
                "config": {
                    "mode": "allow",
                    "trace_paths": ["TRACE2-2", "WIDE1-1"],
                    "no_trace_paths": ["TCPIP", "NOGATE"],
                },
            },
            payload["steps"][2],
        ]
        with temporary_database():
            normalized = normalize_digi_flow_payload(payload)
            self.assertEqual(normalized["steps"][1]["config"]["trace_paths"], ["TRACE2-2", "WIDE1-1"])
            self.assertEqual(normalized["steps"][1]["config"]["no_trace_paths"], ["TCPIP", "NOGATE"])

    def test_non_log_target_requires_path_filter(self) -> None:
        payload = sample_flow_payload()
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_dupe",
                "title": "Duplicate Filter",
                "enabled": 1,
                "config": {"window_sec": 30},
            },
            payload["steps"][2],
        ]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "must include at least one Path Rule"):
                normalize_digi_flow_payload(payload)

    def test_path_filter_allows_only_allow_mode(self) -> None:
        payload = sample_flow_payload()
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_path",
                "title": "Path Filter",
                "enabled": 1,
                "config": {
                    "mode": "deny",
                    "trace_paths": ["WIDE1-1"],
                    "no_trace_paths": [],
                },
            },
            payload["steps"][2],
        ]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "Path filter mode must be allow"):
                normalize_digi_flow_payload(payload)


if __name__ == "__main__":
    unittest.main()
